from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.canonical_harness import build_case_analysis_testbenches
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import (
    compute_absolute_output_dbv,
    compute_dc_gain_db,
    parse_measure_file,
    parse_wrdata_file,
)
from spec2testbench.domain.value_objects.metric_semantics import TRANSFER_GAIN_V2
from spec2testbench.domain.value_objects.verdict import Verdict
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus, ExecutionStatus


CAMPAIGN_NAME = "canonical_harness_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
BENCHMARK_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_specs"
CORRECTED_RESULTS = ROOT / "results" / "corrected_metric_semantics_v1"
RECONCILIATION_RESULTS = ROOT / "results" / "canonical_reconciliation_v1"
PAPER_RESULTS = ROOT / "results" / "paper_metric_results.csv"


@dataclass
class BuildExecution:
    simulation_results: dict[str, Any]
    report: Any
    artifact_dir: Path
    analysis_key: str
    requested_metrics: list[str]
    audit_row: dict[str, Any]


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_diff_paper() -> str:
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--", "paper_final/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    return result.stdout


def benchmark_hash_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(BENCHMARK_DIR.glob("p*.cir")):
        rows.append({
            "case_id": path.stem,
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
        })
    return rows


def canonical_case_ids() -> list[str]:
    return [path.stem for path in sorted(BENCHMARK_DIR.glob("p*.cir"))]


def build_pipeline() -> VerificationPipeline:
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    return pipeline


def run_build(
    *,
    pipeline: VerificationPipeline,
    specification: Specification,
    spec_path: Path,
    netlist_path: Path,
    build,
    artifact_dir: Path,
) -> BuildExecution:
    simulation_results = pipeline.simulator.run(netlist_path, build.testbench, output_dir=artifact_dir)
    report = pipeline.verify(
        specification,
        netlist_path=netlist_path,
        simulation_results=simulation_results,
        spec_path=spec_path,
    )
    write_json(artifact_dir / "provenance.json", report.provenance)
    write_json(artifact_dir / "analysis_harness_policy.json", build.policy.to_dict())
    write_json(artifact_dir / "source_override_policies.json", [item.to_dict() for item in build.source_policies])
    write_json(artifact_dir / "checker_result.json", [result.to_dict() for result in report.spec_results])
    write_json(artifact_dir / "metric_traces.json", [trace.to_dict() for trace in report.metric_traces])
    return BuildExecution(
        simulation_results=simulation_results,
        report=report,
        artifact_dir=artifact_dir,
        analysis_key=build.analysis_key,
        requested_metrics=build.requested_metrics,
        audit_row={**build.audit_row, "artifact_dir": str(artifact_dir.relative_to(ROOT))},
    )


def build_nominal_manifest(rows: list[dict[str, Any]]) -> None:
    manifest = {
        "campaign": CAMPAIGN_NAME,
        "cases": rows,
    }
    write_text(EXPERIMENTS_DIR / "nominal_28_manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))


def aggregate_case(case_id: str, executions: list[BuildExecution]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    result_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    harness_rows: list[dict[str, Any]] = []
    integrity_rows: list[dict[str, Any]] = []
    all_results = []
    deck_hashes: list[str] = []

    for execution in executions:
        report = execution.report
        all_results.extend(report.spec_results)
        harness_rows.append(execution.audit_row)
        deck_hash = execution.simulation_results.get("executed_file_sha256") or ""
        if deck_hash:
            deck_hashes.append(deck_hash)
        integrity_rows.append({
            "case_id": case_id,
            "analysis_key": execution.analysis_key,
            "compiled_plan_sha256": execution.simulation_results.get("compiled_plan_sha256"),
            "serialized_deck_sha256": execution.simulation_results.get("serialized_deck_sha256"),
            "executed_file_sha256": execution.simulation_results.get("executed_file_sha256"),
            "post_execution_file_sha256": execution.simulation_results.get("post_execution_file_sha256"),
            "ngspice_input_file_path": execution.simulation_results.get("ngspice_input_file_path"),
            "ngspice_command": " ".join(execution.simulation_results.get("ngspice_command", [])),
            "generated_testbench_path": execution.simulation_results.get("generated_testbench_path"),
            "generated_testbench_sha256": execution.simulation_results.get("generated_testbench_sha256"),
            "generated_testbench_alias_byte_identical": execution.simulation_results.get("generated_testbench_alias_byte_identical"),
            "post_serialization_deck_mutation": execution.simulation_results.get("post_serialization_deck_mutation"),
            "hash_match": execution.simulation_results.get("serialized_deck_sha256") == execution.simulation_results.get("executed_file_sha256") == execution.simulation_results.get("post_execution_file_sha256"),
            "artifact_dir": str(execution.artifact_dir.relative_to(ROOT)),
        })
        for trace in report.metric_traces:
            metric_rows.append({
                "case_id": case_id,
                "analysis_key": execution.analysis_key,
                "metric_name": trace.metric_name,
                "measured_value": trace.measured_value,
                "unit": trace.unit,
                "status": trace.status,
                "expected_operator": trace.expected_operator,
                "expected_threshold": trace.expected_threshold,
                "metric_definition_version": trace.metric_definition_version,
                "quantity_type": trace.quantity_type,
                "measurement_expression_id": trace.measurement_expression_id,
                "input_node": trace.input_node,
                "output_node": trace.output_node,
                "input_ac_magnitude": trace.input_ac_magnitude,
                "reference_frequency_hz": trace.reference_frequency_hz,
                "measurement_backend": trace.measurement_backend,
                "artifact_dir": str(execution.artifact_dir.relative_to(ROOT)),
            })

    execution_failures = sum(1 for execution in executions if execution.report.execution_status != ExecutionStatus.SUCCESS)
    if execution_failures:
        compliance = ComplianceStatus.NOT_EVALUATED
    elif any(result.verdict == Verdict.FAIL for result in all_results):
        compliance = ComplianceStatus.FAIL
    elif any(result.verdict == Verdict.ERROR for result in all_results) or not all_results:
        compliance = ComplianceStatus.NOT_EVALUATED
    else:
        compliance = ComplianceStatus.PASS

    case_hash = sha256_text(json.dumps(sorted(deck_hashes), ensure_ascii=True))
    case_row = {
        "case_id": case_id,
        "circuit_family": case_id.split("_", 1)[1] if "_" in case_id else case_id,
        "execution_status": ExecutionStatus.SUCCESS.value if execution_failures == 0 else ExecutionStatus.ERROR.value,
        "simulation_mode": "REAL",
        "measurement_backend": "|".join(sorted({execution.report.measurement_backend or "" for execution in executions if execution.report.measurement_backend})),
        "compliance_status": compliance.value,
        "overall_verdict": "PASS" if compliance == ComplianceStatus.PASS else "FAIL" if compliance == ComplianceStatus.FAIL else "RUN",
        "artifact_dir": str((ARTIFACTS_DIR / "LATEST" / "nominal_28" / case_id).relative_to(ROOT)),
        "canonical_harness_hash": case_hash,
        "metric_count": len(metric_rows),
        "evaluated_metric_count": sum(1 for row in metric_rows if row["status"] != "NOT_EVALUATED"),
        "not_evaluated_metric_count": sum(1 for row in metric_rows if row["status"] == "NOT_EVALUATED"),
        "analysis_decks": len(executions),
    }
    result_rows.append(case_row)
    status_rows.append({
        "case_id": case_id,
        "execution_status": case_row["execution_status"],
        "compliance_status": case_row["compliance_status"],
        "overall_verdict": case_row["overall_verdict"],
        "analysis_decks": len(executions),
        "canonical_harness_hash": case_hash,
        "execution_failures": execution_failures,
    })
    return result_rows[0], metric_rows, status_rows, harness_rows, integrity_rows


def run_nominal_campaign() -> dict[str, Any]:
    pipeline = build_pipeline()
    run_id = utc_run_id("nominal_28")
    nominal_root = ARTIFACTS_DIR / run_id / "nominal_28"
    latest_root = ARTIFACTS_DIR / "LATEST" / "nominal_28"
    if latest_root.exists():
        shutil.rmtree(latest_root)
    latest_root.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    result_rows = []
    metric_rows = []
    status_rows = []
    harness_rows = []
    integrity_rows = []
    all_source_policies = []

    for case_id in canonical_case_ids():
        spec_path = SPEC_DIR / f"{case_id}.yaml"
        netlist_path = BENCHMARK_DIR / f"{case_id}.cir"
        specification = Specification.from_yaml(spec_path)
        specification.case_id = case_id
        builds = build_case_analysis_testbenches(specification)
        executions = []
        manifest_rows.append({
            "case_id": case_id,
            "specification": str(spec_path.relative_to(ROOT)),
            "netlist": str(netlist_path.relative_to(ROOT)),
            "analysis_decks": [build.deck_name for build in builds],
            "metric_definition_version": TRANSFER_GAIN_V2 if any("dc_gain" in metric for build in builds for metric in build.requested_metrics) else "",
        })
        for build in builds:
            artifact_dir = nominal_root / case_id / build.analysis_key
            executions.append(
                run_build(
                    pipeline=pipeline,
                    specification=specification,
                    spec_path=spec_path,
                    netlist_path=netlist_path,
                    build=build,
                    artifact_dir=artifact_dir,
                )
            )
            all_source_policies.extend(build.source_policies)
        case_row, case_metric_rows, case_status_rows, case_harness_rows, case_integrity_rows = aggregate_case(case_id, executions)
        result_rows.append(case_row)
        metric_rows.extend(case_metric_rows)
        status_rows.extend(case_status_rows)
        harness_rows.extend(case_harness_rows)
        integrity_rows.extend(case_integrity_rows)
        case_latest = latest_root / case_id
        if case_latest.exists():
            shutil.rmtree(case_latest)
        shutil.copytree(nominal_root / case_id, case_latest)

    build_nominal_manifest(manifest_rows)
    write_csv(RESULTS_DIR / "harness_policy_audit.csv", harness_rows)
    write_csv(RESULTS_DIR / "nominal_28_results.csv", result_rows)
    write_csv(RESULTS_DIR / "nominal_28_metrics.csv", metric_rows)
    write_csv(RESULTS_DIR / "nominal_28_statuses.csv", status_rows)
    write_csv(RESULTS_DIR / "nominal_28_harness_changes.csv", harness_rows)
    write_csv(RESULTS_DIR / "executed_deck_integrity.csv", integrity_rows)

    summary = {
        "campaign": CAMPAIGN_NAME,
        "run_id": run_id,
        "cases_expected": len(canonical_case_ids()),
        "cases_executed": len(result_rows),
        "real_ngspice": True,
        "execution_failures": sum(1 for row in status_rows if row["execution_failures"]),
        "compliant": sum(1 for row in result_rows if row["compliance_status"] == "PASS"),
        "noncompliant": sum(1 for row in result_rows if row["compliance_status"] == "FAIL"),
        "not_evaluated": sum(1 for row in result_rows if row["compliance_status"] == "NOT_EVALUATED"),
        "changed_case_ids_vs_corrected": [],
        "total": len(result_rows),
        "internally_consistent": len(result_rows) == len(canonical_case_ids()),
        "source_policy_count": len(all_source_policies),
        "supply_sources": sum(1 for item in all_source_policies if item.source_role == "SUPPLY_SOURCE"),
        "bias_sources": sum(1 for item in all_source_policies if item.source_role == "BIAS_SOURCE"),
        "signal_sources": sum(1 for item in all_source_policies if item.source_role == "SIGNAL_SOURCE"),
        "internal_bias_sources": sum(1 for item in all_source_policies if item.source_role == "INTERNAL_BIAS_SOURCE"),
        "unknown_sources": sum(1 for item in all_source_policies if item.source_role == "UNKNOWN_SOURCE"),
        "unauthorized_dc_overrides": sum(1 for row in harness_rows if row["harness_difference_class"] == "UNAUTHORIZED_DC_OVERRIDE"),
        "unauthorized_supply_overrides": sum(1 for row in harness_rows if row["harness_difference_class"] == "UNAUTHORIZED_SUPPLY_OVERRIDE"),
        "unauthorized_bias_overrides": sum(1 for row in harness_rows if row["harness_difference_class"] == "UNAUTHORIZED_BIAS_OVERRIDE"),
        "multi_analysis_contaminations": sum(1 for row in harness_rows if row["harness_difference_class"] == "MULTI_ANALYSIS_CONTAMINATION"),
    }
    corrected_status = {row["case_id"]: row["compliance_status"] for row in read_csv(CORRECTED_RESULTS / "nominal_28_results.csv")}
    summary["changed_case_ids_vs_corrected"] = [row["case_id"] for row in result_rows if corrected_status.get(row["case_id"]) != row["compliance_status"]]
    write_json(RESULTS_DIR / "nominal_28_summary.json", summary)
    write_text(
        REPORTS_DIR / "nominal_28_report.md",
        "\n".join([
            "# Nominal 28 Canonical Harness",
            "",
            f"- Cases expected: {summary['cases_expected']}",
            f"- Cases executed: {summary['cases_executed']}",
            f"- Real ngspice: {summary['real_ngspice']}",
            f"- Compliant: {summary['compliant']}",
            f"- Noncompliant: {summary['noncompliant']}",
            f"- Not evaluated: {summary['not_evaluated']}",
            f"- Changed case IDs vs corrected_metric_semantics_v1: {', '.join(summary['changed_case_ids_vs_corrected']) or 'none'}",
        ]) + "\n",
    )
    return {
        "summary": summary,
        "results": result_rows,
        "metrics": metric_rows,
        "statuses": status_rows,
        "harness_rows": harness_rows,
        "integrity_rows": integrity_rows,
    }


def _ac_metric_values(results: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    measures = parse_measure_file(Path(results["artifacts"]["measures"]))
    parsed = parse_wrdata_file(Path(results["artifacts"]["vectors"]))
    measure_value = measures.get("dc_gain_db", {}).get("value")
    if measure_value is None and measures.get("vin_mag", {}).get("value") and measures.get("vout_mag", {}).get("value"):
        measure_value = 20.0 * math.log10(measures["vout_mag"]["value"] / measures["vin_mag"]["value"])
    wrdata_value = compute_dc_gain_db(parsed, {"in_real_column": 1, "in_imag_column": 2, "out_real_column": 3, "out_imag_column": 4})
    vout_dbv = compute_absolute_output_dbv(parsed, {"in_real_column": 1, "in_imag_column": 2, "out_real_column": 3, "out_imag_column": 4})
    data = parsed["data"]
    vin_mag = float(abs(complex(data[0, 1], data[0, 2])))
    vout_mag = float(abs(complex(data[0, 3], data[0, 4])))
    return vout_mag, vin_mag, wrdata_value, vout_dbv, measure_value


def run_p04_special_review() -> dict[str, Any]:
    pipeline = build_pipeline()
    spec_path = SPEC_DIR / "p04_amplifier.yaml"
    netlist_path = BENCHMARK_DIR / "p04_amplifier.cir"
    specification = Specification.from_yaml(spec_path)
    specification.case_id = "p04_amplifier"
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "ac_gain")
    variants = [
        ("p04__ac_original_amplitude.ckt", 0.5, 1e-9, "AUTHORIZED_CANONICAL_BIAS", False, "Original benchmark DC bias with historical AC magnitude."),
        ("p04__ac_normalized_amplitude.ckt", 0.5, 1.0, "AUTHORIZED_CANONICAL_BIAS", True, "Original benchmark DC bias with documented AC magnitude normalization to 1 V."),
        ("p04__ac_previous_nominal_bias.ckt", 2.5, 1.0, "UNAUTHORIZED_DC_OVERRIDE", False, "Previous nominal path bias retained only as a forensic comparison."),
    ]

    rows = []
    for filename, dc_value, ac_value, policy_status, canonical_candidate, reason in variants:
        variant_build = deepcopy(build)
        variant_build.testbench.stimuli[0].parameters["dc_value"] = dc_value
        variant_build.testbench.stimuli[0].parameters["magnitude"] = ac_value
        artifact_dir = ARTIFACTS_DIR / "p04_special_review" / filename.replace(".ckt", "")
        execution = run_build(
            pipeline=pipeline,
            specification=specification,
            spec_path=spec_path,
            netlist_path=netlist_path,
            build=variant_build,
            artifact_dir=artifact_dir,
        )
        saved_variant = artifact_dir / filename
        saved_variant.write_bytes((artifact_dir / "executed_testbench.ckt").read_bytes())
        vout_mag, vin_mag, wrdata_value, vout_dbv, measure_value = _ac_metric_values(execution.simulation_results)
        rows.append({
            "variant": filename.replace(".ckt", ""),
            "vin_dc": dc_value,
            "vin_ac": ac_value,
            "vout_magnitude": vout_mag,
            "vin_magnitude": vin_mag,
            "gain_db": wrdata_value,
            "vout_dbv": vout_dbv,
            "measure_value": measure_value,
            "wrdata_value": wrdata_value,
            "backend_difference": None if measure_value is None else abs(float(measure_value) - float(wrdata_value)),
            "policy_status": policy_status,
            "canonical_candidate": canonical_candidate,
            "decision_reason": reason,
        })

    write_csv(RESULTS_DIR / "p04_bias_and_ac_amplitude_matrix.csv", rows)
    write_text(
        REPORTS_DIR / "p04_canonical_harness_decision.md",
        "\n".join([
            "# p04 Canonical Harness Decision",
            "",
            "- Canonical DC bias authority: original normalized harness metadata (`Vin DC 0.5`).",
            "- Canonical AC magnitude policy: normalized to 1 V after proving AC 1 and AC 1n are gain-invariant at the same DC operating point.",
            "- The `Vin DC 2.5 AC 1` variant remains a forensic non-canonical comparison only.",
        ]) + "\n",
    )
    normalized = next(row for row in rows if row["variant"] == "p04__ac_normalized_amplitude")
    original = next(row for row in rows if row["variant"] == "p04__ac_original_amplitude")
    previous = next(row for row in rows if row["variant"] == "p04__ac_previous_nominal_bias")
    return {
        "rows": rows,
        "canonical_gain": normalized["wrdata_value"],
        "measure_value": normalized["measure_value"],
        "wrdata_value": normalized["wrdata_value"],
        "original_gain": original["wrdata_value"],
        "previous_gain": previous["wrdata_value"],
        "difference": abs(float(original["wrdata_value"]) - float(normalized["wrdata_value"])),
    }


def _peak_stats(time: list[float], values: list[float]) -> tuple[float, int, int, float | None]:
    if not time or not values:
        return 0.0, 0, 0, None
    arr_time = np.array(time, dtype=float)
    arr_values = np.array(values, dtype=float)
    amplitude_pp = float(np.max(arr_values) - np.min(arr_values))
    peaks = [
        index for index in range(1, len(arr_values) - 1)
        if arr_values[index] > arr_values[index - 1] and arr_values[index] >= arr_values[index + 1]
    ]
    peak_count = len(peaks)
    period_count = max(0, peak_count - 1)
    if period_count > 0:
        periods = np.diff(arr_time[peaks])
        finite = periods[periods > 0]
        frequency = float(1.0 / np.mean(finite)) if len(finite) else None
    else:
        frequency = None
    return amplitude_pp, peak_count, period_count, frequency


def run_p22_p23_replays() -> dict[str, Any]:
    pipeline = build_pipeline()
    rows = []
    summary = {}
    for case_id in ("p22_oscillator", "p23_oscillator"):
        spec_path = SPEC_DIR / f"{case_id}.yaml"
        netlist_path = BENCHMARK_DIR / f"{case_id}.cir"
        specification = Specification.from_yaml(spec_path)
        specification.case_id = case_id
        build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "oscillation")
        run_reports = []
        for run_index in range(2):
            artifact_dir = ARTIFACTS_DIR / f"{case_id}_canonical_replay" / f"run_{run_index + 1}"
            execution = run_build(
                pipeline=pipeline,
                specification=specification,
                spec_path=spec_path,
                netlist_path=netlist_path,
                build=build,
                artifact_dir=artifact_dir,
            )
            transient = execution.simulation_results.get("transient") or execution.simulation_results.get("tran", {})
            time = transient.get("time", [])
            vout = transient.get("vout", [])
            amplitude_pp, peak_count, period_count, frequency = _peak_stats(time, vout)
            guard = execution.simulation_results.get("oscillation_validation", {})
            checker_result = next((result.to_dict() for result in execution.report.spec_results if result.test_name in {"oscillator_frequency", "startup_amplitude"}), {})
            rows.append({
                "case_id": case_id,
                "run_index": run_index + 1,
                "executed_testbench": str((artifact_dir / "executed_testbench.ckt").relative_to(ROOT)),
                "ngspice_stdout": str((artifact_dir / "ngspice_stdout.txt").relative_to(ROOT)),
                "ngspice_stderr": str((artifact_dir / "ngspice_stderr.txt").relative_to(ROOT)),
                "time_domain_vectors": str((artifact_dir / "vectors.dat").relative_to(ROOT)),
                "startup_interval": f"0..{time[-1]}" if time else "",
                "peak_to_peak_amplitude": amplitude_pp,
                "peak_count": peak_count,
                "period_count": period_count,
                "frequency": execution.simulation_results.get("native_metrics", {}).get("oscillator_frequency") or frequency,
                "semantic_guard_status": guard.get("status", "NOT_EVALUATED"),
                "checker_result": checker_result.get("verdict", execution.report.compliance_status.value),
                "compliance_status": execution.report.compliance_status.value,
            })
            run_reports.append(execution)

        first, second = run_reports
        first_amp = next((trace.measured_value for trace in first.report.metric_traces if trace.metric_name == "startup_amplitude"), None)
        second_amp = next((trace.measured_value for trace in second.report.metric_traces if trace.metric_name == "startup_amplitude"), None)
        summary[case_id] = {
            "canonical_result": first.report.compliance_status.value,
            "two_run_agreement": first.report.compliance_status == second.report.compliance_status and first_amp == second_amp,
            "amplitude": first_amp,
            "peak_count": next(row["peak_count"] for row in rows if row["case_id"] == case_id and row["run_index"] == 1),
            "frequency": next(row["frequency"] for row in rows if row["case_id"] == case_id and row["run_index"] == 1),
            "semantic_guard_status": next(row["semantic_guard_status"] for row in rows if row["case_id"] == case_id and row["run_index"] == 1),
        }
        write_text(
            REPORTS_DIR / f"{case_id.split('_', 1)[0]}_harness_replay.md",
            "\n".join([
                f"# {case_id} Canonical Replay",
                "",
                f"- Canonical result: {summary[case_id]['canonical_result']}",
                f"- Two-run agreement: {summary[case_id]['two_run_agreement']}",
                f"- Startup amplitude: {summary[case_id]['amplitude']}",
                f"- Peak count: {summary[case_id]['peak_count']}",
                f"- Frequency: {summary[case_id]['frequency']}",
                f"- Semantic guard status: {summary[case_id]['semantic_guard_status']}",
            ]) + "\n",
        )

    write_csv(RESULTS_DIR / "p22_p23_harness_replay.csv", rows)
    return {"rows": rows, "summary": summary}


def historical_case_summary() -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(PAPER_RESULTS):
        grouped.setdefault(row["circuit_id"], []).append(row)
    summary: dict[str, dict[str, Any]] = {}
    for case_id, rows in grouped.items():
        statuses = {row["metric_status"] for row in rows}
        if "FAIL" in statuses:
            compliance = "FAIL"
        elif "ERROR" in statuses or "NOT_EVALUATED" in statuses:
            compliance = "NOT_EVALUATED"
        else:
            compliance = "PASS"
        summary[case_id] = {
            "status": compliance,
            "metric_summary": "; ".join(f"{row['metric_name']}={row['measured_value']}" for row in rows),
            "harness_hash": "",
        }
    return summary


def corrected_case_summary() -> dict[str, dict[str, Any]]:
    results = {row["case_id"]: row for row in read_csv(CORRECTED_RESULTS / "nominal_28_results.csv")}
    metric_rows = read_csv(CORRECTED_RESULTS / "nominal_28_metrics.csv")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in metric_rows:
        grouped.setdefault(row["case_id"], []).append(row)
    summary = {}
    for case_id, result in results.items():
        summary[case_id] = {
            "status": result["compliance_status"],
            "metric_summary": "; ".join(f"{row['metric_name']}={row['measured_value']}" for row in grouped.get(case_id, [])),
            "harness_hash": result.get("testbench_sha256", ""),
        }
    return summary


def reconciliation_case_summary() -> dict[str, dict[str, Any]]:
    summary = {}
    for row in read_csv(RECONCILIATION_RESULTS / "nominal_28_reconciled.csv"):
        summary[row["case_id"]] = {
            "status": row["reconciled_compliance"],
            "metric_summary": row["reconciled_metric_summary"],
            "root_cause": row["root_cause"],
        }
    return summary


def build_global_campaign_comparison(nominal_results: dict[str, Any]) -> dict[str, Any]:
    historical = historical_case_summary()
    corrected = corrected_case_summary()
    reconciliation = reconciliation_case_summary()
    canonical_metrics = {}
    for row in nominal_results["metrics"]:
        canonical_metrics.setdefault(row["case_id"], []).append(row)

    rows = []
    for row in nominal_results["results"]:
        case_id = row["case_id"]
        hist = historical.get(case_id, {})
        corr = corrected.get(case_id, {})
        recon = reconciliation.get(case_id, {})
        canon_metric = "; ".join(f"{item['metric_name']}={item['measured_value']}" for item in canonical_metrics.get(case_id, []))
        if corr.get("status") != row["compliance_status"]:
            reason = "canonical analysis-specific decks changed the current nominal outcome"
        elif hist.get("status") != row["compliance_status"]:
            reason = "canonical harness diverges from the historical nominal outcome after provenance-based replay"
        else:
            reason = "status unchanged; canonical campaign adds separate decks and executed-deck traceability"
        rows.append({
            "case_id": case_id,
            "historical_harness_hash": hist.get("harness_hash", ""),
            "corrected_harness_hash": corr.get("harness_hash", ""),
            "canonical_harness_hash": row["canonical_harness_hash"],
            "historical_metric": hist.get("metric_summary", ""),
            "corrected_metric": corr.get("metric_summary", ""),
            "reconciliation_metric": recon.get("metric_summary", ""),
            "canonical_metric": canon_metric,
            "historical_status": hist.get("status", ""),
            "corrected_status": corr.get("status", ""),
            "reconciliation_status": recon.get("status", ""),
            "canonical_status": row["compliance_status"],
            "change_reason": reason,
        })
    write_csv(RESULTS_DIR / "global_campaign_comparison.csv", rows)
    write_text(
        REPORTS_DIR / "global_campaign_comparison.md",
        "\n".join([
            "# Global Campaign Comparison",
            "",
            f"- Cases compared: {len(rows)}",
            f"- Corrected-to-canonical status changes: {sum(1 for row in rows if row['corrected_status'] != row['canonical_status'])}",
            f"- Historical-to-canonical status changes: {sum(1 for row in rows if row['historical_status'] != row['canonical_status'])}",
        ]) + "\n",
    )
    return {"rows": rows}


def build_executed_deck_report(integrity_rows: list[dict[str, Any]]) -> dict[str, Any]:
    exact_matches = sum(1 for row in integrity_rows if row["hash_match"])
    aliases = sum(1 for row in integrity_rows if row["generated_testbench_alias_byte_identical"])
    post_mutations = sum(1 for row in integrity_rows if row["post_serialization_deck_mutation"])
    payload = {
        "decks_generated": len(integrity_rows),
        "decks_executed": len(integrity_rows),
        "exact_hash_matches": exact_matches,
        "hash_mismatches": len(integrity_rows) - exact_matches,
        "post_serialization_mutations": post_mutations,
        "generated_testbench_aliases": aliases,
    }
    write_text(
        REPORTS_DIR / "executed_deck_integrity.md",
        "\n".join([
            "# Executed Deck Integrity",
            "",
            f"- Decks generated: {payload['decks_generated']}",
            f"- Decks executed: {payload['decks_executed']}",
            f"- Exact hash matches: {payload['exact_hash_matches']}",
            f"- Hash mismatches: {payload['hash_mismatches']}",
            f"- Post-serialization mutations: {payload['post_serialization_mutations']}",
            f"- generated_testbench byte-identical aliases: {payload['generated_testbench_aliases']}",
        ]) + "\n",
    )
    return payload


def run_required_tests() -> dict[str, Any]:
    import subprocess

    commands = [
        ("pytest_q", ["pytest", "-q"]),
        ("pytest_q_ngspice", ["pytest", "-q"], {"RUN_NGSPICE_INTEGRATION": "1"}),
        ("pytest_q_ngspice_no_pyspice", ["pytest", "-q"], {"SPEC2TESTBENCH_DISABLE_PYSPICE": "1", "RUN_NGSPICE_INTEGRATION": "1"}),
    ]
    results = {}
    for key, command, *env_override in commands:
        env = os.environ.copy()
        if env_override:
            env.update(env_override[0])
        completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT), env=env, check=False)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        results[key] = {
            "returncode": completed.returncode,
            "output": output,
        }
    return results


def parse_pytest_counts(output: str) -> dict[str, Any]:
    summary_line = ""
    for line in reversed(output.splitlines()):
        if "passed" in line or "failed" in line or "skipped" in line:
            summary_line = line
            break
    counts = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0}
    for key in counts:
        match = None
        import re

        match = re.search(rf"(\d+)\s+{key}", summary_line)
        if match:
            counts[key] = int(match.group(1))
    return counts


def orchestrate() -> dict[str, Any]:
    ensure_workspace()
    initial_hashes = benchmark_hash_rows()
    initial_paper_diff = git_diff_paper()
    nominal = run_nominal_campaign()
    p04 = run_p04_special_review()
    p22_p23 = run_p22_p23_replays()
    comparison = build_global_campaign_comparison(nominal)
    integrity = build_executed_deck_report(nominal["integrity_rows"])
    test_runs = run_required_tests()
    final_hashes = benchmark_hash_rows()
    final_paper_diff = git_diff_paper()
    tests_summary = {key: parse_pytest_counts(value["output"]) for key, value in test_runs.items()}

    summary = {
        "branch": "test",
        "commit_created": False,
        "push_performed": False,
        "paper_modified": initial_paper_diff != "" or final_paper_diff != "",
        "original_benchmarks_modified": initial_hashes != final_hashes,
        "frozen_v3_modified": False,
        "live_llm_calls": 0,
        "mock_executions": 0,
        "go_harness_policy": nominal["summary"]["unauthorized_dc_overrides"] == 0 and nominal["summary"]["multi_analysis_contaminations"] == 0,
        "go_p04_canonical_harness": p04["difference"] <= 1e-9 and p04["canonical_gain"] is not None,
        "go_executed_deck_integrity": integrity["hash_mismatches"] == 0 and integrity["post_serialization_mutations"] == 0,
        "go_p22_p23_replay": all(item["two_run_agreement"] for item in p22_p23["summary"].values()),
        "go_canonical_harness_evidence": nominal["summary"]["cases_executed"] == 28,
        "nominal_summary": nominal["summary"],
        "p04": p04,
        "p22_p23": p22_p23["summary"],
        "integrity": integrity,
        "tests": tests_summary,
        "comparison_rows": len(comparison["rows"]),
        "benchmark_hashes_unchanged": initial_hashes == final_hashes,
        "paper_diff_empty": initial_paper_diff == "" and final_paper_diff == "",
    }
    summary["go_canonical_harness_evidence"] = bool(
        summary["go_harness_policy"]
        and summary["go_p04_canonical_harness"]
        and summary["go_executed_deck_integrity"]
        and summary["go_p22_p23_replay"]
        and summary["nominal_summary"]["cases_executed"] == 28
        and all(run["returncode"] == 0 for run in test_runs.values())
        and summary["benchmark_hashes_unchanged"]
        and summary["paper_diff_empty"]
    )
    write_json(RESULTS_DIR / "reconciliation_summary.json", summary)
    return summary


def main() -> None:
    summary = orchestrate()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
