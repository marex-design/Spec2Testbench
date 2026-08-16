from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ...domain.entities.specification import Specification
from ...domain.value_objects.llm_status import LLMPlanValidationStatus, RepairStatus
from ...infrastructure.testbench.testbench_generator import TestBenchGenerator
from ..ports.llm_provider import LLMProviderError
from .llm_generation_service import LLMGenerationService, LLMPlanningOutcome
from .testbench_plan_compiler import TestbenchPlanCompiler


DEFAULT_MAX_RETRIES = 3


class FeedbackKind(str, Enum):
    PLAN_VALIDATION_ERROR = "PLAN_VALIDATION_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    SIMULATION_ERROR = "SIMULATION_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DUT_MUTATION_ERROR = "DUT_MUTATION_ERROR"
    SPECIFICATION_MUTATION_ERROR = "SPECIFICATION_MUTATION_ERROR"
    ELECTRICAL_NONCOMPLIANCE = "ELECTRICAL_NONCOMPLIANCE"
    SUCCESS = "SUCCESS"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


@dataclass(frozen=True)
class RetryPolicy:
    """One shared repair budget for protocol/testbench failures.

    Provider-level transport retries are separate and remain the responsibility of
    the provider adapter. `max_retries` counts LLM *repair* calls after the initial
    planner call.
    """

    max_retries: int = DEFAULT_MAX_RETRIES
    retryable_feedback: frozenset[FeedbackKind] = frozenset(
        {
            FeedbackKind.PLAN_VALIDATION_ERROR,
            FeedbackKind.COMPILATION_ERROR,
            FeedbackKind.SIMULATION_ERROR,
            FeedbackKind.EXTRACTION_ERROR,
        }
    )

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.max_retries > 10:
            raise ValueError("max_retries > 10 is blocked by the scientific safety policy")


@dataclass
class FeedbackEvent:
    attempt_index: int
    kind: FeedbackKind
    retryable: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "kind": self.kind.value,
            "retryable": self.retryable,
            "summary": self.summary,
            "details": self.details,
        }


@dataclass
class HybridAttempt:
    attempt_index: int
    plan_validation_status: str
    plan_valid: bool
    compiled: bool = False
    simulation_success: bool = False
    execution_status: str = ""
    measurement_status: str = ""
    compliance_status: str = "NOT_EVALUATED"
    feedback: FeedbackEvent | None = None
    testbench_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "attempt_index": self.attempt_index,
            "plan_validation_status": self.plan_validation_status,
            "plan_valid": self.plan_valid,
            "compiled": self.compiled,
            "simulation_success": self.simulation_success,
            "execution_status": self.execution_status,
            "measurement_status": self.measurement_status,
            "compliance_status": self.compliance_status,
            "testbench_sha256": self.testbench_sha256,
        }
        payload["feedback"] = self.feedback.to_dict() if self.feedback else None
        return payload


@dataclass
class HybridVerificationResult:
    final_status: FeedbackKind
    planning_outcome: LLMPlanningOutcome
    report: Any | None
    simulation_results: dict[str, Any] | None
    attempts: list[HybridAttempt]
    repair_count: int
    llm_call_count: int
    dut_sha256_before: str
    dut_sha256_after: str
    specification_sha256_before: str
    specification_sha256_after: str
    threshold_sha256_before: str
    threshold_sha256_after: str
    invariants_ok: bool
    stopped_on_electrical_fail: bool

    def to_dict(self) -> dict[str, Any]:
        provider_calls = getattr(self.planning_outcome, "call_history", []) or []
        total_prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in provider_calls)
        total_completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in provider_calls)
        total_tokens = sum(int(item.get("total_tokens") or 0) for item in provider_calls)
        total_latency = sum(float(item.get("latency_seconds") or 0.0) for item in provider_calls)
        provider_transport_attempt_count = sum(len(item.get("attempts") or []) for item in provider_calls)
        provider_transport_retry_count = sum(max(len(item.get("attempts") or []) - 1, 0) for item in provider_calls)
        initial_validation = self.planning_outcome.initial_validation or self.planning_outcome.validation.to_dict()
        initial_status = str(initial_validation.get("status") or "")
        initial_json_valid = initial_status not in {
            LLMPlanValidationStatus.INVALID_JSON.value,
            LLMPlanValidationStatus.SCHEMA_ERROR.value,
        }
        initial_plan_valid = initial_status == LLMPlanValidationStatus.VALID.value
        return {
            "final_status": self.final_status.value,
            "repair_count": self.repair_count,
            "llm_call_count": self.llm_call_count,
            "attempt_count": len(self.attempts),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "dut_sha256_before": self.dut_sha256_before,
            "dut_sha256_after": self.dut_sha256_after,
            "specification_sha256_before": self.specification_sha256_before,
            "specification_sha256_after": self.specification_sha256_after,
            "threshold_sha256_before": self.threshold_sha256_before,
            "threshold_sha256_after": self.threshold_sha256_after,
            "invariants_ok": self.invariants_ok,
            "stopped_on_electrical_fail": self.stopped_on_electrical_fail,
            "provider": (self.planning_outcome.provider_metadata or {}).get("provider"),
            "model": (self.planning_outcome.provider_metadata or {}).get("model"),
            "prompt_sha256": self.planning_outcome.prompt_sha256,
            "initial_plan_status": initial_status,
            "initial_json_valid": initial_json_valid,
            "initial_plan_valid": initial_plan_valid,
            "initial_validation": initial_validation,
            "repair_history": [
                {
                    "repair_status": record.repair_status.value,
                    "prompt": record.prompt,
                    "validation": record.validation,
                }
                for record in self.planning_outcome.repair_history
            ],
            "json_valid": self.planning_outcome.validation.status
            not in {LLMPlanValidationStatus.INVALID_JSON, LLMPlanValidationStatus.SCHEMA_ERROR},
            "final_plan_valid": self.planning_outcome.validation.is_valid,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_llm_latency_seconds": total_latency,
            "provider_transport_attempt_count": provider_transport_attempt_count,
            "provider_transport_retry_count": provider_transport_retry_count,
        }


class ExecutionFeedbackClassifier:
    """Classifies only protocol/testbench failures as repairable.

    A successful simulation followed by a specification FAIL is deliberately not
    retryable: that is an electrical non-conformity, not a testbench defect.
    """

    NON_RETRYABLE_SIMULATION_MARKERS = (
        "ngspice executable not available",
        "ngspice_unavailable",
        "permission denied",
        "dut_mutation_error",
        "netlist_binding_mismatch",
    )

    @classmethod
    def from_simulation(cls, simulation_results: dict[str, Any]) -> FeedbackEvent:
        errors = [str(item) for item in simulation_results.get("errors", [])]
        error_type = str(simulation_results.get("error_type") or "")
        joined = "\n".join(errors + [error_type]).lower()
        retryable = not any(marker in joined for marker in cls.NON_RETRYABLE_SIMULATION_MARKERS)
        return FeedbackEvent(
            attempt_index=0,
            kind=FeedbackKind.SIMULATION_ERROR,
            retryable=retryable,
            summary="ngspice execution failed",
            details={
                "error_type": error_type,
                "errors": errors[:20],
                "returncode": simulation_results.get("ngspice_returncode"),
            },
        )

    @staticmethod
    def from_extraction(simulation_results: dict[str, Any], requested_metrics: list[str]) -> FeedbackEvent | None:
        metrics = simulation_results.get("metrics") or {}
        missing = [metric for metric in requested_metrics if metrics.get(metric) is None]
        measurement_status = str(simulation_results.get("measurement_status") or "")
        if not missing and measurement_status not in {"ERROR", "FAILED", "UNAVAILABLE"}:
            return None
        return FeedbackEvent(
            attempt_index=0,
            kind=FeedbackKind.EXTRACTION_ERROR,
            retryable=True,
            summary="simulation completed but required metric extraction is incomplete",
            details={
                "missing_metrics": missing,
                "measurement_status": measurement_status,
                "measurement_backend": simulation_results.get("measurement_backend"),
                "errors": [str(item) for item in simulation_results.get("errors", [])][:20],
            },
        )


class HybridFeedbackLoop:
    """Controlled LLM -> validator -> compiler -> SPICE -> feedback loop.

    Scientific invariants:
    - the LLM never emits or decides PASS/FAIL;
    - measured values come only from SPICE extraction backends;
    - specification thresholds are immutable during verification;
    - the DUT file is immutable during verification;
    - all plans pass deterministic node/analysis/metric validation before execution;
    - the repair budget is finite;
    - electrical non-compliance is terminal and is never sent as a design-change task.
    """

    def __init__(
        self,
        generation_service: LLMGenerationService,
        *,
        retry_policy: RetryPolicy | None = None,
        compiler: TestbenchPlanCompiler | None = None,
        pipeline_factory: Callable[[int], Any] | None = None,
    ) -> None:
        self._generation_service = generation_service
        self._retry_policy = retry_policy or RetryPolicy()
        self._compiler = compiler or TestbenchPlanCompiler()
        self._pipeline_factory = pipeline_factory

    def run(
        self,
        *,
        specification: Specification,
        netlist_path: Path,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        top_p: float = 1.0,
        include_deterministic_summary: bool = True,
        provider_mode: str = "UNKNOWN",
        scientific_llm_evidence: bool = False,
        knowledge_bundle: dict[str, Any] | None = None,
        knowledge_version: str | None = None,
        spec_path: Path | None = None,
    ) -> HybridVerificationResult:
        from ..usecases.run_verification import VerificationPipeline

        netlist_path = Path(netlist_path)
        if not netlist_path.exists():
            raise FileNotFoundError(f"DUT netlist not found: {netlist_path}")

        dut_before = self._sha256_file(netlist_path)
        spec_before = self._specification_sha(specification)
        threshold_before = self._threshold_sha(specification)
        deterministic_testbench = TestBenchGenerator(use_llm=False).generate(
            specification,
            netlist_path=netlist_path,
        )

        outcome = self._generation_service.generate_plan(
            specification=specification,
            netlist_path=netlist_path,
            deterministic_testbench=deterministic_testbench,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            include_deterministic_summary=include_deterministic_summary,
            max_repairs=0,
            knowledge_bundle=knowledge_bundle,
            knowledge_version=knowledge_version,
            provider_mode=provider_mode,
            scientific_llm_evidence=scientific_llm_evidence,
        )

        attempts: list[HybridAttempt] = []
        repairs_used = 0
        report = None
        simulation_results = None
        final_status = FeedbackKind.RETRY_EXHAUSTED
        stopped_on_electrical_fail = False

        while True:
            invariant_event = self._check_invariants(
                specification=specification,
                netlist_path=netlist_path,
                dut_before=dut_before,
                spec_before=spec_before,
                threshold_before=threshold_before,
                attempt_index=len(attempts),
            )
            if invariant_event is not None:
                attempts.append(
                    HybridAttempt(
                        attempt_index=len(attempts),
                        plan_validation_status=outcome.validation.status.value,
                        plan_valid=outcome.validation.is_valid,
                        feedback=invariant_event,
                    )
                )
                final_status = invariant_event.kind
                break

            if not outcome.validation.is_valid or outcome.parsed_plan is None:
                feedback = FeedbackEvent(
                    attempt_index=len(attempts),
                    kind=FeedbackKind.PLAN_VALIDATION_ERROR,
                    retryable=True,
                    summary="LLM plan failed deterministic validation",
                    details=outcome.validation.to_dict(),
                )
                attempt = HybridAttempt(
                    attempt_index=len(attempts),
                    plan_validation_status=outcome.validation.status.value,
                    plan_valid=False,
                    feedback=feedback,
                )
                attempts.append(attempt)
                if not self._can_retry(feedback, repairs_used):
                    final_status = FeedbackKind.RETRY_EXHAUSTED
                    break
                repairs_used += 1
                outcome = self._generation_service.repair_plan(
                    previous_outcome=outcome,
                    feedback=feedback.to_dict(),
                    specification=specification,
                    netlist_path=netlist_path,
                    deterministic_testbench=deterministic_testbench,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    include_deterministic_summary=include_deterministic_summary,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_llm_evidence,
                    knowledge_bundle=knowledge_bundle,
                    knowledge_version=knowledge_version,
                    repair_status=RepairStatus.PLAN_REPAIR,
                )
                continue

            attempt = HybridAttempt(
                attempt_index=len(attempts),
                plan_validation_status=outcome.validation.status.value,
                plan_valid=True,
            )
            try:
                compiled = self._compiler.compile(outcome.parsed_plan, specification=specification)
                attempt.compiled = True
                attempt.testbench_sha256 = hashlib.sha256(
                    json.dumps(compiled.testbench.to_dict(), sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
            except Exception as exc:  # compiler failures are protocol failures
                feedback = FeedbackEvent(
                    attempt_index=attempt.attempt_index,
                    kind=FeedbackKind.COMPILATION_ERROR,
                    retryable=True,
                    summary="validated plan could not be compiled into an executable testbench",
                    details={"error_type": type(exc).__name__, "message": str(exc)},
                )
                attempt.feedback = feedback
                attempts.append(attempt)
                if not self._can_retry(feedback, repairs_used):
                    final_status = FeedbackKind.RETRY_EXHAUSTED
                    break
                repairs_used += 1
                outcome = self._generation_service.repair_plan(
                    previous_outcome=outcome,
                    feedback=feedback.to_dict(),
                    specification=specification,
                    netlist_path=netlist_path,
                    deterministic_testbench=deterministic_testbench,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    include_deterministic_summary=include_deterministic_summary,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_llm_evidence,
                    knowledge_bundle=knowledge_bundle,
                    knowledge_version=knowledge_version,
                    repair_status=RepairStatus.EXECUTION_REPAIR,
                )
                continue

            pipeline = (
                self._pipeline_factory(int(timeout_seconds))
                if self._pipeline_factory is not None
                else VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=int(timeout_seconds))
            )
            pipeline.testbench_gen.generate = lambda spec, netlist_path=None: compiled.testbench
            simulation_results = pipeline._run_simulation_with_ngspice(netlist_path, compiled.testbench)
            post_execution_invariant = self._check_invariants(
                specification=specification,
                netlist_path=netlist_path,
                dut_before=dut_before,
                spec_before=spec_before,
                threshold_before=threshold_before,
                attempt_index=attempt.attempt_index,
            )
            if post_execution_invariant is not None:
                attempt.feedback = post_execution_invariant
                attempts.append(attempt)
                final_status = post_execution_invariant.kind
                break
            attempt.simulation_success = bool(simulation_results.get("success"))
            attempt.execution_status = str(simulation_results.get("execution_status") or "")
            attempt.measurement_status = str(simulation_results.get("measurement_status") or "")

            if not attempt.simulation_success:
                feedback = ExecutionFeedbackClassifier.from_simulation(simulation_results)
                feedback.attempt_index = attempt.attempt_index
                attempt.feedback = feedback
                attempts.append(attempt)
                if not self._can_retry(feedback, repairs_used):
                    final_status = feedback.kind if not feedback.retryable else FeedbackKind.RETRY_EXHAUSTED
                    break
                repairs_used += 1
                outcome = self._generation_service.repair_plan(
                    previous_outcome=outcome,
                    feedback=feedback.to_dict(),
                    specification=specification,
                    netlist_path=netlist_path,
                    deterministic_testbench=deterministic_testbench,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    include_deterministic_summary=include_deterministic_summary,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_llm_evidence,
                    knowledge_bundle=knowledge_bundle,
                    knowledge_version=knowledge_version,
                    repair_status=RepairStatus.EXECUTION_REPAIR,
                )
                continue

            extraction_feedback = ExecutionFeedbackClassifier.from_extraction(
                simulation_results,
                specification.verification_metric_names(),
            )
            if extraction_feedback is not None:
                extraction_feedback.attempt_index = attempt.attempt_index
                attempt.feedback = extraction_feedback
                attempts.append(attempt)
                if not self._can_retry(extraction_feedback, repairs_used):
                    final_status = FeedbackKind.RETRY_EXHAUSTED
                    break
                repairs_used += 1
                outcome = self._generation_service.repair_plan(
                    previous_outcome=outcome,
                    feedback=extraction_feedback.to_dict(),
                    specification=specification,
                    netlist_path=netlist_path,
                    deterministic_testbench=deterministic_testbench,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    include_deterministic_summary=include_deterministic_summary,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_llm_evidence,
                    knowledge_bundle=knowledge_bundle,
                    knowledge_version=knowledge_version,
                    repair_status=RepairStatus.METRIC_REPAIR,
                )
                continue

            report = pipeline.verify(
                specification,
                netlist_path=netlist_path,
                simulation_results=simulation_results,
                spec_path=spec_path,
            )
            attempt.compliance_status = report.compliance_status.value
            if report.compliance_status.value == "FAIL" or report.overall_verdict.value == "FAIL":
                feedback = FeedbackEvent(
                    attempt_index=attempt.attempt_index,
                    kind=FeedbackKind.ELECTRICAL_NONCOMPLIANCE,
                    retryable=False,
                    summary="SPICE execution succeeded and the deterministic SpecChecker found electrical non-compliance",
                    details={
                        "failed_metrics": list(report.failed_metrics),
                        "compliance_status": report.compliance_status.value,
                    },
                )
                attempt.feedback = feedback
                attempts.append(attempt)
                final_status = FeedbackKind.ELECTRICAL_NONCOMPLIANCE
                stopped_on_electrical_fail = True
                break

            success_feedback = FeedbackEvent(
                attempt_index=attempt.attempt_index,
                kind=FeedbackKind.SUCCESS,
                retryable=False,
                summary="validated testbench executed and required metrics were checked deterministically",
                details={"compliance_status": report.compliance_status.value},
            )
            attempt.feedback = success_feedback
            attempts.append(attempt)
            final_status = FeedbackKind.SUCCESS
            break

        dut_after = self._sha256_file(netlist_path)
        spec_after = self._specification_sha(specification)
        threshold_after = self._threshold_sha(specification)
        invariants_ok = (
            dut_before == dut_after
            and spec_before == spec_after
            and threshold_before == threshold_after
            and final_status not in {FeedbackKind.DUT_MUTATION_ERROR, FeedbackKind.SPECIFICATION_MUTATION_ERROR}
        )
        return HybridVerificationResult(
            final_status=final_status,
            planning_outcome=outcome,
            report=report,
            simulation_results=simulation_results,
            attempts=attempts,
            repair_count=repairs_used,
            llm_call_count=len(getattr(outcome, "call_history", []) or []),
            dut_sha256_before=dut_before,
            dut_sha256_after=dut_after,
            specification_sha256_before=spec_before,
            specification_sha256_after=spec_after,
            threshold_sha256_before=threshold_before,
            threshold_sha256_after=threshold_after,
            invariants_ok=invariants_ok,
            stopped_on_electrical_fail=stopped_on_electrical_fail,
        )

    def _can_retry(self, feedback: FeedbackEvent, repairs_used: int) -> bool:
        return (
            feedback.retryable
            and feedback.kind in self._retry_policy.retryable_feedback
            and repairs_used < self._retry_policy.max_retries
        )

    def _check_invariants(
        self,
        *,
        specification: Specification,
        netlist_path: Path,
        dut_before: str,
        spec_before: str,
        threshold_before: str,
        attempt_index: int,
    ) -> FeedbackEvent | None:
        if self._sha256_file(netlist_path) != dut_before:
            return FeedbackEvent(
                attempt_index=attempt_index,
                kind=FeedbackKind.DUT_MUTATION_ERROR,
                retryable=False,
                summary="DUT hash changed during verification",
            )
        if self._threshold_sha(specification) != threshold_before or self._specification_sha(specification) != spec_before:
            return FeedbackEvent(
                attempt_index=attempt_index,
                kind=FeedbackKind.SPECIFICATION_MUTATION_ERROR,
                retryable=False,
                summary="Specification or user threshold changed during verification",
            )
        return None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _specification_sha(specification: Specification) -> str:
        payload = json.dumps(specification.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _threshold_sha(specification: Specification) -> str:
        payload = json.dumps(specification.performance_targets, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
