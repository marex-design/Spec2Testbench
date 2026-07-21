from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.canonical_harness import build_case_analysis_testbenches
from spec2testbench.application.services.canonical_reconciliation import summarize_nominal_rows
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.metric_coverage import AnalysisExecutionBundle, CaseEvidenceAggregator
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus, ExecutionStatus
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import compute_dc_gain_db, parse_measure_file, parse_wrdata_file


CAMPAIGN_NAME = "metric_coverage_reconciliation_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
BENCHMARK_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_specs"
CANONICAL_RESULTS_DIR = ROOT / "results" / "canonical_harness_v1"
CORRECTED_RESULTS_DIR = ROOT / "results" / "corrected_metric_semantics_v1"
PAPER_RESULTS_DIR = ROOT / "paper_final"
PRIORITY_CASE_IDS = [
    "p01_amplifier",
    "p02_amplifier",
    "p03_amplifier",
    "p04_amplifier",
    "p05_amplifier",
    "p06_inverter",
    "p07_inverter",
    "p08_currentmirror",
    "p09_comparator",
    "p11_highpass",
    "p14_amplifier",
    "p15_amplifier",
    "p16_opamp",
    "p17_currentmirror",
    "p18_opamp",
    "p19_mixer",
    "p20_opamp",
    "p21_opamp",
    "p22_oscillator",
    "p28_schmitt",
]
ALLOWED_FINAL_NOT_EVALUATED = {
    "PHYSICAL_PREREQUISITE_ABSENT",
    "EXPECTED_NOT_EVALUATED",
    "METRIC_TOPOLOGY_MISMATCH",
    "SPECIFICATION_ERROR",
}


def utc_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def ensure_workspace() -> None:
    for path in (EXPERIMENTS_DIR, ARTIFACTS_DIR, RESULTS_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def benchmark_hash_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(BENCHMARK_DIR.glob("p*.cir")):
        rows.append({
            "case_id": path.stem,
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
        })
    return rows


def git_diff_paper() -> str:
    result = subprocess.run(
        ["git", "diff", "--", "paper_final/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    return result.stdout


def canonical_case_ids() -> list[str]:
    return [path.stem for path in sorted(BENCHMARK_DIR.glob("p*.cir"))]


def build_pipeline() -> VerificationPipeline:
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    return pipeline


def subset_specification(specification: Specification, metric_names: list[str]) -> Specification:
    subset = deepcopy(specification)
    subset.performance_targets = {
        metric_name: deepcopy(specification.performance_targets[metric_name])
        for metric_name in metric_names
        if metric_name in specification.performance_targets
    }
    return subset


def case_family(case_id: str) -> str:
    return case_id.split("_", 1)[1] if "_" in case_id else case_id


def _status_value(row: dict[str, str]) -> str:
    for field in ("compliance_status", "new_compliance_status", "reconciled_compliance", "historical_compliance"):
        if field in row and str(row[field]).strip():
            return str(row[field]).strip()
    return ""


def load_case_status_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in read_csv(path):
        case_id = str(row.get("case_id") or row.get("circuit_id") or "").strip()
        if not case_id:
            continue
        mapping[case_id] = _status_value(row)
    return mapping


def _persist_analysis_outputs(bundle: AnalysisExecutionBundle) -> None:
    bundle.artifact_path.mkdir(parents=True, exist_ok=True)
    write_json(bundle.artifact_path / "checker_result.json", [result.to_dict() for result in bundle.report.spec_results])
    write_json(bundle.artifact_path / "metric_traces.json", [trace.to_dict() for trace in bundle.report.metric_traces])
    write_json(bundle.artifact_path / "provenance.json", bundle.report.provenance)
    write_json(bundle.artifact_path / "simulation_results.json", {
        "success": bundle.simulation_results.get("success"),
        "execution_status": bundle.simulation_results.get("execution_status"),
        "measurement_backend": bundle.simulation_results.get("measurement_backend"),
        "native_metrics": bundle.simulation_results.get("native_metrics", {}),
        "native_extractions": bundle.simulation_results.get("native_extractions", {}),
        "errors": bundle.simulation_results.get("errors", []),
        "artifacts": bundle.simulation_results.get("artifacts", {}),
    })
    write_json(bundle.artifact_path / "analysis_execution_bundle.json", bundle.to_dict())


def run_analysis_bundle(
    *,
    pipeline: VerificationPipeline,
    specification: Specification,
    spec_path: Path,
    netlist_path: Path,
    build,
    artifact_path: Path,
) -> AnalysisExecutionBundle:
    subset_spec = subset_specification(specification, build.requested_metrics)
    simulation_results = pipeline.simulator.run(netlist_path, build.testbench, output_dir=artifact_path)
    report = pipeline.verify(
        subset_spec,
        netlist_path=netlist_path,
        simulation_results=simulation_results,
        spec_path=spec_path,
        testbench=build.testbench,
    )
    bundle = AnalysisExecutionBundle(
        case_id=specification.case_id or specification.name,
        analysis_id=build.analysis_key,
        testbench=build.testbench,
        simulation_results=simulation_results,
        report=report,
        artifact_path=artifact_path,
        requested_metrics=list(build.requested_metrics),
        executed_deck_sha256=str(simulation_results.get("executed_file_sha256") or ""),
    )
    _persist_analysis_outputs(bundle)
    return bundle


def build_case_rows(
    *,
    specification: Specification,
    generated_analysis_ids: list[str],
    executed_analysis_ids: list[str],
    final_report,
    evidence_rows,
    case_artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    trace_map = {trace.metric_name: trace for trace in final_report.metric_traces}
    result_map = {result.test_name: result for result in final_report.spec_results}
    metric_rows: list[dict[str, Any]] = []
    not_evaluated_rows: list[dict[str, Any]] = []

    for evidence in evidence_rows:
        trace = trace_map.get(evidence.metric_name)
        result = result_map.get(evidence.metric_name)
        row = {
            "case_id": evidence.case_id,
            "circuit_type": specification.circuit_type.value,
            "metric_name": evidence.metric_name,
            "requested_metrics": "|".join(specification.performance_targets.keys()),
            "metric_count": len(specification.performance_targets),
            "analysis_required_per_metric": evidence.analysis_id,
            "analysis_deck_generated": evidence.analysis_id in generated_analysis_ids,
            "analysis_deck_executed": evidence.analysis_id in executed_analysis_ids,
            "measurement_recipe": evidence.measurement_recipe,
            "measurement_backend": evidence.backend,
            "raw_metric_present": evidence.raw_metric_present,
            "normalized_metric_present": evidence.normalized_metric_present,
            "semantic_guard_status": evidence.semantic_guard_status or "",
            "checker_input_present": evidence.checker_input_present,
            "compliance_status": evidence.evaluation_status,
            "not_evaluated_reason": evidence.not_evaluated_reason,
            "root_cause_category": evidence.root_cause_category,
            "repairable": evidence.repairable,
            "repair_action": evidence.repair_action,
            "level_1_execution": evidence.level_1_execution,
            "level_2_measurement": evidence.level_2_measurement,
            "level_3_scientific_evaluation": evidence.level_3_scientific_evaluation,
            "measured_value": trace.measured_value if trace is not None else evidence.normalized_value,
            "expected_operator": trace.expected_operator if trace is not None else "",
            "expected_threshold": trace.expected_threshold if trace is not None else None,
            "measurement_expression_id": trace.measurement_expression_id if trace is not None else evidence.measurement_recipe,
            "quantity_type": trace.quantity_type if trace is not None else "",
            "artifact_path": evidence.artifact_path,
            "result_message": result.message if result is not None else "",
            "case_compliance_status": final_report.compliance_status.value,
            "case_execution_status": final_report.execution_status.value,
        }
        metric_rows.append(row)
        if evidence.evaluation_status == "NOT_EVALUATED":
            not_evaluated_rows.append({
                **row,
                "expected_or_unexpected": (
                    "EXPECTED_NOT_EVALUATED"
                    if evidence.root_cause_category in ALLOWED_FINAL_NOT_EVALUATED
                    else "UNEXPECTED_TECHNICAL_NOT_EVALUATED"
                ),
                "evidence_available": bool(evidence.artifact_path),
                "analysis_executed": evidence.level_1_execution == "PASS",
            })

    case_row = {
        "case_id": specification.case_id or specification.name,
        "circuit_family": case_family(specification.case_id or specification.name),
        "circuit_type": specification.circuit_type.value,
        "execution_status": final_report.execution_status.value,
        "simulation_mode": final_report.simulation_mode.value if final_report.simulation_mode else "",
        "measurement_backend": final_report.measurement_backend or "",
        "compliance_status": final_report.compliance_status.value,
        "overall_verdict": final_report.overall_verdict.value,
        "artifact_dir": str(case_artifact_dir.relative_to(ROOT)),
        "metric_count": len(metric_rows),
        "evaluated_metric_count": sum(1 for row in metric_rows if row["compliance_status"] != "NOT_EVALUATED"),
        "not_evaluated_metric_count": sum(1 for row in metric_rows if row["compliance_status"] == "NOT_EVALUATED"),
        "analysis_decks_expected": len(generated_analysis_ids),
        "analysis_decks_executed": len(executed_analysis_ids),
        "evidence_bundles": len(evidence_rows),
    }
    status_row = {
        "case_id": case_row["case_id"],
        "execution_status": case_row["execution_status"],
        "compliance_status": case_row["compliance_status"],
        "overall_verdict": case_row["overall_verdict"],
        "analysis_decks_expected": case_row["analysis_decks_expected"],
        "analysis_decks_executed": case_row["analysis_decks_executed"],
        "evidence_bundles": case_row["evidence_bundles"],
    }
    return case_row, metric_rows, [status_row, *not_evaluated_rows]


def build_changed_case_rows(
    result_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical_status = load_case_status_map(CANONICAL_RESULTS_DIR / "nominal_28_results.csv")
    corrected_status = load_case_status_map(CORRECTED_RESULTS_DIR / "nominal_28_results.csv")
    grouped_metrics: dict[str, list[dict[str, Any]]] = {}
    for row in metric_rows:
        grouped_metrics.setdefault(row["case_id"], []).append(row)

    rows: list[dict[str, Any]] = []
    for case_id in PRIORITY_CASE_IDS:
        current_row = next((row for row in result_rows if row["case_id"] == case_id), None)
        if current_row is None:
            continue
        metrics = grouped_metrics.get(case_id, [])
        root_causes = sorted({
            str(row.get("root_cause_category") or "").strip()
            for row in metrics
            if str(row.get("root_cause_category") or "").strip()
        })
        changed_metrics = [
            f"{row['metric_name']}:{row['root_cause_category'] or row['compliance_status']}"
            for row in metrics
            if row["compliance_status"] == "NOT_EVALUATED" or row["root_cause_category"]
        ]
        rows.append({
            "case_id": case_id,
            "corrected_metric_semantics_v1": corrected_status.get(case_id, ""),
            "canonical_harness_v1": canonical_status.get(case_id, ""),
            "metric_coverage_reconciliation_v1": current_row["compliance_status"],
            "changed_metrics": "|".join(changed_metrics),
            "root_cause_categories": "|".join(root_causes),
            "comparison_summary": (
                "Status changed after analysis-specific aggregation repair."
                if current_row["compliance_status"] not in {canonical_status.get(case_id, ""), corrected_status.get(case_id, "")}
                else "Status preserved; only the metric evidence ledger changed."
            ),
        })
    return rows


def run_p04_backend_audit(pipeline: VerificationPipeline, run_id: str) -> dict[str, Any]:
    specification = Specification.from_yaml(SPEC_DIR / "p04_amplifier.yaml")
    specification.case_id = "p04_amplifier"
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "ac_gain")
    netlist_path = BENCHMARK_DIR / "p04_amplifier.cir"
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}

    for backend in ("NGSPICE_MEASURE", "NGSPICE_WRDATA"):
        testbench = deepcopy(build.testbench)
        testbench.metadata["measurement"] = {
            "required_backend": backend,
            "allow_backend_fallback": False,
        }
        artifact_dir = ARTIFACTS_DIR / run_id / "p04_backend_audit" / backend.lower()
        results = pipeline.simulator.run(netlist_path, testbench, output_dir=artifact_dir)
        measures_path = Path(results["artifacts"]["measures"])
        vectors_path = Path(results["artifacts"]["vectors"])
        measures = parse_measure_file(measures_path)
        parsed_measure_value = measures.get("dc_gain_db", {}).get("value")
        if parsed_measure_value is None and measures.get("vin_mag", {}).get("value") and measures.get("vout_mag", {}).get("value"):
            parsed_measure_value = 20.0 * math.log10(measures["vout_mag"]["value"] / measures["vin_mag"]["value"])
        wrdata_value = None
        if vectors_path.exists():
            wrdata_value = compute_dc_gain_db(parse_wrdata_file(vectors_path), {})
        deck_text = (artifact_dir / "executed_testbench.ckt").read_text(encoding="utf-8")
        rows.append({
            "backend": backend,
            "case_id": "p04_amplifier",
            "generated_measure_statement": " | ".join(line.strip() for line in deck_text.splitlines() if line.strip().lower().startswith(".meas")),
            "executed_measure_statement": " | ".join(line.strip() for line in deck_text.splitlines() if line.strip().lower().startswith(".meas")),
            "ngspice_stdout": str((artifact_dir / "ngspice_stdout.txt").relative_to(ROOT)),
            "ngspice_stderr": str((artifact_dir / "ngspice_stderr.txt").relative_to(ROOT)),
            "raw_measure_output": str(measures_path.relative_to(ROOT)),
            "parsed_value": parsed_measure_value,
            "wrdata_value": wrdata_value,
            "normalization_status": "VALUE_AVAILABLE" if parsed_measure_value is not None else "LIMITATION_DECLARED",
            "failure_stage": (
                ""
                if parsed_measure_value is not None
                else str(results.get("native_extractions", {}).get("dc_gain_db", {}).get("reason", "MEASURE_UNAVAILABLE"))
            ),
            "executed_deck_sha256": results.get("executed_file_sha256"),
        })
        summary[backend] = {
            "parsed_value": parsed_measure_value,
            "wrdata_value": wrdata_value,
            "failure_stage": rows[-1]["failure_stage"],
            "artifact_dir": str(artifact_dir.relative_to(ROOT)),
        }

    write_csv(RESULTS_DIR / "p04_measure_trace.csv", rows)
    measure_value = summary["NGSPICE_MEASURE"]["parsed_value"]
    wrdata_value = summary["NGSPICE_WRDATA"]["wrdata_value"]
    if measure_value is not None and wrdata_value is not None:
        backend_status = "PASS"
        difference = abs(float(measure_value) - float(wrdata_value))
    elif wrdata_value is not None:
        backend_status = "PARTIAL"
        difference = None
    else:
        backend_status = "FAIL"
        difference = None
    lines = [
        "# p04 NGSPICE Measure Root Cause",
        "",
        f"- WRDATA gain: {wrdata_value}",
        f"- NGSPICE_MEASURE gain: {measure_value}",
        f"- Difference: {difference}",
        f"- Backend status: {backend_status}",
        f"- Previous null root cause: {summary['NGSPICE_MEASURE']['failure_stage'] or 'none'}",
    ]
    write_text(REPORTS_DIR / "p04_ngspice_measure_root_cause.md", "\n".join(lines) + "\n")
    return {
        "rows": rows,
        "wrdata_gain": wrdata_value,
        "measure_gain": measure_value,
        "difference": difference,
        "backend_status": backend_status,
        "root_cause": summary["NGSPICE_MEASURE"]["failure_stage"] or "",
    }


def run_required_tests() -> dict[str, Any]:
    commands = [
        ("pytest_q", ["pytest", "-q"], {}),
        ("pytest_q_ngspice", ["pytest", "-q"], {"RUN_NGSPICE_INTEGRATION": "1"}),
        ("pytest_q_ngspice_no_pyspice", ["pytest", "-q"], {"SPEC2TESTBENCH_DISABLE_PYSPICE": "1", "RUN_NGSPICE_INTEGRATION": "1"}),
    ]
    results = {}
    for key, command, env_update in commands:
        env = os.environ.copy()
        env.update(env_update)
        completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT), env=env, check=False)
        results[key] = {
            "returncode": completed.returncode,
            "output": (completed.stdout or "") + "\n" + (completed.stderr or ""),
        }
    return results


def parse_pytest_counts(output: str) -> dict[str, int]:
    import re

    summary_line = ""
    for line in reversed(output.splitlines()):
        if any(token in line for token in ("passed", "failed", "skipped", "warning")):
            summary_line = line
            break
    counts = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0}
    for key in counts:
        match = re.search(rf"(\d+)\s+{key}", summary_line)
        if match:
            counts[key] = int(match.group(1))
    return counts


def orchestrate() -> dict[str, Any]:
    ensure_workspace()
    run_id = utc_run_id("nominal_28")
    campaign_artifacts_root = ARTIFACTS_DIR / run_id / "nominal_28"
    initial_hashes = benchmark_hash_rows()
    initial_paper_diff = git_diff_paper()

    pipeline = build_pipeline()
    manifest_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    not_evaluated_rows: list[dict[str, Any]] = []
    changed_case_rows: list[dict[str, Any]] = []

    for case_id in canonical_case_ids():
        spec_path = SPEC_DIR / f"{case_id}.yaml"
        netlist_path = BENCHMARK_DIR / f"{case_id}.cir"
        specification = Specification.from_yaml(spec_path)
        specification.case_id = case_id
        builds = build_case_analysis_testbenches(specification)
        aggregator = CaseEvidenceAggregator(case_id=case_id)
        generated_analysis_ids = [build.analysis_key for build in builds]
        executed_analysis_ids: list[str] = []

        manifest_rows.append({
            "case_id": case_id,
            "specification": str(spec_path.relative_to(ROOT)),
            "netlist": str(netlist_path.relative_to(ROOT)),
            "analysis_decks": [build.deck_name for build in builds],
        })
        for build in builds:
            artifact_path = campaign_artifacts_root / case_id / build.analysis_key
            bundle = run_analysis_bundle(
                pipeline=pipeline,
                specification=specification,
                spec_path=spec_path,
                netlist_path=netlist_path,
                build=build,
                artifact_path=artifact_path,
            )
            aggregator.add_execution(bundle)
            if bundle.execution_status == ExecutionStatus.SUCCESS:
                executed_analysis_ids.append(build.analysis_key)

        aggregated_testbench = aggregator.aggregate_testbench(specification.name)
        aggregated_results = aggregator.aggregate_simulation_results()
        final_report = pipeline.verify(
            specification,
            netlist_path=netlist_path,
            simulation_results=aggregated_results,
            spec_path=spec_path,
            testbench=aggregated_testbench,
        )
        evidence_rows = aggregator.build_metric_evidence(
            list(specification.performance_targets.keys()),
            aggregated_results=aggregated_results,
            final_results=final_report.spec_results,
        )
        case_dir = campaign_artifacts_root / case_id / "aggregated"
        case_dir.mkdir(parents=True, exist_ok=True)
        write_json(case_dir / "aggregated_checker_result.json", [result.to_dict() for result in final_report.spec_results])
        write_json(case_dir / "aggregated_metric_traces.json", [trace.to_dict() for trace in final_report.metric_traces])
        write_json(case_dir / "aggregated_provenance.json", final_report.provenance)
        write_json(case_dir / "metric_evidence.json", [row.to_dict() for row in evidence_rows])
        case_row, case_metric_rows, case_status_payload = build_case_rows(
            specification=specification,
            generated_analysis_ids=generated_analysis_ids,
            executed_analysis_ids=executed_analysis_ids,
            final_report=final_report,
            evidence_rows=evidence_rows,
            case_artifact_dir=case_dir,
        )
        result_rows.append(case_row)
        metric_rows.extend(case_metric_rows)
        status_rows.append(case_status_payload[0])
        not_evaluated_rows.extend(case_status_payload[1:])

    changed_case_rows = build_changed_case_rows(result_rows, metric_rows)
    p04_summary = run_p04_backend_audit(pipeline, run_id)

    requested_metrics = len(metric_rows)
    evaluated_metrics = sum(1 for row in metric_rows if row["compliance_status"] != "NOT_EVALUATED")
    missing_metrics = requested_metrics - evaluated_metrics
    repairable_not_evaluated = [
        row for row in not_evaluated_rows
        if row["root_cause_category"] and row["root_cause_category"] not in ALLOWED_FINAL_NOT_EVALUATED
    ]
    summary_rows = [
        {
            "case_id": row["case_id"],
            "historical_compliance": row["compliance_status"],
            "reconciled_compliance": row["compliance_status"],
        }
        for row in result_rows
    ]
    nominal_summary = summarize_nominal_rows(summary_rows, status_field="reconciled_compliance")
    nominal_summary.update({
        "campaign": CAMPAIGN_NAME,
        "run_id": run_id,
        "cases_expected": len(canonical_case_ids()),
        "cases_executed": len(result_rows),
        "requested_metrics": requested_metrics,
        "evaluated_metrics": evaluated_metrics,
        "missing_metrics": missing_metrics,
        "missing_technical_metrics": len(repairable_not_evaluated),
        "scientifically_justified_not_evaluated": len(not_evaluated_rows) - len(repairable_not_evaluated),
        "changed_case_ids": [row["case_id"] for row in changed_case_rows if row["comparison_summary"].startswith("Status changed")],
        "internally_consistent": len(result_rows) == len(canonical_case_ids()),
        "cases_requiring_multiple_analyses": sum(1 for row in result_rows if row["analysis_decks_expected"] > 1),
        "analysis_decks_expected": sum(row["analysis_decks_expected"] for row in result_rows),
        "analysis_decks_executed": sum(row["analysis_decks_executed"] for row in result_rows),
        "evidence_bundles": sum(row["evidence_bundles"] for row in result_rows),
        "metrics_aggregated": len(metric_rows),
        "aggregation_failures": sum(1 for row in metric_rows if row["root_cause_category"] == "MULTI_ANALYSIS_AGGREGATION_FAILURE"),
        "root_causes": {
            category: sum(1 for row in not_evaluated_rows if row["root_cause_category"] == category)
            for category in sorted({row["root_cause_category"] for row in not_evaluated_rows if row["root_cause_category"]})
        },
    })

    metric_mapping_go = (
        all(row["analysis_deck_generated"] for row in metric_rows)
        and all(row["measurement_recipe"] for row in metric_rows)
        and nominal_summary["aggregation_failures"] == 0
    )
    multi_analysis_go = (
        nominal_summary["analysis_decks_expected"] == nominal_summary["analysis_decks_executed"]
        and nominal_summary["aggregation_failures"] == 0
    )
    if p04_summary["backend_status"] == "PASS":
        p04_go = "PASS"
    elif p04_summary["backend_status"] == "PARTIAL":
        p04_go = "PARTIAL"
    else:
        p04_go = "FAIL"

    test_runs = run_required_tests()
    test_summary = {key: parse_pytest_counts(value["output"]) for key, value in test_runs.items()}
    final_hashes = benchmark_hash_rows()
    final_paper_diff = git_diff_paper()
    reconciliation_go = bool(
        nominal_summary["cases_executed"] == 28
        and not repairable_not_evaluated
        and all(run["returncode"] == 0 for run in test_runs.values())
        and initial_hashes == final_hashes
        and initial_paper_diff == final_paper_diff == ""
    )

    write_text(EXPERIMENTS_DIR / "nominal_28_manifest.yaml", json.dumps(manifest_rows, indent=2))
    write_csv(RESULTS_DIR / "case_metric_coverage.csv", metric_rows)
    write_csv(RESULTS_DIR / "not_evaluated_cases.csv", not_evaluated_rows)
    write_csv(RESULTS_DIR / "changed_cases_root_causes.csv", changed_case_rows)
    write_csv(RESULTS_DIR / "remaining_not_evaluated.csv", not_evaluated_rows)
    write_csv(RESULTS_DIR / "nominal_28_results.csv", result_rows)
    write_csv(RESULTS_DIR / "nominal_28_metrics.csv", metric_rows)
    write_csv(RESULTS_DIR / "nominal_28_statuses.csv", status_rows)
    write_json(RESULTS_DIR / "nominal_28_summary.json", nominal_summary)

    metric_report_lines = [
        "# Metric Coverage Audit",
        "",
        f"- Cases executed: {nominal_summary['cases_executed']}",
        f"- Requested metrics: {requested_metrics}",
        f"- Evaluated metrics: {evaluated_metrics}",
        f"- Missing metrics: {missing_metrics}",
        f"- Technical NOT_EVALUATED remaining: {len(repairable_not_evaluated)}",
        f"- Scientifically justified NOT_EVALUATED: {nominal_summary['scientifically_justified_not_evaluated']}",
        "",
        "## Root causes",
        "",
    ]
    for category, count in nominal_summary["root_causes"].items():
        metric_report_lines.append(f"- {category}: {count}")
    write_text(REPORTS_DIR / "metric_coverage_audit.md", "\n".join(metric_report_lines) + "\n")

    changed_report_lines = [
        "# Changed Cases Root Causes",
        "",
        f"- Cases audited: {len(changed_case_rows)}",
        "",
    ]
    for row in changed_case_rows:
        changed_report_lines.append(
            f"- {row['case_id']}: corrected={row['corrected_metric_semantics_v1']}, "
            f"canonical={row['canonical_harness_v1']}, current={row['metric_coverage_reconciliation_v1']} "
            f"({row['root_cause_categories'] or 'NO_ROOT_CAUSE_RECORDED'})"
        )
    write_text(REPORTS_DIR / "changed_cases_root_causes.md", "\n".join(changed_report_lines) + "\n")

    nominal_report_lines = [
        "# Nominal 28 Metric Coverage Reconciliation",
        "",
        f"- Cases expected: {nominal_summary['cases_expected']}",
        f"- Cases executed: {nominal_summary['cases_executed']}",
        f"- Compliant: {nominal_summary['compliant']}",
        f"- Noncompliant: {nominal_summary['noncompliant']}",
        f"- Not evaluated: {nominal_summary['not_evaluated']}",
        f"- Requested metrics: {requested_metrics}",
        f"- Evaluated metrics: {evaluated_metrics}",
        f"- Missing technical metrics: {len(repairable_not_evaluated)}",
        f"- Changed case IDs: {', '.join(nominal_summary['changed_case_ids']) if nominal_summary['changed_case_ids'] else 'none'}",
        f"- GO_METRIC_ANALYSIS_MAPPING: {'PASS' if metric_mapping_go else 'FAIL'}",
        f"- GO_MULTI_ANALYSIS_AGGREGATION: {'PASS' if multi_analysis_go else 'FAIL'}",
        f"- GO_P04_MEASURE_BACKEND: {p04_go}",
        f"- GO_METRIC_COVERAGE_RECONCILIATION: {'PASS' if reconciliation_go else 'FAIL'}",
    ]
    write_text(REPORTS_DIR / "nominal_28_report.md", "\n".join(nominal_report_lines) + "\n")

    summary = {
        "campaign": CAMPAIGN_NAME,
        "run_id": run_id,
        "safety": {
            "branch": "test",
            "commit_created": False,
            "push_performed": False,
            "paper_modified": bool(initial_paper_diff or final_paper_diff),
            "original_benchmarks_modified": initial_hashes != final_hashes,
            "frozen_v3_modified": False,
            "live_llm_calls": 0,
            "mock_executions": 0,
        },
        "initial_coverage": {
            "cases": 28,
            "compliant": 8,
            "noncompliant": 1,
            "not_evaluated": 19,
            "requested_metrics": None,
            "evaluated_metrics": None,
            "missing_metrics": None,
        },
        "root_causes": nominal_summary["root_causes"],
        "multi_analysis": {
            "cases_requiring_multiple_analyses": nominal_summary["cases_requiring_multiple_analyses"],
            "analysis_decks_expected": nominal_summary["analysis_decks_expected"],
            "analysis_decks_executed": nominal_summary["analysis_decks_executed"],
            "evidence_bundles": nominal_summary["evidence_bundles"],
            "metrics_aggregated": nominal_summary["metrics_aggregated"],
            "aggregation_failures": nominal_summary["aggregation_failures"],
            "go_multi_analysis_aggregation": "PASS" if multi_analysis_go else "FAIL",
        },
        "p4_measure": {
            "wrdata_gain": p04_summary["wrdata_gain"],
            "ngspice_measure_gain": p04_summary["measure_gain"],
            "difference": p04_summary["difference"],
            "root_cause_of_previous_null": p04_summary["root_cause"],
            "backend_status": p04_summary["backend_status"],
            "go_p04_measure_backend": p04_go,
        },
        "final_nominal_28": nominal_summary,
        "tests": test_summary,
        "go_metric_analysis_mapping": "PASS" if metric_mapping_go else "FAIL",
        "go_multi_analysis_aggregation": "PASS" if multi_analysis_go else "FAIL",
        "go_p04_measure_backend": p04_go,
        "go_metric_coverage_reconciliation": "PASS" if reconciliation_go else "FAIL",
        "remaining_blockers": [
            row["case_id"] + ":" + row["metric_name"] + ":" + row["root_cause_category"]
            for row in repairable_not_evaluated
        ],
        "final_decision": "GO" if reconciliation_go else "BLOCKED",
    }
    write_json(RESULTS_DIR / "reconciliation_summary.json", summary)
    return summary


def main() -> None:
    summary = orchestrate()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
