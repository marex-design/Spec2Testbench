from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...application.ports.llm_provider import (
    LLMEmptyResponseError,
    LLMProvider,
    LLMRequest,
    LLMTruncatedResponseError,
)
from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.entities.testbench_plan import TestbenchPlan
from ...domain.value_objects.llm_status import RepairStatus
from .llm_capability_builder import LLMCapabilityBuilder
from .llm_testbench_plan_validator import LLMPlanValidationResult, LLMTestbenchPlanValidator


@dataclass
class LLMRepairRecord:
    repair_status: RepairStatus
    prompt: str
    validation: dict[str, Any]


@dataclass
class LLMPlanningOutcome:
    request_payload: dict[str, Any]
    system_prompt: str
    prompt_sha256: str
    raw_response: str
    validation: LLMPlanValidationResult
    repair_history: list[LLMRepairRecord] = field(default_factory=list)
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    parsed_plan: TestbenchPlan | None = None
    call_history: list[dict[str, Any]] = field(default_factory=list)
    initial_validation: dict[str, Any] | None = None


class LLMGenerationService:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        capability_builder: LLMCapabilityBuilder | None = None,
        validator: LLMTestbenchPlanValidator | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self._provider = provider
        self._capability_builder = capability_builder or LLMCapabilityBuilder()
        self._validator = validator or LLMTestbenchPlanValidator()
        self._prompt_path = prompt_path or Path(
            "spec2testbench/infrastructure/llm/prompts/deepseek_testbench_planner_v1.txt"
        )

    def generate_plan(
        self,
        *,
        specification: Specification,
        netlist_path: Path,
        deterministic_testbench: TestBench | None,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        top_p: float = 1.0,
        include_deterministic_summary: bool,
        max_repairs: int = 2,
        knowledge_bundle: dict[str, Any] | None = None,
        knowledge_version: str | None = None,
        provider_mode: str = "UNKNOWN",
        scientific_llm_evidence: bool = False,
        request_overrides: dict[str, Any] | None = None,
    ) -> LLMPlanningOutcome:
        capability_payload, system_prompt, request_payload, prompt_sha = self.build_request_context(
            specification=specification,
            netlist_path=netlist_path,
            deterministic_testbench=deterministic_testbench,
            include_deterministic_summary=include_deterministic_summary,
            knowledge_bundle=knowledge_bundle,
            knowledge_version=knowledge_version,
            provider_mode=provider_mode,
            scientific_llm_evidence=scientific_llm_evidence,
            request_overrides=request_overrides,
        )
        raw_response, response_metadata = self._request_plan(
            system_prompt=system_prompt,
            request_payload=request_payload,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            top_p=top_p,
        )
        validation = self._validator.parse_and_validate(
            raw_response,
            specification=specification,
            netlist_path=netlist_path,
            expected_case_id=capability_payload.case_id,
        )
        repair_history: list[LLMRepairRecord] = []
        call_history: list[dict[str, Any]] = [dict(response_metadata)]
        initial_validation = validation.to_dict()

        repair_attempts = 0
        current_response = raw_response
        current_validation = validation
        while repair_attempts < max_repairs and not current_validation.is_valid:
            repair_attempts += 1
            repair_prompt = self._build_plan_repair_prompt(current_validation)
            current_response, response_metadata = self._request_plan(
                system_prompt=system_prompt,
                request_payload={
                    **request_payload,
                    "repair_prompt": repair_prompt,
                },
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                timeout_seconds=timeout_seconds,
            )
            call_history.append(dict(response_metadata))
            current_validation = self._validator.parse_and_validate(
                current_response,
                specification=specification,
                netlist_path=netlist_path,
                expected_case_id=capability_payload.case_id,
            )
            repair_history.append(
                LLMRepairRecord(
                    repair_status=RepairStatus.PLAN_REPAIR,
                    prompt=repair_prompt,
                    validation=current_validation.to_dict(),
                )
            )

        return LLMPlanningOutcome(
            request_payload=request_payload,
            system_prompt=system_prompt,
            prompt_sha256=prompt_sha,
            raw_response=current_response,
            validation=current_validation,
            repair_history=repair_history,
            provider_metadata=response_metadata,
            parsed_plan=current_validation.parsed_plan,
            call_history=call_history,
            initial_validation=initial_validation,
        )

    def repair_plan(
        self,
        *,
        previous_outcome: LLMPlanningOutcome,
        feedback: dict[str, Any],
        specification: Specification,
        netlist_path: Path,
        deterministic_testbench: TestBench | None,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        top_p: float = 1.0,
        include_deterministic_summary: bool,
        provider_mode: str = "UNKNOWN",
        scientific_llm_evidence: bool = False,
        knowledge_bundle: dict[str, Any] | None = None,
        knowledge_version: str | None = None,
        repair_status: RepairStatus = RepairStatus.EXECUTION_REPAIR,
    ) -> LLMPlanningOutcome:
        """Request one bounded repair using deterministic feedback.

        The previous plan and simulator/extractor diagnostics are context only.
        The prompt explicitly forbids threshold/DUT changes and forbids emitting a
        PASS/FAIL verdict.
        """
        capability_payload, system_prompt, request_payload, prompt_sha = self.build_request_context(
            specification=specification,
            netlist_path=netlist_path,
            deterministic_testbench=deterministic_testbench,
            include_deterministic_summary=include_deterministic_summary,
            knowledge_bundle=knowledge_bundle,
            knowledge_version=knowledge_version,
            provider_mode=provider_mode,
            scientific_llm_evidence=scientific_llm_evidence,
        )
        repair_prompt = self._build_execution_repair_prompt(feedback)
        request_payload = {
            **request_payload,
            "task": "Repair the previous TestbenchPlan using deterministic validation/SPICE feedback",
            "previous_plan_response": previous_outcome.raw_response,
            "feedback": feedback,
            "repair_prompt": repair_prompt,
        }
        raw_response, response_metadata = self._request_plan(
            system_prompt=system_prompt,
            request_payload=request_payload,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            top_p=top_p,
        )
        validation = self._validator.parse_and_validate(
            raw_response,
            specification=specification,
            netlist_path=netlist_path,
            expected_case_id=capability_payload.case_id,
        )
        repair_history = list(previous_outcome.repair_history)
        repair_history.append(
            LLMRepairRecord(
                repair_status=repair_status,
                prompt=repair_prompt,
                validation=validation.to_dict(),
            )
        )
        call_history = list(previous_outcome.call_history)
        call_history.append(dict(response_metadata))
        return LLMPlanningOutcome(
            request_payload=request_payload,
            system_prompt=system_prompt,
            prompt_sha256=prompt_sha,
            raw_response=raw_response,
            validation=validation,
            repair_history=repair_history,
            provider_metadata=response_metadata,
            parsed_plan=validation.parsed_plan,
            call_history=call_history,
            initial_validation=previous_outcome.initial_validation or previous_outcome.validation.to_dict(),
        )

    def build_request_context(
        self,
        *,
        specification: Specification,
        netlist_path: Path,
        deterministic_testbench: TestBench | None,
        include_deterministic_summary: bool,
        knowledge_bundle: dict[str, Any] | None = None,
        knowledge_version: str | None = None,
        provider_mode: str = "UNKNOWN",
        scientific_llm_evidence: bool = False,
        request_overrides: dict[str, Any] | None = None,
    ) -> tuple[Any, str, dict[str, Any], str]:
        capability_payload = self._capability_builder.build(
            specification,
            netlist_path=netlist_path,
            deterministic_testbench=deterministic_testbench if include_deterministic_summary else None,
        )
        system_prompt = self._prompt_path.read_text(encoding="utf-8")
        request_payload = {
            "task": "Generate a valid JSON TestbenchPlan",
            "case_id": capability_payload.case_id,
            "circuit_family": capability_payload.circuit_family,
            "available_nodes": capability_payload.available_nodes,
            "canonical_circuit_representation": capability_payload.canonical_circuit_representation,
            "supply_information": capability_payload.supply_information,
            "requested_metrics": capability_payload.requested_metrics,
            "supported_capabilities": capability_payload.to_dict()["supported_capabilities"],
            "normalized_specification": self._normalized_specification(specification),
            "deterministic_plan_summary": capability_payload.deterministic_plan_summary,
            "response_schema": TestbenchPlan.model_json_schema(),
            "provider_mode": provider_mode,
            "scientific_llm_evidence": scientific_llm_evidence,
            "knowledge_version": knowledge_version,
            "knowledge_bundle": knowledge_bundle or {},
            "knowledge_bundle_sha256": (knowledge_bundle or {}).get("knowledge_bundle_sha256", ""),
        }
        if request_overrides:
            request_payload.update(request_overrides)
        prompt_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        return capability_payload, system_prompt, request_payload, prompt_sha

    def _request_plan(
        self,
        *,
        system_prompt: str,
        request_payload: dict[str, Any],
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        top_p: float = 1.0,
    ) -> tuple[str, dict[str, Any]]:
        response = self._provider.generate(
            LLMRequest(
                system_prompt=system_prompt,
                user_payload=request_payload,
                response_format={"type": "json_object"},
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                timeout_seconds=timeout_seconds,
                metadata={},
            )
        )
        if response.finish_reason == "length":
            raise LLMTruncatedResponseError(
                "DeepSeek response was truncated",
                provider=response.provider,
                attempts=response.raw_metadata.get("attempts", []),
            )
        if not response.content.strip():
            raise LLMEmptyResponseError(
                "DeepSeek response was empty",
                provider=response.provider,
                attempts=response.raw_metadata.get("attempts", []),
            )
        return response.content, {
            **response.raw_metadata,
            "provider": response.provider,
            "model": response.model,
            "finish_reason": response.finish_reason,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "latency_seconds": response.latency_seconds,
        }

    @staticmethod
    def _normalized_specification(specification: Specification) -> dict[str, Any]:
        allowed_input_keys = {
            "vdd",
            "vss",
            "vcm",
            "input_nodes",
            "output_nodes",
            "cl",
            "rl",
            "temperature",
            "nominal_temperature",
            "input_amplitude",
            "input_frequency",
            "start_frequency",
            "stop_frequency",
            "points_per_decade",
            "pulse_width",
            "period",
            "rise_time",
            "fall_time",
        }
        sanitized_input_conditions = {
            key: value
            for key, value in specification.input_conditions.items()
            if key in allowed_input_keys
        }
        return {
            "name": specification.name,
            "circuit_type": specification.circuit_type.value,
            "performance_targets": specification.verification_performance_targets(),
            "input_conditions": sanitized_input_conditions,
            "test_categories": specification.test_categories,
            "measurement": specification.measurement,
        }

    @staticmethod
    def _build_execution_repair_prompt(feedback: dict[str, Any]) -> str:
        return "\n".join(
            [
                "The previous TestbenchPlan failed because of a verification-protocol error.",
                "Repair only the testbench plan.",
                "Do not modify the DUT, component values, specification thresholds, or requested metrics.",
                "Do not invent measured values and do not emit PASS/FAIL/COMPLIANT/NONCOMPLIANT.",
                "Choose nodes only from available_nodes and use only analyses allowed by the response schema.",
                "Return one corrected JSON TestbenchPlan only.",
                "",
                "Deterministic feedback:",
                json.dumps(feedback, sort_keys=True, ensure_ascii=True),
            ]
        )

    @staticmethod
    def _build_plan_repair_prompt(validation: LLMPlanValidationResult) -> str:
        issue_lines = [
            f"- {issue.field}: {issue.message}"
            for issue in validation.issues
        ]
        return "\n".join(
            [
                "The previous JSON TestbenchPlan failed deterministic validation.",
                "",
                "Validation errors:",
                *issue_lines,
                "",
                "Return one corrected JSON TestbenchPlan only.",
                "Preserve the case ID, requested metrics, circuit nodes, and",
                "specification thresholds.",
            ]
        )
