import argparse
import csv
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PER_CIRCUIT_CSV = ROOT / "results" / "acp28_campaign_matrix" / "campaign_per_circuit.csv"
ROBUST_RESULTS_DIR = ROOT / "results" / "acp28_campaign_matrix" / "robust"
ROBUST_SPECS_DIR = ROOT / "examples" / "benchmark_robust_specs"
OUT_CSV = ROOT / "results" / "acp28_campaign_matrix" / "robust_fail_audit.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Audit ACP28 robust campaign failures.")
    parser.add_argument("--per-circuit-csv", type=Path, default=PER_CIRCUIT_CSV)
    parser.add_argument("--results-dir", type=Path, default=ROBUST_RESULTS_DIR)
    parser.add_argument("--spec-dir", type=Path, default=ROBUST_SPECS_DIR)
    parser.add_argument("--output-csv", type=Path, default=OUT_CSV)
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_report_path(raw_path: str) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    return path


def latest_report_path(results_dir: Path, circuit: str) -> Path | None:
    report_dir = results_dir / circuit / "reports"
    candidates = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def expected_range(metric: dict) -> str:
    expected_min = metric.get("expected_min")
    expected_max = metric.get("expected_max")
    unit = metric.get("unit", "")
    if expected_min is not None and expected_max is not None:
        return f"[{expected_min}, {expected_max}] {unit}".strip()
    if expected_min is not None:
        return f">= {expected_min} {unit}".strip()
    if expected_max is not None:
        return f"<= {expected_max} {unit}".strip()
    return "unspecified"


def classify_failure(report: dict, metric_rows: list[dict], missing_metrics: list[str], failed_metrics: list[str]) -> str:
    if report.get("failure_kind"):
        return str(report["failure_kind"])
    if report.get("errors") or not report.get("testbench_generation_success", True):
        return "testbench_generation_failed"
    if not report.get("simulation_success", True):
        return "simulation_not_successful"
    if missing_metrics:
        first_missing = next((metric for metric in metric_rows if metric.get("name") in missing_metrics), None)
        if first_missing:
            message = str(first_missing.get("message", ""))
            prefix = message.split(":", 1)[0].strip().lower()
            if prefix and prefix != message.lower():
                return prefix
        return "metric_missing"
    if failed_metrics:
        return "metric_out_of_spec"
    return "unknown_failure"


def root_cause_guess(failure_kind: str, missing_metrics: list[str], failed_metrics: list[str]) -> str:
    all_problem_metrics = [*missing_metrics, *failed_metrics]
    if failure_kind in {"metric_missing", "no_waveform_data"}:
        if all_problem_metrics and all(name.startswith("pvt_") for name in all_problem_metrics):
            return "pvt_extraction_gap"
        return "metric_extraction_gap"
    if failure_kind == "simulation_not_successful":
        return "simulation_failure"
    if failure_kind == "testbench_generation_failed":
        return "testbench_generation_failure"
    if failure_kind == "metric_out_of_spec":
        if all_problem_metrics and all(name.startswith("pvt_") for name in all_problem_metrics):
            return "pvt_variation_above_threshold"
        return "nominal_metric_out_of_spec"
    return "manual_review_needed"


def recommended_fix(root_cause: str, missing_metrics: list[str], failed_metrics: list[str]) -> str:
    metric_list = ", ".join(missing_metrics or failed_metrics)
    if root_cause == "pvt_extraction_gap":
        return f"Implement or wire robust PVT extraction for {metric_list} in simulator results and spec checker."
    if root_cause == "metric_extraction_gap":
        return f"Add extractor or alias coverage for {metric_list} and verify the generated analyses expose the needed data."
    if root_cause == "simulation_failure":
        return "Inspect ngspice logs, convergence setup, and generated testbench stimuli for this circuit."
    if root_cause == "testbench_generation_failure":
        return "Fix testbench generation inputs or unsupported analysis configuration before rerunning the robust campaign."
    if root_cause == "pvt_variation_above_threshold":
        return f"Review the robust limit for {metric_list} and confirm whether the measured PVT spread is physically expected."
    if root_cause == "nominal_metric_out_of_spec":
        return f"Inspect nominal extraction and circuit behavior for {metric_list}; the robust campaign is failing on a measured limit."
    return "Review the report JSON manually and refine the failure taxonomy for this case."


def build_audit_row(circuit_row: dict, report: dict, spec_data: dict) -> dict:
    metric_rows = report.get("metrics", [])
    target_metrics = list((spec_data.get("performance_targets") or {}).keys())
    metrics_by_name = {metric.get("name"): metric for metric in metric_rows}

    missing_metrics = [
        metric_name
        for metric_name in target_metrics
        if metrics_by_name.get(metric_name, {}).get("verdict") == "ERROR"
    ]
    failed_metrics = [
        metric_name
        for metric_name in target_metrics
        if metrics_by_name.get(metric_name, {}).get("verdict") == "FAIL"
    ]

    measured_values = []
    expected_ranges = []
    for metric_name in target_metrics:
        metric = metrics_by_name.get(metric_name, {})
        measured = metric.get("measured")
        measured_values.append(f"{metric_name}={measured if measured is not None else 'N/A'}")
        expected_ranges.append(f"{metric_name}:{expected_range(metric)}")

    failure_kind = classify_failure(report, metric_rows, missing_metrics, failed_metrics)
    root_cause = root_cause_guess(failure_kind, missing_metrics, failed_metrics)

    return {
        "circuit": circuit_row["circuit"],
        "circuit_type": circuit_row["circuit_type"],
        "overall_verdict": report.get("terminal_status", report.get("overall_verdict", circuit_row.get("overall_verdict", ""))),
        "failure_kind": failure_kind,
        "failed_metric_names": ", ".join(failed_metrics),
        "missing_metric_names": ", ".join(missing_metrics),
        "measured_values": "; ".join(measured_values),
        "expected_ranges": "; ".join(expected_ranges),
        "root_cause_guess": root_cause,
        "recommended_fix": recommended_fix(root_cause, missing_metrics, failed_metrics),
    }


def load_circuit_index(rows: list[dict]) -> dict[str, dict]:
    index = {}
    for row in rows:
        circuit = row.get("circuit")
        if circuit and circuit not in index:
            index[circuit] = row
    return index


def find_robust_report_paths(results_dir: Path) -> list[Path]:
    return sorted(results_dir.glob("*/reports/*.json"))


def main():
    args = parse_args()
    rows = load_rows(args.per_circuit_csv)
    circuit_index = load_circuit_index(rows)
    report_paths = find_robust_report_paths(args.results_dir)

    audit_rows = []
    for report_path in report_paths:
        report = load_json(report_path)
        overall_verdict = report.get("terminal_status", report.get("overall_verdict", ""))
        if overall_verdict != "FAIL":
            continue

        circuit = report_path.parent.parent.name
        circuit_row = circuit_index.get(circuit, {"circuit": circuit, "circuit_type": ""})
        spec_path = args.spec_dir / f"{circuit}.yaml"
        if not spec_path.exists():
            raise FileNotFoundError(f"Missing robust spec for {circuit}: {spec_path}")

        spec_data = load_yaml(spec_path)
        audit_rows.append(build_audit_row(circuit_row, report, spec_data))

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "circuit",
        "circuit_type",
        "overall_verdict",
        "failure_kind",
        "failed_metric_names",
        "missing_metric_names",
        "measured_values",
        "expected_ranges",
        "root_cause_guess",
        "recommended_fix",
    ]
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)

    print(f"Robust FAIL audit CSV: {args.output_csv}")
    print(f"Audited circuits: {len(audit_rows)}")


if __name__ == "__main__":
    main()
