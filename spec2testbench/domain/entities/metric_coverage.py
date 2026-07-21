from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..value_objects.scientific_status import ComplianceStatus, ExecutionStatus
from ..value_objects.verdict import Verdict, CheckResult
from .testbench import TestBench


LEVEL_1_EXECUTION = "LEVEL_1_EXECUTION"
LEVEL_2_MEASUREMENT = "LEVEL_2_MEASUREMENT"
LEVEL_3_SCIENTIFIC_EVALUATION = "LEVEL_3_SCIENTIFIC_EVALUATION"

NOT_EVALUATED_CATEGORIES = {
    "MISSING_ANALYSIS_DECK",
    "MISSING_MEASUREMENT_RECIPE",
    "MISSING_COMPILER_TEMPLATE",
    "MISSING_INPUT_ROLE",
    "MISSING_OUTPUT_ROLE",
    "MISSING_SOURCE_ROLE",
    "MISSING_VECTOR",
    "MISSING_MEASURE_RESULT",
    "BACKEND_UNAVAILABLE",
    "PARSER_FAILURE",
    "METRIC_ANALYSIS_MISMATCH",
    "METRIC_TOPOLOGY_MISMATCH",
    "MULTI_ANALYSIS_AGGREGATION_FAILURE",
    "SEMANTIC_GUARD_REJECTION",
    "PHYSICAL_PREREQUISITE_ABSENT",
    "SIMULATION_FAILURE",
    "SPECIFICATION_ERROR",
    "EXPECTED_NOT_EVALUATED",
    "UNKNOWN",
}

_DC_METRICS = {"operating_point", "vout_dc", "quiescent_current", "idd", "power"}
_AC_METRICS = {
    "dc_gain",
    "dc_gain_db",
    "absolute_output_dbv",
    "absolute_input_dbv",
    "transfer_magnitude_linear",
    "transfer_phase_deg",
    "bandwidth",
    "cutoff_frequency_hz",
    "unity_gain_frequency",
    "ugbw",
    "phase_margin",
}
_OSCILLATION_METRICS = {"frequency_hz", "oscillator_frequency", "startup_amplitude"}
_SCHMITT_METRICS = {"v_t_plus", "v_t_minus", "hysteresis_width"}
_TRANSIENT_METRICS = {"slew_rate", "settling_time", "propagation_delay", "propagation_delay_s"}
_SPECTRAL_METRICS = {"thd", "thd_percent", "fundamental_frequency"}


def analysis_id_for_metric(metric_name: str) -> str:
    if metric_name in _DC_METRICS:
        return "op"
    if metric_name in _AC_METRICS:
        return "ac_gain"
    if metric_name in _SCHMITT_METRICS:
        return "schmitt"
    if metric_name in _OSCILLATION_METRICS:
        return "oscillation"
    if metric_name in _TRANSIENT_METRICS:
        return "transient_delay"
    if metric_name in _SPECTRAL_METRICS:
        return "spectral"
    return "unknown"


def infer_not_evaluated_category(
    *,
    metric_name: str,
    analysis_id: str,
    requested_analysis_present: bool,
    request: dict[str, Any] | None,
    execution_bundle: "AnalysisExecutionBundle | None",
    extraction: dict[str, Any] | None,
    result: CheckResult | None,
) -> tuple[str, str]:
    if not requested_analysis_present:
        return "MISSING_ANALYSIS_DECK", "No analysis-specific deck was produced for the required metric."
    if request is None:
        return "MISSING_MEASUREMENT_RECIPE", "No measurement request was attached to the required metric."
    if not request.get("measurement_expression_id"):
        return "MISSING_MEASUREMENT_RECIPE", "The measurement request is missing its measurement expression identifier."
    if execution_bundle is None:
        return "MULTI_ANALYSIS_AGGREGATION_FAILURE", "The analysis ran but was not retained in the aggregated evidence bundle."
    if execution_bundle.execution_status != ExecutionStatus.SUCCESS:
        return "SIMULATION_FAILURE", "The analysis deck did not execute successfully."

    input_node = str(request.get("input_node") or "").strip()
    output_node = str(request.get("output_node") or "").strip()
    if metric_name in _AC_METRICS | _SCHMITT_METRICS | {"propagation_delay", "propagation_delay_s"} and not input_node:
        return "MISSING_INPUT_ROLE", "The measurement recipe has no resolved input node."
    if metric_name not in {"quiescent_current", "idd", "power"} and not output_node:
        return "MISSING_OUTPUT_ROLE", "The measurement recipe has no resolved output node."

    extraction = extraction or {}
    reason = str(extraction.get("reason") or "").strip().upper()
    backend = str(extraction.get("measurement_backend") or extraction.get("backend") or "").strip().upper()
    message = str((result.message if result else "") or "")

    if reason.startswith("OSCILLATION_GUARD_"):
        if "AMPLITUDE_TOO_LOW" in reason or "NO_VALID_PERIOD" in reason:
            return "EXPECTED_NOT_EVALUATED", "The oscillation guard rejected a physically absent oscillation."
        return "SEMANTIC_GUARD_REJECTION", "The semantic guard rejected the waveform before scientific evaluation."
    if "precheck_failed" in message.lower():
        lowered = message.lower()
        if "target_metric_supported_by_extractor" in lowered:
            return "SPECIFICATION_ERROR", "The specification requests an unsupported metric."
        if "required_analysis_generated" in lowered:
            return "MISSING_ANALYSIS_DECK", "The required analysis was not present in the aggregated testbench."
        if "required_signals_available" in lowered:
            return "MISSING_SOURCE_ROLE", "The specification does not expose the required signal roles."
        return "MISSING_MEASUREMENT_RECIPE", "The metric failed the precheck before measurement extraction."
    if reason in {"WRDATA_FILE_MISSING", "WRDATA_FILE_EMPTY"}:
        return "MISSING_VECTOR", "The measurement backend expected a vector file that was missing or empty."
    if reason in {"WRDATA_UNPARSABLE", "WRDATA_NON_FINITE", "UNPARSABLE_MEASURE", "NON_FINITE_MEASURE"}:
        return "PARSER_FAILURE", "The measurement artifact exists but its numeric output could not be parsed safely."
    if reason in {"WRDATA_COLUMN_MISMATCH", "INPUT_VECTOR_MISSING", "OUTPUT_VECTOR_MISSING"}:
        return "MISSING_VECTOR", "The measurement artifact does not contain the required vectors."
    if reason in {"INPUT_VECTOR_ZERO", "INVALID_GAIN_RATIO"}:
        return "METRIC_TOPOLOGY_MISMATCH", "The extracted vectors do not satisfy the topology required by the metric."
    if reason in {"NO_OUTPUT_TRANSITION", "NO_VALID_PERIOD", "CUTOFF_NOT_FOUND", "UNITY_GAIN_NOT_FOUND", "FUNDAMENTAL_NOT_FOUND"}:
        return "PHYSICAL_PREREQUISITE_ABSENT", "The waveform never reached the physical condition needed for this metric."
    if reason in {"NGSPICE_MEASURE_FAILED"}:
        return "MISSING_MEASURE_RESULT", "Ngspice executed but did not emit the requested .measure value."
    if reason in {"WRDATA_UNSUPPORTED_METRIC"}:
        return "BACKEND_UNAVAILABLE", "The selected backend does not implement this measurement recipe yet."
    if backend == "NGSPICE_MEASURE" and extraction.get("measured_value") is None:
        return "MISSING_MEASURE_RESULT", "The .measure backend stayed empty on an otherwise successful run."
    if backend == "NGSPICE_WRDATA" and extraction.get("measured_value") is None:
        return "MISSING_VECTOR", "The wrdata backend did not provide a usable numeric vector."
    return "UNKNOWN", "The metric stayed unevaluated for a reason that requires manual triage."


@dataclass
class AnalysisExecutionBundle:
    case_id: str
    analysis_id: str
    testbench: TestBench
    simulation_results: dict[str, Any]
    report: Any
    artifact_path: Path
    requested_metrics: list[str] = field(default_factory=list)
    executed_deck_sha256: str = ""

    @property
    def execution_status(self) -> ExecutionStatus:
        raw_status = (
            self.simulation_results.get("execution_status")
            or getattr(self.report, "execution_status", ExecutionStatus.ERROR)
        )
        if isinstance(raw_status, ExecutionStatus):
            return raw_status
        try:
            return ExecutionStatus(str(raw_status))
        except ValueError:
            return ExecutionStatus.ERROR

    def measurement_requests(self) -> list[dict[str, Any]]:
        metadata = getattr(self.testbench, "metadata", None) or {}
        return [dict(item) for item in metadata.get("measurement_requests", [])]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "analysis_id": self.analysis_id,
            "requested_metrics": list(self.requested_metrics),
            "executed_deck_sha256": self.executed_deck_sha256 or self.simulation_results.get("executed_file_sha256", ""),
            "artifact_path": str(self.artifact_path),
            "execution_status": self.execution_status.value,
            "measurement_backend": self.simulation_results.get("measurement_backend"),
        }


@dataclass
class MetricEvidenceBundle:
    case_id: str
    analysis_id: str
    executed_deck_sha256: str
    metric_name: str
    raw_value: float | None
    normalized_value: float | None
    evaluation_status: str
    backend: str
    semantic_guards: list[str]
    artifact_path: str
    level_1_execution: str
    level_2_measurement: str
    level_3_scientific_evaluation: str
    checker_input_present: bool
    raw_metric_present: bool
    normalized_metric_present: bool
    semantic_guard_status: str
    measurement_recipe: str
    not_evaluated_reason: str
    root_cause_category: str
    repairable: bool
    repair_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "analysis_id": self.analysis_id,
            "executed_deck_sha256": self.executed_deck_sha256,
            "metric_name": self.metric_name,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "evaluation_status": self.evaluation_status,
            "backend": self.backend,
            "semantic_guards": "|".join(self.semantic_guards),
            "artifact_path": self.artifact_path,
            "level_1_execution": self.level_1_execution,
            "level_2_measurement": self.level_2_measurement,
            "level_3_scientific_evaluation": self.level_3_scientific_evaluation,
            "checker_input_present": self.checker_input_present,
            "raw_metric_present": self.raw_metric_present,
            "normalized_metric_present": self.normalized_metric_present,
            "semantic_guard_status": self.semantic_guard_status,
            "measurement_recipe": self.measurement_recipe,
            "not_evaluated_reason": self.not_evaluated_reason,
            "root_cause_category": self.root_cause_category,
            "repairable": self.repairable,
            "repair_action": self.repair_action,
        }


@dataclass
class CaseEvidenceAggregator:
    case_id: str
    executions: list[AnalysisExecutionBundle] = field(default_factory=list)

    def add_execution(self, bundle: AnalysisExecutionBundle) -> None:
        if bundle.case_id != self.case_id:
            raise ValueError(f"Case mismatch: expected {self.case_id}, received {bundle.case_id}")
        self.executions.append(bundle)

    def aggregate_testbench(self, specification_name: str) -> TestBench:
        if not self.executions:
            raise ValueError("No analysis executions were recorded for aggregation.")

        merged = deepcopy(self.executions[0].testbench)
        merged.name = f"{self.case_id}__aggregated"
        merged.category = "aggregated"
        merged.circuit_name = specification_name
        merged.case_id = self.case_id
        merged.stimuli = []
        merged.analyses = []
        merged.measurements = []

        seen_measurements: set[str] = set()
        measurement_requests: list[dict[str, Any]] = []
        request_names: set[str] = set()
        required_metrics: list[str] = []

        for execution in self.executions:
            merged.analyses.extend(deepcopy(execution.testbench.analyses))
            required_metrics.extend(name for name in execution.requested_metrics if name not in required_metrics)
            for measurement in execution.testbench.measurements:
                if measurement.name in seen_measurements:
                    continue
                merged.measurements.append(deepcopy(measurement))
                seen_measurements.add(measurement.name)
            for request in execution.measurement_requests():
                name = str(request.get("name") or "").strip()
                if not name or name in request_names:
                    continue
                measurement_requests.append(deepcopy(request))
                request_names.add(name)

        metadata = dict(merged.metadata or {})
        metadata["required_metrics"] = required_metrics
        metadata["measurement_requests"] = measurement_requests
        metadata["analysis_execution_bundles"] = [bundle.to_dict() for bundle in self.executions]
        merged.metadata = metadata
        return merged

    def aggregate_simulation_results(self) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "success": True,
            "simulation_mode": None,
            "execution_status": ExecutionStatus.SUCCESS.value,
            "metrics": {},
            "native_metrics": {},
            "native_extractions": {},
            "measurement_requests": [],
            "logs": [],
            "errors": [],
            "dc": {},
            "ac": {},
            "tran": {},
            "transient": {},
            "fourier": {},
            "pvt": {},
            "currents": {},
            "case_id": self.case_id,
            "measurement_backend": "",
            "analysis_execution_bundles": [bundle.to_dict() for bundle in self.executions],
            "netlist_binding_status": "",
            "expected_netlist_sha256": "",
            "actual_netlist_sha256": "",
        }
        measurement_requests: list[dict[str, Any]] = []
        request_names: set[str] = set()
        backends: list[str] = []
        binding_statuses: list[str] = []

        for execution in self.executions:
            results = execution.simulation_results or {}
            if merged["simulation_mode"] is None and results.get("simulation_mode"):
                merged["simulation_mode"] = results.get("simulation_mode")
            if execution.execution_status != ExecutionStatus.SUCCESS:
                merged["success"] = False
                merged["execution_status"] = execution.execution_status.value
            merged["logs"].extend(results.get("logs", []))
            merged["errors"].extend(results.get("errors", []))
            if results.get("expected_netlist_sha256") and not merged["expected_netlist_sha256"]:
                merged["expected_netlist_sha256"] = str(results.get("expected_netlist_sha256"))
            if results.get("actual_netlist_sha256") and not merged["actual_netlist_sha256"]:
                merged["actual_netlist_sha256"] = str(results.get("actual_netlist_sha256"))
            if results.get("netlist_binding_status"):
                binding_statuses.append(str(results.get("netlist_binding_status")))
            for section in ("dc", "ac", "tran", "transient", "fourier", "pvt", "currents", "metrics", "native_metrics"):
                payload = results.get(section)
                if isinstance(payload, dict):
                    merged.setdefault(section, {}).update(deepcopy(payload))
            if results.get("measurement_backend"):
                backend = str(results["measurement_backend"]).strip()
                if backend and backend not in backends:
                    backends.append(backend)
            for request in execution.measurement_requests():
                name = str(request.get("name") or "").strip()
                if not name or name in request_names:
                    continue
                measurement_requests.append(deepcopy(request))
                request_names.add(name)
            for metric_name, extraction in (results.get("native_extractions", {}) or {}).items():
                merged["native_extractions"][metric_name] = {
                    **deepcopy(extraction),
                    "analysis_id": execution.analysis_id,
                    "artifact_path": str(execution.artifact_path),
                    "executed_deck_sha256": execution.executed_deck_sha256 or results.get("executed_file_sha256", ""),
                }

        merged["measurement_requests"] = measurement_requests
        if len(backends) == 1:
            merged["measurement_backend"] = backends[0]
        elif backends:
            merged["measurement_backend"] = "MIXED"
        else:
            merged["measurement_backend"] = "UNAVAILABLE"
        if binding_statuses and all(status == "MATCH" for status in binding_statuses):
            merged["netlist_binding_status"] = "MATCH"
        elif binding_statuses:
            merged["netlist_binding_status"] = binding_statuses[0]
        return merged

    def build_metric_evidence(
        self,
        specification_metrics: list[str],
        *,
        aggregated_results: dict[str, Any],
        final_results: list[CheckResult],
    ) -> list[MetricEvidenceBundle]:
        final_result_map = {result.test_name: result for result in final_results}
        request_map = {
            str(request.get("name") or "").strip(): request
            for request in aggregated_results.get("measurement_requests", [])
            if str(request.get("name") or "").strip()
        }
        execution_map = {bundle.analysis_id: bundle for bundle in self.executions}
        evidence_rows: list[MetricEvidenceBundle] = []

        for metric_name in specification_metrics:
            analysis_id = analysis_id_for_metric(metric_name)
            execution_bundle = execution_map.get(analysis_id)
            request = request_map.get(metric_name)
            extraction = (aggregated_results.get("native_extractions", {}) or {}).get(metric_name, {})
            result = final_result_map.get(metric_name)
            normalized_value = None if result is None else result.measured_value
            raw_value = extraction.get("measured_value")
            semantic_guards = list(request.get("semantic_guards", [])) if request else []
            semantic_guard_status = ""
            if str(extraction.get("reason") or "").upper().startswith("OSCILLATION_GUARD_"):
                semantic_guard_status = str(extraction.get("reason") or "")
            elif execution_bundle is not None:
                semantic_guard_status = str(execution_bundle.simulation_results.get("oscillation_validation", {}).get("status", "") or "")

            evaluation_status = "NOT_EVALUATED"
            if result is not None:
                if result.verdict in (Verdict.PASS, Verdict.WARNING):
                    evaluation_status = "PASS"
                elif result.verdict == Verdict.FAIL:
                    evaluation_status = "FAIL"
            elif raw_value is not None:
                evaluation_status = "PASS"

            if evaluation_status == "NOT_EVALUATED":
                root_cause_category, detailed_reason = infer_not_evaluated_category(
                    metric_name=metric_name,
                    analysis_id=analysis_id,
                    requested_analysis_present=analysis_id in execution_map,
                    request=request,
                    execution_bundle=execution_bundle,
                    extraction=extraction,
                    result=result,
                )
                not_evaluated_reason = detailed_reason
            else:
                root_cause_category = ""
                not_evaluated_reason = ""

            repairable = root_cause_category not in {"", "PHYSICAL_PREREQUISITE_ABSENT", "EXPECTED_NOT_EVALUATED", "METRIC_TOPOLOGY_MISMATCH", "SPECIFICATION_ERROR"}
            if root_cause_category == "MISSING_ANALYSIS_DECK":
                repair_action = "Generate and execute the missing analysis-specific deck."
            elif root_cause_category == "MISSING_MEASUREMENT_RECIPE":
                repair_action = "Add or correct the measurement request and backend recipe for this metric."
            elif root_cause_category == "MISSING_VECTOR":
                repair_action = "Preserve the required vectors in wrdata and keep them available to the checker."
            elif root_cause_category == "MISSING_MEASURE_RESULT":
                repair_action = "Adjust the .measure command or declare the backend unsupported for this recipe."
            elif root_cause_category == "BACKEND_UNAVAILABLE":
                repair_action = "Implement or route the metric to a supported extraction backend."
            elif root_cause_category == "PARSER_FAILURE":
                repair_action = "Fix the parser or artifact format so the numeric result can be extracted."
            elif root_cause_category == "MULTI_ANALYSIS_AGGREGATION_FAILURE":
                repair_action = "Aggregate the per-analysis evidence under the same case before verification."
            elif root_cause_category == "SIMULATION_FAILURE":
                repair_action = "Repair the deck or ngspice invocation before scientific evaluation."
            elif root_cause_category in {"PHYSICAL_PREREQUISITE_ABSENT", "EXPECTED_NOT_EVALUATED", "METRIC_TOPOLOGY_MISMATCH", "SPECIFICATION_ERROR"}:
                repair_action = "No technical repair is applied automatically; document the scientific or specification limitation."
            else:
                repair_action = "Manual triage required."

            evidence_rows.append(
                MetricEvidenceBundle(
                    case_id=self.case_id,
                    analysis_id=analysis_id,
                    executed_deck_sha256=str(extraction.get("executed_deck_sha256") or (execution_bundle.executed_deck_sha256 if execution_bundle else "") or ""),
                    metric_name=metric_name,
                    raw_value=float(raw_value) if isinstance(raw_value, (int, float)) else None,
                    normalized_value=float(normalized_value) if isinstance(normalized_value, (int, float)) else None,
                    evaluation_status=evaluation_status,
                    backend=str(extraction.get("measurement_backend") or aggregated_results.get("measurement_backend") or ""),
                    semantic_guards=semantic_guards,
                    artifact_path=str(extraction.get("artifact_path") or (execution_bundle.artifact_path if execution_bundle else "")),
                    level_1_execution="PASS" if execution_bundle and execution_bundle.execution_status == ExecutionStatus.SUCCESS else "FAIL",
                    level_2_measurement="PASS" if raw_value is not None else "FAIL",
                    level_3_scientific_evaluation="PASS" if evaluation_status in {"PASS", "FAIL"} else "NOT_EVALUATED",
                    checker_input_present=normalized_value is not None,
                    raw_metric_present=raw_value is not None,
                    normalized_metric_present=normalized_value is not None,
                    semantic_guard_status=semantic_guard_status,
                    measurement_recipe=str(request.get("measurement_expression_id") or "") if request else "",
                    not_evaluated_reason=not_evaluated_reason,
                    root_cause_category=root_cause_category,
                    repairable=repairable,
                    repair_action=repair_action,
                )
            )
        return evidence_rows
