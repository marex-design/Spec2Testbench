import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus, MutationEffectivenessStatus


RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
ARTIFACT_ROOT = ROOT / "artifacts" / "controlled_violation_campaign"
CV_DIR = ROOT / "experiments" / "controlled_violations" / "generated_cases"
PAPER_METRICS = RESULTS_DIR / "paper_metric_results.csv"

PILOT_CASES = [
    "cv_001_p10_c_huge",
    "cv_006_p01_rd_low",
    "cv_012_p16_vdd_low",
    "cv_014_p09_input_slow",
    "cv_017_p22_c_large",
    "cv_020_p28_ref_high",
    "cv_023_p05_vdd_high",
    "cv_027_p19_lo_low",
]


def main() -> None:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_v2")
    run_dir = ARTIFACT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    nominal_metrics = load_nominal_metrics()
    cases = load_cases()
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)

    pilot_rows = []
    full_rows = []
    effect_rows = []

    for case in cases:
        row, effect_row = run_case(case, nominal_metrics, pipeline, run_dir)
        full_rows.append(row)
        effect_rows.append(effect_row)
        if case["case_id"] in PILOT_CASES:
            pilot_rows.append(row)

    write_csv(RESULTS_DIR / "controlled_violation_results_v2.csv", full_rows)
    write_csv(RESULTS_DIR / "mutation_effectiveness_v2.csv", effect_rows)

    comparison_rows, baseline_metrics = build_baseline_comparison_v2(full_rows)
    write_csv(RESULTS_DIR / "baseline_vs_spec2testbench_v2.csv", comparison_rows)

    metrics = compute_metrics_v2(full_rows, effect_rows, baseline_metrics)
    (RESULTS_DIR / "controlled_violation_metrics_v2.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_pilot_report(pilot_rows, effect_rows)
    write_campaign_report(metrics, full_rows)
    write_baseline_report_v2(baseline_metrics)
    write_metric_category_report_v2(full_rows, effect_rows)


def load_nominal_metrics() -> dict[tuple[str, str], float]:
    rows = read_csv(PAPER_METRICS)
    return {
        (row["circuit_id"], row["metric_name"]): float(row["measured_value"])
        for row in rows
        if row.get("measured_value") not in {"", None}
    }


def load_cases() -> list[dict[str, Any]]:
    cases = []
    for case_dir in sorted(CV_DIR.iterdir(), key=lambda p: p.name):
        if not case_dir.is_dir():
            continue
        mutation = json.loads((case_dir / "mutation.json").read_text(encoding="utf-8"))
        expected = json.loads((case_dir / "expected_result.json").read_text(encoding="utf-8"))
        cases.append({
            **mutation,
            "expected_result": expected,
            "spec_path": case_dir / "specification.yaml",
            "netlist_path": case_dir / "mutated_netlist.cir",
            "artifact_case_dir": case_dir,
        })
    return cases


def run_case(case: dict[str, Any], nominal_metrics: dict[tuple[str, str], float], pipeline: VerificationPipeline, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    specification = Specification.from_yaml(case["spec_path"])
    specification.case_id = case["case_id"]
    specification.parent_circuit_id = case["parent_circuit_id"]
    report = pipeline.verify(specification, case["netlist_path"], spec_path=case["spec_path"])
    case_dir = run_dir / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "provenance.json").write_text(json.dumps(report.provenance, indent=2), encoding="utf-8")
    (case_dir / "metrics.json").write_text(json.dumps([trace.to_dict() for trace in report.metric_traces], indent=2), encoding="utf-8")
    (case_dir / "testbench.cir").write_text(report.testbench.generate_spice_deck() if report.testbench else "", encoding="utf-8")

    metric_trace = next((trace for trace in report.metric_traces if trace.metric_name == case["target_metric"]), None)
    mutated_value = metric_trace.measured_value if metric_trace else None
    nominal_value = nominal_metrics.get((case["parent_circuit_id"], case["target_metric"]))
    threshold_crossed = threshold_crossed_by_spec(specification, case["target_metric"], mutated_value)
    effectiveness = classify_mutation_effectiveness(nominal_value, mutated_value, threshold_crossed)
    compliance = report.compliance_status.value
    classification = classify_outcome(case["ground_truth_label"], compliance, report.execution_status.value)

    row = {
        "case_id": case["case_id"],
        "parent_circuit_id": case["parent_circuit_id"],
        "circuit_family": case.get("circuit_family", specification.circuit_type.value),
        "mutation_type": case["mutation_type"],
        "target_metric": case["target_metric"],
        "ground_truth_label": case["ground_truth_label"],
        "execution_status": report.execution_status.value,
        "compliance_status": compliance,
        "scientific_category": report.scientific_category.value,
        "netlist_binding_status": report.netlist_binding_status.value,
        "measurement_backend": report.measurement_backend or "UNAVAILABLE",
        "mutation_effectiveness_status": effectiveness.value,
        "threshold_crossed_independently": threshold_crossed,
        "expected_outcome": case["expected_result"]["expected_framework_status"],
        "classification_result": classification,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
        "paper_eligible": report.eligible_for_paper_results,
    }
    effect_row = {
        "case_id": case["case_id"],
        "parent_circuit_id": case["parent_circuit_id"],
        "target_metric": case["target_metric"],
        "nominal_metric_value": nominal_value if nominal_value is not None else "",
        "mutated_metric_value": mutated_value if mutated_value is not None else "",
        "threshold_crossed_independently": threshold_crossed,
        "mutation_effectiveness_status": effectiveness.value,
        "netlist_binding_status": report.netlist_binding_status.value,
    }
    return row, effect_row


def threshold_crossed_by_spec(specification: Specification, metric_name: str, value: Any) -> bool:
    if value is None:
        return False
    target = specification.get_metric(metric_name) or {}
    minimum = target.get("min")
    maximum = target.get("max")
    if minimum is not None and float(value) < float(minimum):
        return True
    if maximum is not None and float(value) > float(maximum):
        return True
    return False


def classify_mutation_effectiveness(nominal_value: Any, mutated_value: Any, threshold_crossed: bool) -> MutationEffectivenessStatus:
    if mutated_value is None:
        return MutationEffectivenessStatus.NOT_EVALUATED
    if nominal_value is None:
        return MutationEffectivenessStatus.NOT_EVALUATED
    delta = abs(float(mutated_value) - float(nominal_value))
    if threshold_crossed:
        return MutationEffectivenessStatus.EFFECTIVE_THRESHOLD_CROSSED
    if delta > max(1e-12, 0.01 * max(abs(float(nominal_value)), 1.0)):
        return MutationEffectivenessStatus.EFFECTIVE_NO_THRESHOLD_CROSSING
    return MutationEffectivenessStatus.NO_MEASURABLE_EFFECT


def classify_outcome(label: str, compliance: str, execution: str) -> str:
    if label == "GROUND_TRUTH_NON_SIMULABLE":
        return "TRUE_NON_SIMULABLE" if execution != "SUCCESS" else "FALSE_SIMULABLE"
    if label == "GROUND_TRUTH_NONCOMPLIANT":
        if compliance == ComplianceStatus.FAIL.value:
            return "TRUE_FAIL"
        if compliance == ComplianceStatus.PASS.value:
            return "FALSE_PASS"
        return "UNEVALUATED"
    return "TRANSPARENT"


def build_baseline_comparison_v2(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    comparison = []
    baseline_false_pass = 0
    spec_false_pass = 0
    effective_total = 0
    for row in rows:
        effective = row["mutation_effectiveness_status"] == MutationEffectivenessStatus.EFFECTIVE_THRESHOLD_CROSSED.value
        if effective and row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT":
            effective_total += 1
        baseline_accept = row["execution_status"] == "SUCCESS"
        spec_accept = row["compliance_status"] == "PASS"
        if effective and baseline_accept and row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT":
            baseline_false_pass += 1
        if effective and spec_accept and row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT":
            spec_false_pass += 1
        comparison.append({
            "case_id": row["case_id"],
            "parent_circuit_id": row["parent_circuit_id"],
            "circuit_family": row["circuit_family"],
            "mutation_type": row["mutation_type"],
            "target_metric": row["target_metric"],
            "ground_truth_label": row["ground_truth_label"],
            "mutation_effectiveness_status": row["mutation_effectiveness_status"],
            "baseline_accept": baseline_accept,
            "spec2testbench_accept": spec_accept,
            "spec2testbench_compliance_status": row["compliance_status"],
            "classification_result": row["classification_result"],
        })
    metrics = {
        "effective_total": effective_total,
        "baseline_false_pass": baseline_false_pass,
        "spec_false_pass": spec_false_pass,
        "baseline_false_pass_rate": safe_ratio(baseline_false_pass, effective_total),
        "spec_false_pass_rate": safe_ratio(spec_false_pass, effective_total),
        "false_pass_reduction": safe_ratio(baseline_false_pass, effective_total) - safe_ratio(spec_false_pass, effective_total),
    }
    return comparison, metrics


def compute_metrics_v2(rows: list[dict[str, Any]], effect_rows: list[dict[str, Any]], baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    effective_rows = [
        row for row in rows
        if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT"
        and row["mutation_effectiveness_status"] == MutationEffectivenessStatus.EFFECTIVE_THRESHOLD_CROSSED.value
    ]
    detected = sum(1 for row in effective_rows if row["compliance_status"] == "FAIL")
    false_pass = sum(1 for row in effective_rows if row["compliance_status"] == "PASS")
    unevaluated = sum(1 for row in effective_rows if row["compliance_status"] == "NOT_EVALUATED")
    by_family = defaultdict(Counter)
    by_metric = defaultdict(Counter)
    for row in effective_rows:
        by_family[row["circuit_family"]][row["classification_result"]] += 1
        by_metric[row["mutation_type"]][row["classification_result"]] += 1
    return {
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "total_variants": len(rows),
        "effective_controlled_violations": len(effective_rows),
        "ineffective_mutations": sum(1 for row in effect_rows if row["mutation_effectiveness_status"] != MutationEffectivenessStatus.EFFECTIVE_THRESHOLD_CROSSED.value),
        "netlist_binding_mismatches": sum(1 for row in rows if row["netlist_binding_status"] != "MATCH"),
        "detected_effective_violations": detected,
        "false_pass": false_pass,
        "not_evaluated": unevaluated,
        "violation_detection_recall": safe_ratio(detected, len(effective_rows)),
        "false_pass_rate": safe_ratio(false_pass, len(effective_rows)),
        "precision": safe_ratio(detected, detected + false_pass),
        "f1_score": safe_ratio(2 * detected, (2 * detected) + false_pass + unevaluated),
        "decision_coverage": safe_ratio(detected + false_pass, len(effective_rows)),
        "unevaluated_rate": safe_ratio(unevaluated, len(effective_rows)),
        "baseline_false_pass_rate": baseline_metrics["baseline_false_pass_rate"],
        "false_pass_reduction": baseline_metrics["false_pass_reduction"],
        "by_family": {key: dict(value) for key, value in by_family.items()},
        "by_metric_category": {key: dict(value) for key, value in by_metric.items()},
    }


def write_pilot_report(pilot_rows: list[dict[str, Any]], effect_rows: list[dict[str, Any]]) -> None:
    effects = {row["case_id"]: row for row in effect_rows}
    lines = [
        "# Controlled Violation Pilot Report",
        "",
        f"- Pilot cases: {len(pilot_rows)}",
        "",
        "| Case | Binding | Effectiveness | Threshold crossed | Compliance | Classification |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in pilot_rows:
        effect = effects[row["case_id"]]
        lines.append(
            f"| {row['case_id']} | {row['netlist_binding_status']} | {row['mutation_effectiveness_status']} | "
            f"{effect['threshold_crossed_independently']} | {row['compliance_status']} | {row['classification_result']} |"
        )
    (REPORTS_DIR / "controlled_violation_pilot_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_campaign_report(metrics: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Controlled Violation Campaign Report V2",
        "",
        f"Total variants: {metrics['total_variants']}",
        f"Effective controlled violations: {metrics['effective_controlled_violations']}",
        f"Ineffective mutations: {metrics['ineffective_mutations']}",
        f"Netlist binding mismatches: {metrics['netlist_binding_mismatches']}",
        f"Detected effective violations: {metrics['detected_effective_violations']}",
        f"False PASS: {metrics['false_pass']}",
        f"Not evaluated: {metrics['not_evaluated']}",
        f"Violation detection recall: {metrics['violation_detection_recall']:.4f}",
        f"False-PASS rate: {metrics['false_pass_rate']:.4f}",
        f"Baseline false-PASS rate: {metrics['baseline_false_pass_rate']:.4f}",
        f"False-PASS reduction: {metrics['false_pass_reduction']:.4f}",
        f"Metric categories effectively evaluated: {len(metrics['by_metric_category'])}",
        "",
        "| Case | Compliance | Binding | Effectiveness | Classification |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['compliance_status']} | {row['netlist_binding_status']} | "
            f"{row['mutation_effectiveness_status']} | {row['classification_result']} |"
        )
    (REPORTS_DIR / "controlled_violation_campaign_report_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_baseline_report_v2(metrics: dict[str, Any]) -> None:
    lines = [
        "# Simulability Baseline Report V2",
        "",
        f"- Effective violations considered: {metrics['effective_total']}",
        f"- Baseline false-PASS rate: {metrics['baseline_false_pass_rate']:.4f}",
        f"- Spec2Testbench false-PASS rate: {metrics['spec_false_pass_rate']:.4f}",
        f"- False-PASS reduction: {metrics['false_pass_reduction']:.4f}",
    ]
    (REPORTS_DIR / "simulability_baseline_report_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_metric_category_report_v2(rows: list[dict[str, Any]], effect_rows: list[dict[str, Any]]) -> None:
    represented = sorted({row["mutation_type"] for row in rows})
    effective = sorted({row["mutation_type"] for row in rows if row["mutation_effectiveness_status"] == MutationEffectivenessStatus.EFFECTIVE_THRESHOLD_CROSSED.value})
    lines = [
        "# Metric Category Evaluation V2",
        "",
        f"- Implemented categories: {', '.join(represented)}",
        f"- Categories with effective violations: {', '.join(effective) if effective else 'none'}",
    ]
    (REPORTS_DIR / "metric_category_evaluation_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


if __name__ == "__main__":
    main()
