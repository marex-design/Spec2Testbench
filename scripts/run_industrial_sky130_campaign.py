import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification


SPEC_DIR = ROOT / "benchmark" / "industrial" / "specs"
NETLIST_DIR = ROOT / "benchmark" / "industrial" / "netlists"
MODEL_BRIDGE = ROOT / "benchmark" / "industrial" / "models" / "sky130_tt.spice"
OUT_CSV = ROOT / "results" / "industrial_sky130_campaign.csv"
OUT_JSON = ROOT / "results" / "industrial_sky130_campaign.json"
OUT_MD = ROOT / "results" / "industrial_sky130_campaign.md"


def model_bridge_ready() -> tuple[bool, str]:
    if not MODEL_BRIDGE.exists():
        return False, f"Missing model bridge: {MODEL_BRIDGE}"
    text = MODEL_BRIDGE.read_text(encoding="utf-8", errors="ignore")
    if "__REPLACE_WITH_LOCAL_SKY130_LIB__" in text:
        return False, "Edit benchmark/industrial/models/sky130_tt.spice with a local SKY130 .lib path before running."
    return True, ""


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
    ready, message = model_bridge_ready()
    if not ready:
        print(f"Industrial SKY130 campaign blocked: {message}")
        return

    pipeline = VerificationPipeline(use_llm=False)
    rows = []

    for spec_path in sorted(SPEC_DIR.glob("ind*.yaml")):
        spec = normalize_specification(Specification.from_yaml(spec_path))
        netlist_path = NETLIST_DIR / f"{spec_path.stem}.cir"
        print(f"[industrial-sky130] {spec_path.stem}")
        report = pipeline.verify(spec, netlist_path=netlist_path)

        rows.append(
            {
                "case": spec_path.stem,
                "circuit_type": spec.circuit_type.value,
                "testbench_generation_success": report.testbench_generation_success,
                "simulation_success": report.simulation_success,
                "overall_verdict": report.overall_verdict.value,
                "success_rate": report.success_rate,
                "compliance_score": report.compliance_score,
                "nominal_compliance_score": report.nominal_compliance_score,
                "pvt_compliance_score": report.pvt_compliance_score,
                "measurement_count": len(report.testbench.measurements) if report.testbench else 0,
                "failed_metric_count": len(report.failed_metrics),
                "error": "; ".join(report.errors),
            }
        )

    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    lines = [
        "# SKY130 Industrial Campaign",
        "",
        f"- Cases: {len(rows)}",
        "",
        "| Case | Type | Generated | Simulated | Verdict | Compliance | Failed Metrics |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['circuit_type']} | {row['testbench_generation_success']} | "
            f"{row['simulation_success']} | {row['overall_verdict']} | {row['compliance_score']:.2f} | "
            f"{row['failed_metric_count']} |"
        )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print("Industrial SKY130 campaign complete.")
    print(f"CSV report: {OUT_CSV}")
    print(f"JSON report: {OUT_JSON}")
    print(f"Markdown report: {OUT_MD}")


if __name__ == "__main__":
    main()
