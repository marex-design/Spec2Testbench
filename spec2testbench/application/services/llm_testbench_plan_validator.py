from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ...domain.entities.specification import Specification
from ...domain.entities.testbench_plan import (
    AnalysisType,
    MeasurementBackendPreference,
    TestbenchPlan,
)
from ...domain.value_objects.llm_status import LLMPlanValidationStatus
from ...infrastructure.simulator.netlist_parser import NetlistParser
from .llm_metric_registry import get_metric_definition


VERDICT_LEAKAGE_TOKENS = {
    "PASS",
    "FAIL",
    "COMPLIANT",
    "NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
}


@dataclass(frozen=True)
class LLMPlanValidationIssue:
    status: LLMPlanValidationStatus
    field: str
    message: str


@dataclass
class LLMPlanValidationResult:
    status: LLMPlanValidationStatus
    issues: list[LLMPlanValidationIssue] = field(default_factory=list)
    parsed_plan: TestbenchPlan | None = None
    raw_payload: dict[str, Any] | None = None
    expected_case_id: str | None = None
    netlist_sha256: str | None = None
    specification_sha256: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status == LLMPlanValidationStatus.VALID and self.parsed_plan is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": [
                {"status": issue.status.value, "field": issue.field, "message": issue.message}
                for issue in self.issues
            ],
            "expected_case_id": self.expected_case_id,
            "netlist_sha256": self.netlist_sha256,
            "specification_sha256": self.specification_sha256,
        }


class LLMTestbenchPlanValidator:
    def __init__(self, netlist_parser: NetlistParser | None = None) -> None:
        self._netlist_parser = netlist_parser or NetlistParser()

    def parse_and_validate(
        self,
        raw_text: str,
        *,
        specification: Specification,
        netlist_path: Path,
        expected_case_id: str | None = None,
        expected_netlist_sha256: str | None = None,
        expected_specification_sha256: str | None = None,
    ) -> LLMPlanValidationResult:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return LLMPlanValidationResult(
                status=LLMPlanValidationStatus.INVALID_JSON,
                issues=[
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.INVALID_JSON,
                        field="raw_text",
                        message=str(exc),
                    )
                ],
                expected_case_id=expected_case_id,
                netlist_sha256=self._sha256_file(netlist_path),
                specification_sha256=self._sha256_specification(specification),
            )

        try:
            plan = TestbenchPlan.model_validate(payload)
        except ValidationError as exc:
            issues = [
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.SCHEMA_ERROR,
                    field=".".join(str(item) for item in error["loc"]),
                    message=error["msg"],
                )
                for error in exc.errors()
            ]
            return LLMPlanValidationResult(
                status=LLMPlanValidationStatus.SCHEMA_ERROR,
                issues=issues,
                raw_payload=payload,
                expected_case_id=expected_case_id,
                netlist_sha256=self._sha256_file(netlist_path),
                specification_sha256=self._sha256_specification(specification),
            )

        return self.validate(
            plan,
            specification=specification,
            netlist_path=netlist_path,
            expected_case_id=expected_case_id,
            expected_netlist_sha256=expected_netlist_sha256,
            expected_specification_sha256=expected_specification_sha256,
            raw_payload=payload,
        )

    def validate(
        self,
        plan: TestbenchPlan,
        *,
        specification: Specification,
        netlist_path: Path,
        expected_case_id: str | None = None,
        expected_netlist_sha256: str | None = None,
        expected_specification_sha256: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> LLMPlanValidationResult:
        issues: list[LLMPlanValidationIssue] = []
        expected_case_id = expected_case_id or specification.case_id or specification.name
        actual_netlist_sha = self._sha256_file(netlist_path)
        actual_spec_sha = self._sha256_specification(specification)

        if plan.case_id != expected_case_id:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.CASE_ID_MISMATCH,
                    field="case_id",
                    message=f"Expected case_id {expected_case_id}, got {plan.case_id}",
                )
            )

        if expected_netlist_sha256 and actual_netlist_sha != expected_netlist_sha256:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.CASE_ID_MISMATCH,
                    field="netlist_sha256",
                    message="Netlist hash mismatch for validation context",
                )
            )
        if expected_specification_sha256 and actual_spec_sha != expected_specification_sha256:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.CASE_ID_MISMATCH,
                    field="specification_sha256",
                    message="Specification hash mismatch for validation context",
                )
            )

        netlist = self._netlist_parser.parse(netlist_path)
        available_nodes = {
            *netlist.nodes,
            *specification.input_nodes,
            *specification.output_nodes,
            "0",
            "gnd",
            "GND",
        }

        for node in plan.observed_nodes:
            if node not in available_nodes:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.UNKNOWN_NODE,
                        field="observed_nodes",
                        message=f"Unknown observed node: {node}",
                    )
                )

        for stimulus in plan.stimuli:
            if stimulus.target_node not in available_nodes:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.UNKNOWN_NODE,
                        field=f"stimuli.{stimulus.source_name}.target_node",
                        message=f"Unknown stimulus target node: {stimulus.target_node}",
                    )
                )
            missing_keys = self._missing_stimulus_parameters(stimulus.stimulus_type.value, stimulus.parameters)
            if missing_keys:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.INVALID_STIMULUS,
                        field=f"stimuli.{stimulus.source_name}.parameters",
                        message=f"Missing stimulus parameters: {', '.join(missing_keys)}",
                    )
                )

        requested_metrics = list(specification.performance_targets.keys())
        plan_metrics = [measurement.metric_name for measurement in plan.measurements]
        missing = sorted(set(requested_metrics) - set(plan_metrics))
        extra = sorted(set(plan_metrics) - set(requested_metrics))
        if missing:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.MISSING_REQUIRED_METRIC,
                    field="measurements",
                    message=f"Missing requested metrics: {', '.join(missing)}",
                )
            )
        if extra:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.EXTRA_UNREQUESTED_METRIC,
                    field="measurements",
                    message=f"Unexpected metrics: {', '.join(extra)}",
                )
            )

        for measurement in plan.measurements:
            definition = get_metric_definition(measurement.metric_name)
            if definition is None:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.EXTRA_UNREQUESTED_METRIC,
                        field=f"measurements.{measurement.metric_name}",
                        message=f"Unsupported metric definition: {measurement.metric_name}",
                    )
                )
                continue

            if measurement.expected_unit != definition.expected_unit:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.UNIT_MISMATCH,
                        field=f"measurements.{measurement.metric_name}.expected_unit",
                        message=f"Expected unit {definition.expected_unit}, got {measurement.expected_unit}",
                    )
                )

            if measurement.analysis_type not in definition.compatible_analysis_types:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.ANALYSIS_MISMATCH,
                        field=f"measurements.{measurement.metric_name}.analysis_type",
                        message=(
                            f"Metric {measurement.metric_name} is incompatible with "
                            f"{measurement.analysis_type.value}"
                        ),
                    )
                )

            if measurement.backend_preference not in {
                MeasurementBackendPreference.AUTO,
                definition.preferred_backend,
            } and definition.preferred_backend != MeasurementBackendPreference.AUTO:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.UNSUPPORTED_BACKEND,
                        field=f"measurements.{measurement.metric_name}.backend_preference",
                        message=(
                            f"Metric {measurement.metric_name} prefers "
                            f"{definition.preferred_backend.value}, got {measurement.backend_preference.value}"
                        ),
                    )
                )

            for node_field, node_value in {
                "input_node": measurement.input_node,
                "output_node": measurement.output_node,
            }.items():
                if node_value and node_value not in available_nodes:
                    issues.append(
                        LLMPlanValidationIssue(
                            status=LLMPlanValidationStatus.UNKNOWN_NODE,
                            field=f"measurements.{measurement.metric_name}.{node_field}",
                            message=f"Unknown node {node_value}",
                        )
                    )

        simulation_issues = self._validate_simulation_parameters(plan)
        issues.extend(simulation_issues)
        issues.extend(self._detect_verdict_leakage(plan))
        issues.extend(self._detect_unsafe_parameters(plan))

        if issues:
            primary_status = issues[0].status
        else:
            primary_status = LLMPlanValidationStatus.VALID

        return LLMPlanValidationResult(
            status=primary_status,
            issues=issues,
            parsed_plan=plan if not issues else None,
            raw_payload=raw_payload,
            expected_case_id=expected_case_id,
            netlist_sha256=actual_netlist_sha,
            specification_sha256=actual_spec_sha,
        )

    def _validate_simulation_parameters(self, plan: TestbenchPlan) -> list[LLMPlanValidationIssue]:
        params = plan.simulation_parameters
        issues: list[LLMPlanValidationIssue] = []
        if plan.analysis_type == AnalysisType.DC:
            if not params.dc_source:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.INVALID_SIMULATION_RANGE,
                        field="simulation_parameters.dc_source",
                        message="DC plans require dc_source",
                    )
                )
            if None in (params.dc_start, params.dc_stop, params.dc_step):
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.INVALID_SIMULATION_RANGE,
                        field="simulation_parameters",
                        message="DC plans require dc_start, dc_stop, and dc_step",
                    )
                )
        if plan.analysis_type == AnalysisType.AC and params.points_per_decade and params.points_per_decade > 1000:
            issues.append(
                LLMPlanValidationIssue(
                    status=LLMPlanValidationStatus.UNSAFE_PARAMETER,
                    field="simulation_parameters.points_per_decade",
                    message="AC sweep exceeds safe points_per_decade bound",
                )
            )
        if plan.analysis_type == AnalysisType.TRAN:
            if params.stop_time_s and params.time_step_s:
                sample_count = params.stop_time_s / params.time_step_s
                if sample_count > 5_000_000:
                    issues.append(
                        LLMPlanValidationIssue(
                            status=LLMPlanValidationStatus.UNSAFE_PARAMETER,
                            field="simulation_parameters.time_step_s",
                            message="Transient sample count exceeds safe bound",
                        )
                    )
        return issues

    def _detect_verdict_leakage(self, plan: TestbenchPlan) -> list[LLMPlanValidationIssue]:
        issues: list[LLMPlanValidationIssue] = []
        texts = [plan.concise_rationale]
        for measurement in plan.measurements:
            texts.extend(str(value) for value in measurement.measurement_parameters.values() if isinstance(value, str))
        for stimulus in plan.stimuli:
            texts.extend(str(value) for value in stimulus.parameters.values() if isinstance(value, str))
        for text in texts:
            upper = text.upper()
            leaked = sorted(token for token in VERDICT_LEAKAGE_TOKENS if token in upper)
            if leaked:
                issues.append(
                    LLMPlanValidationIssue(
                        status=LLMPlanValidationStatus.VERDICT_LEAKAGE,
                        field="concise_rationale",
                        message=f"Verdict leakage token(s): {', '.join(leaked)}",
                    )
                )
                break
        return issues

    def _detect_unsafe_parameters(self, plan: TestbenchPlan) -> list[LLMPlanValidationIssue]:
        issues: list[LLMPlanValidationIssue] = []
        for stimulus in plan.stimuli:
            for key in ("frequency", "frequency_hz", "amplitude", "v2", "magnitude"):
                value = stimulus.parameters.get(key)
                if isinstance(value, (int, float)) and abs(float(value)) > 1e12:
                    issues.append(
                        LLMPlanValidationIssue(
                            status=LLMPlanValidationStatus.UNSAFE_PARAMETER,
                            field=f"stimuli.{stimulus.source_name}.parameters.{key}",
                            message="Stimulus parameter exceeds safe bound",
                        )
                    )
        return issues

    @staticmethod
    def _missing_stimulus_parameters(
        stimulus_type: str,
        parameters: dict[str, Any],
    ) -> list[str]:
        required = {
            "DC": ("value",),
            "AC": ("magnitude",),
            "PULSE": ("v1", "v2", "rise", "fall", "width", "period"),
            "SIN": ("amplitude", "frequency"),
            "PWL": ("points",),
            "TRIANGLE": ("v1", "v2", "period"),
        }
        missing = []
        for item in required.get(stimulus_type, ()):
            value = parameters.get(item)
            if value in (None, "", []):
                missing.append(item)
        return missing

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_specification(specification: Specification) -> str:
        payload = json.dumps(specification.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

