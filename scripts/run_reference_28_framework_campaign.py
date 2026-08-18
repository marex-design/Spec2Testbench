import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification


BENCH_DIR = Path("benchmark_reference_28")
SPEC_DIR = Path("examples/reference_28_specs")
OUT_CSV = Path("results/reference_28_framework_campaign.csv")
OUT_MD = Path("results/reference_28_framework_campaign.md")
OUT_JSON = Path("results/reference_28_framework_campaign.json")


def normalize_specification(specification: Specification) -> Specification:
    for _, target in specification.performance_targets.items():
        if not isinstance(target, dict):
            continue
        for bound in ("min", "max", "typ", "weight"):
            if bound in target and isinstance(target[bound], str):
                try:
                    target[bound] = float(target[bound])
                except Exception:
                    pass
    return specification


def main():
    pipeline = VerificationPipeline(use_llm=False)
    rows = []

    for spec_path in sorted(SPEC_DIR.glob("*.yaml")):
        spec = normalize_specification(Specification.from_yaml(spec_path))
        netlist_path = BENCH_DIR / f"{spec_path.stem}.cir"
        print(f"Running framework verify --no-llm: {spec_path.stem}")
        report = pipeline.verify(spec, netlist_path=netlist_path)

        measurement_names = ",".join(measurement.name for measurement in (report.testbench.measurements if report.testbench else []))
        analysis_types = ",".join(analysis.type.value for analysis in (report.testbench.analyses if report.testbench else []))

        rows.append({
            "topology": spec_path.stem,
            "circuit_type": spec.circuit_type.value,
            "analyses": analysis_types,
            "metrics": measurement_names,
            "testbench_generation_success": report.testbench_generation_success,
            "simulation_success": report.simulation_success,
            "overall_verdict": report.overall_verdict.value,
            "success_rate": report.success_rate,
            "compliance_score": report.compliance_score,
            "nominal_compliance_score": report.nominal_compliance_score,
            "pvt_compliance_score": report.pvt_compliance_score,
            "failed_metric_count": len(report.failed_metrics),
            "error": "; ".join(report.errors),
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    lines = [
        "# Reference-28 Framework Campaign",
        "",
        "| Topology | Type | Analyses | Metrics | Verdict | Compliance | Success Rate | Failed Metrics |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['topology']} | {row['circuit_type']} | {row['analyses']} | {row['metrics']} | "
            f"{row['overall_verdict']} | {row['compliance_score']:.2f} | {row['success_rate']:.2f} | {row['failed_metric_count']} |"
        )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"CSV: {OUT_CSV}")
    print(f"JSON: {OUT_JSON}")
    print(f"Markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
