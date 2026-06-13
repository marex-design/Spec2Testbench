import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.spec_checker.spec_checker import SpecChecker


METRICS_CSV = Path("results/benchmark_campaign_metrics.csv")
SPECS_DIR = Path("examples/benchmark_specs")
OUT_RESULTS_CSV = Path("results/benchmark_spec_results.csv")
OUT_SUMMARY_JSON = Path("results/benchmark_spec_summary.json")
OUT_SUMMARY_MD = Path("results/benchmark_spec_summary.md")


def metric_family(metric_name: str) -> str:
    metric_lower = metric_name.lower()
    if metric_lower.startswith("pvt_"):
        return "pvt"
    if any(token in metric_lower for token in ("dc_gain", "cutoff", "ugbw", "phase_margin", "bandwidth")):
        return "ac"
    if any(token in metric_lower for token in ("thd", "fft", "spectral")):
        return "spectral"
    if any(token in metric_lower for token in ("propagation_delay", "rise_time", "frequency_hz")):
        return "transient"
    if any(token in metric_lower for token in ("vout_dc", "current", "power", "operating_point")):
        return "dc"
    return "other"


def safe_float(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None


def normalize_specification(specification: Specification) -> Specification:
    for metric_name, target in specification.performance_targets.items():
        if not isinstance(target, dict):
            continue
        for bound in ("min", "max", "typ"):
            if bound in target and isinstance(target[bound], str):
                numeric = safe_float(target[bound])
                if numeric is not None:
                    target[bound] = numeric
    return specification


def main():
    rows = list(csv.DictReader(METRICS_CSV.open(encoding="utf-8")))
    rows_by_circuit = {row["circuit"]: row for row in rows}
    checker = SpecChecker()

    result_rows = []
    family_stats = defaultdict(lambda: {"pass": 0, "warning": 0, "fail": 0, "error": 0, "total": 0, "score_sum": 0.0})

    verdict_score = {
        "PASS": 1.0,
        "WARNING": 0.75,
        "FAIL": 0.0,
        "ERROR": 0.0,
        "N/A": 0.0,
    }

    for spec_path in sorted(SPECS_DIR.glob("*.yaml")):
        specification = Specification.from_yaml(spec_path)
        specification = normalize_specification(specification)
        circuit_name = spec_path.stem
        row = rows_by_circuit.get(circuit_name)
        if row is None:
            continue

        for metric_name in specification.performance_targets.keys():
            measured_value = safe_float(row.get(metric_name))
            check = checker.verify_single_metric(metric_name, measured_value, specification)
            family = metric_family(metric_name)
            family_stats[family][check.verdict.value.lower()] += 1
            family_stats[family]["total"] += 1
            family_stats[family]["score_sum"] += verdict_score.get(check.verdict.value, 0.0)
            result_rows.append({
                "circuit": circuit_name,
                "spec_file": spec_path.name,
                "metric": metric_name,
                "family": family,
                "verdict": check.verdict.value,
                "compliance_score": verdict_score.get(check.verdict.value, 0.0),
                "measured_value": "" if check.measured_value is None else check.measured_value,
                "expected_min": "" if check.expected_min is None else check.expected_min,
                "expected_max": "" if check.expected_max is None else check.expected_max,
                "message": check.message,
            })

    with OUT_RESULTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0].keys()))
        writer.writeheader()
        writer.writerows(result_rows)

    summary = {"families": {}}
    for family, stats in sorted(family_stats.items()):
        total = stats["total"] or 1
        summary["families"][family] = {
            **stats,
            "pass_rate": stats["pass"] / total,
            "success_rate": (stats["pass"] + stats["warning"]) / total,
            "compliance_score": stats["score_sum"] / total,
        }

    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Benchmark Spec Summary", ""]
    for family, stats in summary["families"].items():
        lines.extend([
            f"## {family.upper()}",
            "",
            f"- total metrics: {stats['total']}",
            f"- pass: {stats['pass']}",
            f"- warning: {stats['warning']}",
            f"- fail: {stats['fail']}",
            f"- error: {stats['error']}",
            f"- pass rate: {stats['pass_rate']:.1%}",
            f"- success rate: {stats['success_rate']:.1%}",
            f"- compliance score: {stats['compliance_score']:.3f}",
            "",
        ])
    OUT_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Detailed spec results: {OUT_RESULTS_CSV}")
    print(f"Summary JSON: {OUT_SUMMARY_JSON}")
    print(f"Summary Markdown: {OUT_SUMMARY_MD}")


if __name__ == "__main__":
    main()
