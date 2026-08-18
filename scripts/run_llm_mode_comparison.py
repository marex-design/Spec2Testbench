import csv
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.config.settings import settings
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.llm.llm_client import LLMClient


CASE_LIST = Path("examples/benchmark_specs/llm_eval_cases.json")
OUT_CSV = Path("results/llm_mode_comparison.csv")
OUT_MD = Path("results/llm_mode_comparison.md")
OUT_JSON = Path("results/llm_mode_comparison.json")


def build_llm_client():
    if not settings.llm.is_configured:
        return None
    return LLMClient(
        provider=settings.llm.default_provider,
        api_key=settings.llm.get_api_key(),
        model=settings.llm.get_model(vision=False),
        temperature=0.2,
    )


def safe_float(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None


def normalize_specification(specification: Specification) -> Specification:
    for _, target in specification.performance_targets.items():
        if not isinstance(target, dict):
            continue
        for bound in ("min", "max", "typ"):
            if bound in target and isinstance(target[bound], str):
                numeric = safe_float(target[bound])
                if numeric is not None:
                    target[bound] = numeric
    return specification


def run_case(case: dict, use_llm: bool, llm_client):
    spec_path = Path(case["spec"])
    netlist_path = Path(case["netlist"])
    specification = normalize_specification(Specification.from_yaml(spec_path))
    pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client if use_llm else None)

    started = time.time()
    try:
        report = pipeline.verify(specification, netlist_path=netlist_path)
        elapsed = time.time() - started
        measurement_names = ",".join(measurement.name for measurement in (report.testbench.measurements if report.testbench else []))
        analysis_types = ",".join(analysis.type.value for analysis in (report.testbench.analyses if report.testbench else []))
        stimulus_types = ",".join(stimulus.type for stimulus in (report.testbench.stimuli if report.testbench else []))
        status = "OK"
        verdict = report.overall_verdict.value
        if use_llm and not report.testbench_generation_success and report.errors:
            status = "SKIPPED"
            verdict = "SKIPPED"
        return {
            "case": case["name"],
            "mode": "llm" if use_llm else "baseline",
            "status": status,
            "testbench_generation_success": bool(report.testbench),
            "simulation_success": report.simulation_success,
            "overall_verdict": verdict,
            "success_rate": report.success_rate,
            "compliance_score": report.compliance_score,
            "nominal_compliance_score": report.nominal_compliance_score,
            "pvt_compliance_score": report.pvt_compliance_score,
            "has_pvt_coverage": report.has_pvt_coverage,
            "measurement_count": len(report.testbench.measurements) if report.testbench else 0,
            "failed_metric_count": len(report.failed_metrics),
            "measurement_names": measurement_names,
            "analysis_types": analysis_types,
            "stimulus_types": stimulus_types,
            "elapsed_s": elapsed,
            "error": "; ".join(report.errors),
        }
    except Exception as exc:
        elapsed = time.time() - started
        return {
            "case": case["name"],
            "mode": "llm" if use_llm else "baseline",
            "status": "ERROR",
            "testbench_generation_success": False,
            "simulation_success": False,
            "overall_verdict": "ERROR",
            "success_rate": 0.0,
            "compliance_score": 0.0,
            "nominal_compliance_score": 0.0,
            "pvt_compliance_score": 0.0,
            "has_pvt_coverage": False,
            "measurement_count": 0,
            "failed_metric_count": 0,
            "measurement_names": "",
            "analysis_types": "",
            "stimulus_types": "",
            "elapsed_s": elapsed,
            "error": str(exc),
        }


def main():
    cases = json.loads(CASE_LIST.read_text(encoding="utf-8"))
    llm_client = build_llm_client()

    rows = []
    for case in cases:
        print(f"Running baseline: {case['name']}")
        rows.append(run_case(case, use_llm=False, llm_client=None))

        if llm_client is None:
            rows.append({
                "case": case["name"],
                "mode": "llm",
                "status": "SKIPPED",
                "testbench_generation_success": False,
                "simulation_success": False,
                "overall_verdict": "SKIPPED",
                "success_rate": 0.0,
                "compliance_score": 0.0,
                "nominal_compliance_score": 0.0,
                "pvt_compliance_score": 0.0,
                "has_pvt_coverage": False,
                "measurement_count": 0,
                "failed_metric_count": 0,
                "measurement_names": "",
                "analysis_types": "",
                "stimulus_types": "",
                "elapsed_s": 0.0,
                "error": "LLM provider not configured",
            })
            continue

        print(f"Running llm: {case['name']}")
        rows.append(run_case(case, use_llm=True, llm_client=llm_client))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {"cases": cases, "rows": rows}
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# LLM vs Baseline Comparison",
        "",
        f"- Provider configured: {'yes' if llm_client is not None else 'no'}",
        "",
        "| Case | Mode | Status | Verdict | Success Rate | Compliance | PVT Compliance | Measurements | Failed Metrics | Elapsed (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['mode']} | {row['status']} | {row['overall_verdict']} | "
            f"{row['success_rate']:.2f} | {row['compliance_score']:.2f} | {row['pvt_compliance_score']:.2f} | "
            f"{row['measurement_count']} | {row['failed_metric_count']} | {row['elapsed_s']:.2f} |"
        )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Comparison CSV: {OUT_CSV}")
    print(f"Comparison JSON: {OUT_JSON}")
    print(f"Comparison Markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
