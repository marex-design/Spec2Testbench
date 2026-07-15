import csv
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
ARTIFACTS_DIR = ROOT / "artifacts"
CV_DIR = ROOT / "experiments" / "controlled_violations" / "generated_cases"

FULL_SUITE_SUMMARY = {
    "command": "RUN_NGSPICE_INTEGRATION=1 pytest -q",
    "environment": {
        "RUN_NGSPICE_INTEGRATION": "1",
        "SPEC2TESTBENCH_DISABLE_PYSPICE": "0",
    },
    "tests_collected_or_run": 55,
    "passed": 55,
    "failed": 0,
    "skipped": 0,
    "warnings": 1,
    "duration_seconds": 30.12,
}

NGSPICE_MARK_SUMMARY = {
    "command": "RUN_NGSPICE_INTEGRATION=1 pytest -m ngspice -vv --tb=long",
    "environment": {
        "RUN_NGSPICE_INTEGRATION": "1",
        "SPEC2TESTBENCH_DISABLE_PYSPICE": "0",
    },
    "tests_selected": 5,
    "tests_collected": 55,
    "passed": 5,
    "failed": 0,
    "skipped": 0,
    "warnings": 1,
    "duration_seconds": 19.20,
    "deselected": 50,
}

PYSPICE_DISABLED_SUMMARY = {
    "command": "SPEC2TESTBENCH_DISABLE_PYSPICE=1 RUN_NGSPICE_INTEGRATION=1 pytest -q",
    "environment": {
        "RUN_NGSPICE_INTEGRATION": "1",
        "SPEC2TESTBENCH_DISABLE_PYSPICE": "1",
    },
    "tests_collected_or_run": 55,
    "passed": 55,
    "failed": 0,
    "skipped": 0,
    "warnings": 1,
    "duration_seconds": 25.71,
}

REFERENCE_CASES = [
    {
        "case_id": "ref_p08_currentmirror_dc",
        "circuit_id": "p08_currentmirror",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p08_currentmirror.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p08_currentmirror.cir",
        "metric_name": "quiescent_current",
        "category": "dc_current",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p01_amplifier_gain",
        "circuit_id": "p01_amplifier",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p01_amplifier.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p01_amplifier.cir",
        "metric_name": "dc_gain_db",
        "category": "gain",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p10_lowpass_cutoff",
        "circuit_id": "p10_lowpass",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p10_lowpass.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p10_lowpass.cir",
        "metric_name": "cutoff_frequency_hz",
        "category": "cutoff_frequency",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p22_oscillator_amplitude",
        "circuit_id": "p22_oscillator",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p22_oscillator.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p22_oscillator.cir",
        "metric_name": "startup_amplitude",
        "category": "transient_amplitude",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p22_oscillator_frequency",
        "circuit_id": "p22_oscillator",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p22_oscillator.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p22_oscillator.cir",
        "metric_name": "oscillator_frequency",
        "category": "oscillation_frequency",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p09_comparator_delay",
        "circuit_id": "p09_comparator",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p09_comparator.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p09_comparator.cir",
        "metric_name": "propagation_delay",
        "category": "propagation_delay",
        "expected_outcome": "TRUE_ACCEPT",
    },
    {
        "case_id": "ref_p28_schmitt_threshold",
        "circuit_id": "p28_schmitt",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p28_schmitt.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p28_schmitt.cir",
        "metric_name": "hysteresis_width",
        "category": "switching_threshold",
        "expected_outcome": "TRUE_ACCEPT",
        "custom_spec_metric": {
            "hysteresis_width": {"min": 1e-12, "unit": "V"},
        },
        "custom_test_categories": ["transient", "differential"],
    },
]

PILOT_CASE_IDS = [
    "cv_010_p08_iref_low",
    "cv_025_p06_load_heavy",
    "cv_006_p01_rd_low",
    "cv_001_p10_c_huge",
    "cv_014_p09_input_slow",
    "cv_020_p28_ref_high",
    "cv_017_p22_c_large",
    "cv_019_p22_vdd_low",
]


def main() -> None:
    if os.getenv("SPEC2TESTBENCH_DISABLE_PYSPICE", "").lower() not in {"1", "true", "yes"}:
        raise RuntimeError("Run this script with SPEC2TESTBENCH_DISABLE_PYSPICE=1")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    if pipeline.simulator is None:
        pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    ngspice_version = pipeline.simulator._get_ngspice_version()
    ngspice_path = pipeline.simulator.ngspice_path

    reference_rows = [run_reference_case(pipeline, case) for case in REFERENCE_CASES]
    pilot_rows = [run_pilot_case(pipeline, case_id) for case_id in PILOT_CASE_IDS]

    coverage_rows = []
    for row in reference_rows + pilot_rows:
        coverage_rows.append(
            {
                "case_id": row["case_id"],
                "circuit_id": row["circuit_id"],
                "metric_name": row["metric_name"],
                "analysis_type": row["analysis_type"],
                "backend_requested": row["backend_requested"],
                "backend_used": row["backend_used"],
                "measurement_status": row["measurement_status"],
                "value": row["value"],
                "unit": row["unit"],
                "source_file": row["source_file"],
                "pyspice_used": row["pyspice_used"],
                "paper_eligible": row["paper_eligible"],
            }
        )

    write_csv(RESULTS_DIR / "measurement_backend_coverage_v2.csv", coverage_rows)
    write_csv(RESULTS_DIR / "controlled_violation_native_backend_pilot.csv", pilot_rows)

    results_payload = build_results_payload(
        ngspice_version=ngspice_version,
        ngspice_path=ngspice_path,
        reference_rows=reference_rows,
        pilot_rows=pilot_rows,
        coverage_rows=coverage_rows,
    )
    (RESULTS_DIR / "full_ngspice_native_test_results.json").write_text(
        json.dumps(results_payload, indent=2),
        encoding="utf-8",
    )
    write_reports(results_payload, reference_rows, pilot_rows)


def run_reference_case(pipeline: VerificationPipeline, case: dict[str, Any]) -> dict[str, Any]:
    artifact_dir = ARTIFACTS_DIR / "full_ngspice_native_validation" / case["case_id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report = verify_case(
        pipeline=pipeline,
        spec_path=case["spec_path"],
        netlist_path=case["netlist_path"],
        case_id=case["case_id"],
        parent_circuit_id=case["circuit_id"],
        custom_spec_metric=case.get("custom_spec_metric"),
        custom_test_categories=case.get("custom_test_categories"),
    )
    simulation_results = pipeline.simulator.run(case["netlist_path"], report.testbench)
    return materialize_case_row(
        report=report,
        simulation_results=simulation_results,
        case_id=case["case_id"],
        circuit_id=case["circuit_id"],
        metric_name=case["metric_name"],
        expected_outcome=case["expected_outcome"],
        ground_truth="REFERENCE_COMPLIANT",
        artifact_dir=artifact_dir,
        mutation_effectiveness_status="NOT_APPLICABLE",
    )


def run_pilot_case(pipeline: VerificationPipeline, case_id: str) -> dict[str, Any]:
    case_dir = CV_DIR / case_id
    mutation = json.loads((case_dir / "mutation.json").read_text(encoding="utf-8"))
    artifact_dir = ARTIFACTS_DIR / "controlled_violation_native_backend_pilot" / case_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report = verify_case(
        pipeline=pipeline,
        spec_path=case_dir / "specification.yaml",
        netlist_path=case_dir / "mutated_netlist.cir",
        case_id=case_id,
        parent_circuit_id=mutation["parent_circuit_id"],
    )
    simulation_results = pipeline.simulator.run(case_dir / "mutated_netlist.cir", report.testbench)
    row = materialize_case_row(
        report=report,
        simulation_results=simulation_results,
        case_id=case_id,
        circuit_id=mutation["parent_circuit_id"],
        metric_name=mutation["target_metric"],
        expected_outcome="TRUE_DETECTION",
        ground_truth=mutation["ground_truth_label"],
        artifact_dir=artifact_dir,
        mutation_effectiveness_status=report.mutation_effectiveness_status.value,
    )
    row["mutation_type"] = mutation["mutation_type"]
    row["target_component"] = mutation["target_component"]
    row["original_value"] = mutation["original_value"]
    row["mutated_value_component"] = mutation["mutated_value"]
    return row


def verify_case(
    pipeline: VerificationPipeline,
    spec_path: Path,
    netlist_path: Path,
    case_id: str,
    parent_circuit_id: str,
    custom_spec_metric: Optional[dict[str, Any]] = None,
    custom_test_categories: Optional[list[str]] = None,
):
    if custom_spec_metric:
        specification = Specification.from_yaml(spec_path)
        specification.case_id = case_id
        specification.parent_circuit_id = parent_circuit_id
        specification.performance_targets = custom_spec_metric
        if custom_test_categories is not None:
            specification.test_categories = custom_test_categories
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            yaml.safe_dump(specification.to_dict(), handle, sort_keys=False)
            temp_spec_path = Path(handle.name)
        try:
            return pipeline.verify(specification, netlist_path, spec_path=temp_spec_path)
        finally:
            temp_spec_path.unlink(missing_ok=True)
    return pipeline.verify_from_yaml(spec_path, netlist_path)


def materialize_case_row(
    report: Any,
    simulation_results: dict[str, Any],
    case_id: str,
    circuit_id: str,
    metric_name: str,
    expected_outcome: str,
    ground_truth: str,
    artifact_dir: Path,
    mutation_effectiveness_status: str,
) -> dict[str, Any]:
    metric_trace = next(trace for trace in report.metric_traces if trace.metric_name == metric_name)
    independent_value, independent_backend = compute_independent_value(metric_name, report, simulation_results)
    agreement = independent_value is not None and metric_trace.measured_value is not None and math.isfinite(float(metric_trace.measured_value)) and abs(float(metric_trace.measured_value) - float(independent_value)) <= independent_tolerance(metric_name)
    outcome = classify_outcome(ground_truth, report.compliance_status.value, report.execution_status.value)

    copy_artifacts(report, artifact_dir)
    measurement_source = report.provenance.get("measurement_source", "")
    source_exists = bool(measurement_source and Path(measurement_source).exists())
    finite_value = metric_trace.measured_value is not None and math.isfinite(float(metric_trace.measured_value))

    return {
        "case_id": case_id,
        "circuit_id": circuit_id,
        "metric_name": metric_name,
        "analysis_type": metric_trace.source_analysis,
        "backend_requested": report.provenance.get("measurement_backend", ""),
        "backend_used": report.provenance.get("measurement_backend", ""),
        "measurement_status": report.provenance.get("measurement_status", ""),
        "value": metric_trace.measured_value,
        "unit": metric_trace.unit,
        "source_file": measurement_source,
        "pyspice_used": report.provenance.get("measurement_backend") == "PYSPICE",
        "paper_eligible": report.eligible_for_paper_results,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
        "execution_status": report.execution_status.value,
        "compliance_status": report.compliance_status.value,
        "metric_status": metric_trace.status,
        "metric_value_finite": finite_value,
        "source_artifact_exists": source_exists,
        "independent_value": independent_value,
        "independent_backend": independent_backend,
        "independent_agreement": agreement,
        "netlist_binding_status": report.netlist_binding_status.value,
        "mutation_effectiveness_status": mutation_effectiveness_status,
        "evaluation_outcome": outcome,
        "expected_outcome": expected_outcome,
        "artifact_dir": str(artifact_dir),
        "provenance_file": str(artifact_dir / "provenance.json"),
        "pipeline_metric_file": str(artifact_dir / "pipeline_metric.json"),
    }


def compute_independent_value(metric_name: str, report: Any, simulation_results: dict[str, Any]) -> tuple[Optional[float], str]:
    measurement_source = report.provenance.get("measurement_source")
    source_path = Path(measurement_source) if measurement_source else None
    if metric_name == "quiescent_current":
        value = simulation_results.get("native_metrics", {}).get("quiescent_current")
        if value is None:
            value = simulation_results.get("metrics", {}).get("quiescent_current")
        return as_float(value), "NGSPICE_MEASURE_LINE"
    if metric_name == "dc_gain_db":
        value = simulation_results.get("ac", {}).get("dc_gain_db")
        return as_float(value), "RAW_STRUCTURED_AC"
    if metric_name == "cutoff_frequency_hz":
        value = simulation_results.get("ac", {}).get("bandwidth")
        return as_float(value), "RAW_STRUCTURED_AC"
    if metric_name == "startup_amplitude":
        return parse_measure_numeric_prefix(source_path, "startup_amplitude"), "NGSPICE_MEASURE_LINE"
    if metric_name == "oscillator_frequency":
        value = simulation_results.get("fourier", {}).get("fundamental_frequency")
        return as_float(value), "RAW_STRUCTURED_FFT"
    if metric_name == "propagation_delay":
        return parse_measure_numeric_prefix(source_path, "propagation_delay"), "NGSPICE_MEASURE_LINE"
    if metric_name == "hysteresis_width":
        value = simulation_results.get("native_metrics", {}).get("hysteresis_width_v")
        if value is None:
            value = simulation_results.get("metrics", {}).get("hysteresis_width")
        return as_float(value), "NGSPICE_WRDATA"
    if metric_name == "operating_point":
        return parse_measure_numeric_prefix(source_path, "operating_point"), "NGSPICE_MEASURE_LINE"
    return None, "UNAVAILABLE"


def parse_measure_numeric_prefix(path: Optional[Path], metric_name: str) -> Optional[float]:
    if path is None or not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped.startswith(metric_name):
            continue
        if "=" not in stripped:
            continue
        token = stripped.split("=", 1)[1].strip().split()[0]
        try:
            return float(token)
        except ValueError:
            return None
    return None


def independent_tolerance(metric_name: str) -> float:
    if metric_name == "propagation_delay":
        return 1e-12
    if metric_name in {"quiescent_current", "operating_point", "startup_amplitude", "hysteresis_width"}:
        return 1e-9
    return 1e-6


def copy_artifacts(report: Any, artifact_dir: Path) -> None:
    provenance = dict(report.provenance)
    (artifact_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    for trace in report.metric_traces:
        trace_path = artifact_dir / f"{trace.metric_name}.json"
        trace_path.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    source = provenance.get("measurement_source")
    if source and Path(source).exists():
        src_path = Path(source)
        shutil.copy2(src_path, artifact_dir / src_path.name)
        for sibling_name in ("native_backend.cir", "ngspice_stdout.txt", "ngspice_stderr.txt", "vectors.dat", "vectors.csv", "vector_metadata.json"):
            sibling = src_path.parent / sibling_name
            if sibling.exists():
                shutil.copy2(sibling, artifact_dir / sibling.name)
    raw_file = report.raw_result_file
    if raw_file and Path(raw_file).exists():
        shutil.copy2(Path(raw_file), artifact_dir / Path(raw_file).name)
    if report.testbench:
        (artifact_dir / "testbench.cir").write_text(report.testbench.generate_spice_deck(), encoding="utf-8")
    target_trace = report.metric_traces[0] if report.metric_traces else None
    if target_trace:
        (artifact_dir / "pipeline_metric.json").write_text(json.dumps(target_trace.to_dict(), indent=2), encoding="utf-8")


def classify_outcome(ground_truth: str, compliance_status: str, execution_status: str) -> str:
    if execution_status != "SUCCESS":
        return "UNEVALUATED"
    if ground_truth == "REFERENCE_COMPLIANT":
        return "TRUE_ACCEPT" if compliance_status == "PASS" else "FALSE_REJECT"
    if ground_truth == "GROUND_TRUTH_NONCOMPLIANT":
        return "TRUE_DETECTION" if compliance_status == "FAIL" else "FALSE_ACCEPT" if compliance_status == "PASS" else "UNEVALUATED"
    return "UNEVALUATED"


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def build_results_payload(
    ngspice_version: str,
    ngspice_path: str,
    reference_rows: list[dict[str, Any]],
    pilot_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    real_measurement_categories = {
        row["metric_name"]: {
            "case_id": row["case_id"],
            "simulation_mode": row["simulation_mode"],
            "execution_status": row["execution_status"],
            "backend": row["backend_used"],
            "value": row["value"],
            "unit": row["unit"],
            "source_artifact_exists": row["source_artifact_exists"],
        }
        for row in reference_rows
    }
    all_rows = reference_rows + pilot_rows
    ngspice_measure_cases = sum(1 for row in all_rows if row["backend_used"] == "NGSPICE_MEASURE")
    ngspice_wrdata_cases = sum(1 for row in all_rows if row["backend_used"] == "NGSPICE_WRDATA")
    pyspice_cases = sum(1 for row in all_rows if row["backend_used"] == "PYSPICE")
    independent_total = sum(1 for row in all_rows if row["independent_value"] is not None)
    independent_ok = sum(1 for row in all_rows if row["independent_agreement"])
    pilot_outcomes = count_outcomes(pilot_rows)

    return {
        "ngspice": {
            "path": ngspice_path,
            "version": ngspice_version,
        },
        "full_test_suite": FULL_SUITE_SUMMARY,
        "ngspice_integration_tests": NGSPICE_MARK_SUMMARY,
        "tests_with_pyspice_disabled": PYSPICE_DISABLED_SUMMARY,
        "real_measurement_categories": real_measurement_categories,
        "measurement_backend_coverage": coverage_rows,
        "reference_cases": reference_rows,
        "pilot_cases": pilot_rows,
        "summary": {
            "passed": FULL_SUITE_SUMMARY["passed"] + NGSPICE_MARK_SUMMARY["passed"] + PYSPICE_DISABLED_SUMMARY["passed"],
            "failed": FULL_SUITE_SUMMARY["failed"] + NGSPICE_MARK_SUMMARY["failed"] + PYSPICE_DISABLED_SUMMARY["failed"],
            "skipped": FULL_SUITE_SUMMARY["skipped"] + NGSPICE_MARK_SUMMARY["skipped"] + PYSPICE_DISABLED_SUMMARY["skipped"],
            "warnings": FULL_SUITE_SUMMARY["warnings"] + NGSPICE_MARK_SUMMARY["warnings"] + PYSPICE_DISABLED_SUMMARY["warnings"],
            "ngspice_measure_cases": ngspice_measure_cases,
            "ngspice_wrdata_cases": ngspice_wrdata_cases,
            "pyspice_cases": pyspice_cases,
            "independent_comparisons": independent_total,
            "comparisons_within_tolerance": independent_ok,
            "pilot_cases": len(pilot_rows),
            "pilot_traceable_cases": sum(1 for row in pilot_rows if row["source_artifact_exists"] and row["independent_agreement"]),
            "true_detection": pilot_outcomes["TRUE_DETECTION"],
            "true_accept": count_outcomes(reference_rows)["TRUE_ACCEPT"],
            "false_accept": pilot_outcomes["FALSE_ACCEPT"],
            "false_reject": pilot_outcomes["FALSE_REJECT"],
            "unevaluated": pilot_outcomes["UNEVALUATED"],
        },
    }


def count_outcomes(rows: list[dict[str, Any]]) -> dict[str, int]:
    outcomes = {
        "TRUE_DETECTION": 0,
        "TRUE_ACCEPT": 0,
        "FALSE_ACCEPT": 0,
        "FALSE_REJECT": 0,
        "UNEVALUATED": 0,
    }
    for row in rows:
        outcomes[row["evaluation_outcome"]] = outcomes.get(row["evaluation_outcome"], 0) + 1
    return outcomes


def write_reports(results_payload: dict[str, Any], reference_rows: list[dict[str, Any]], pilot_rows: list[dict[str, Any]]) -> None:
    summary = results_payload["summary"]
    full_lines = [
        "# Full Ngspice Native Test Report",
        "",
        f"- Ngspice path: `{results_payload['ngspice']['path']}`",
        f"- Ngspice version: `{results_payload['ngspice']['version']}`",
        f"- Full suite command: `{FULL_SUITE_SUMMARY['command']}`",
        f"- Full suite result: {FULL_SUITE_SUMMARY['passed']} passed, {FULL_SUITE_SUMMARY['failed']} failed, {FULL_SUITE_SUMMARY['skipped']} skipped, {FULL_SUITE_SUMMARY['warnings']} warning, {FULL_SUITE_SUMMARY['duration_seconds']:.2f}s",
        f"- Ngspice command: `{NGSPICE_MARK_SUMMARY['command']}`",
        f"- Ngspice result: {NGSPICE_MARK_SUMMARY['passed']} passed, {NGSPICE_MARK_SUMMARY['failed']} failed, {NGSPICE_MARK_SUMMARY['skipped']} skipped, {NGSPICE_MARK_SUMMARY['warnings']} warning, {NGSPICE_MARK_SUMMARY['duration_seconds']:.2f}s",
        f"- PySpice disabled command: `{PYSPICE_DISABLED_SUMMARY['command']}`",
        f"- PySpice disabled result: {PYSPICE_DISABLED_SUMMARY['passed']} passed, {PYSPICE_DISABLED_SUMMARY['failed']} failed, {PYSPICE_DISABLED_SUMMARY['skipped']} skipped, {PYSPICE_DISABLED_SUMMARY['warnings']} warning, {PYSPICE_DISABLED_SUMMARY['duration_seconds']:.2f}s",
        "",
        "## Real Measurement Categories",
        "",
        "| Metric | Case | Backend | Value | Unit | Source artifact |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in reference_rows:
        full_lines.append(
            f"| {row['metric_name']} | {row['case_id']} | {row['backend_used']} | {row['value']} | {row['unit']} | {row['source_artifact_exists']} |"
        )
    full_lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- NGSPICE_MEASURE cases: {summary['ngspice_measure_cases']}",
            f"- NGSPICE_WRDATA cases: {summary['ngspice_wrdata_cases']}",
            f"- PYSPICE cases: {summary['pyspice_cases']}",
            f"- Independent comparisons: {summary['independent_comparisons']}",
            f"- Comparisons within tolerance: {summary['comparisons_within_tolerance']}",
        ]
    )

    pilot_lines = [
        "# Controlled Violation Native Backend Pilot",
        "",
        f"- Pilot cases: {len(pilot_rows)}",
        f"- Fully traceable pilot cases: {summary['pilot_traceable_cases']}",
        "",
        "| Case | Metric | Backend | Independent agreement | Binding | Effectiveness | Compliance | Outcome |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in pilot_rows:
        pilot_lines.append(
            f"| {row['case_id']} | {row['metric_name']} | {row['backend_used']} | {row['independent_agreement']} | "
            f"{row['netlist_binding_status']} | {row['mutation_effectiveness_status']} | {row['compliance_status']} | {row['evaluation_outcome']} |"
        )

    (REPORTS_DIR / "full_ngspice_native_test_report.md").write_text(
        "\n".join(full_lines) + "\n",
        encoding="utf-8",
    )
    (REPORTS_DIR / "controlled_violation_native_backend_pilot.md").write_text(
        "\n".join(pilot_lines) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
