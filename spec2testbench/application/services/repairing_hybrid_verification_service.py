from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from spec2testbench.application.services.acp_benchmark_runner import (
    circuit_compliance,
    evaluate_contract,
    sha256_file,
)
from spec2testbench.application.services.llm_testbench_plan_validator import (
    LLMTestbenchPlanValidator,
)
from spec2testbench.application.services.testbench_plan_compiler import (
    CompiledTestbenchPlan,
    TestbenchPlanCompiler,
)
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


_FORBIDDEN_PLAN_KEYS = {
    "threshold",
    "thresholds",
    "operator",
    "comparison_operator",
    "verdict",
    "final_verdict",
    "compliance_status",
    "dut_netlist",
    "dut_components",
    "components",
    "performance_targets",
    "functional_requirements",
    "spec_checker_logic",
}


@dataclass
class RepairingHybridVerificationOutcome:
    attempts: list[dict[str, Any]] = field(default_factory=list)
    stopping_condition: str = "max_retries_reached"
    final_plan: Optional[TestbenchPlan] = None
    final_validation: dict[str, Any] = field(default_factory=lambda: {"status": "NOT_RUN", "issues": []})
    final_contract_gate: dict[str, Any] = field(default_factory=lambda: {"status": "NOT_RUN", "issues": []})
    compiled: Optional[CompiledTestbenchPlan] = None
    simulation_result: dict[str, Any] = field(default_factory=dict)
    criteria: list[Any] = field(default_factory=list)
    compliance_status: str = "NOT_EVALUATED"
    immutable_inputs: dict[str, Any] = field(default_factory=dict)
    repair_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def verification_completed(self) -> bool:
        return self.stopping_condition == "verification_success"

    def criteria_dicts(self) -> list[dict[str, Any]]:
        return [
            asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row)
            for row in self.criteria
        ]


class RepairingHybridVerificationService:
    """H1.3 controlled LLM-SPICE feedback and repair loop.

    Repairs are allowed only for the verification plan. A completed deterministic
    NONCOMPLIANT verdict is a successful verification and MUST NOT trigger repair.
    """

    def __init__(
        self,
        provider: Any,
        *,
        simulator: Optional[Any] = None,
        compiler: Optional[TestbenchPlanCompiler] = None,
        validator: Optional[LLMTestbenchPlanValidator] = None,
        max_retries: int = 2,
        ngspice_path: Optional[str] = None,
        timeout_seconds: float = 300.0,
        fault_injection: str = "none",
    ) -> None:
        if int(max_retries) < 0 or int(max_retries) > 2:
            raise ValueError("H1.3 protocol fixes max_retries to the range 0..2")
        allowed_faults = {
            "none",
            "validator_unknown_node_once",
            "contract_missing_metric_once",
            "spice_invalid_ac_start_once",
        }
        if fault_injection not in allowed_faults:
            raise ValueError(
                f"Unsupported H1.3 fault injection {fault_injection!r}; "
                f"choose one of {sorted(allowed_faults)}"
            )
        self.provider = provider
        self.simulator = simulator or PySpiceSimulator(
            ngspice_path=ngspice_path,
            allow_mock=False,
            timeout_seconds=timeout_seconds,
        )
        self.compiler = compiler or TestbenchPlanCompiler()
        self.validator = validator or LLMTestbenchPlanValidator()
        self.max_retries = int(max_retries)
        self.fault_injection = fault_injection

    @staticmethod
    def _canonical_sha256(obj: Any) -> str:
        text = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _executable_contract(specification: Specification) -> tuple[set[str], set[str]]:
        analysis_by_id = {
            str(item.get("id")): str(item.get("type", "")).upper()
            for item in specification.analyses
        }
        metrics: set[str] = set()
        analysis_types: set[str] = set()
        for req in specification.mandatory_requirements():
            if req.get("implementation_status") != "executable":
                continue
            metric = str(req.get("executable_metric") or req.get("metric") or "").strip()
            if metric:
                metrics.add(metric)
            analysis_id = str(req.get("analysis") or "")
            analysis_type = analysis_by_id.get(analysis_id, "")
            if analysis_type:
                analysis_types.add(analysis_type)
        return metrics, analysis_types

    def _contract_gate(self, specification: Specification, plan: TestbenchPlan) -> dict[str, Any]:
        required_metrics, required_analysis_types = self._executable_contract(specification)
        planned_metrics = {m.metric_name for m in plan.measurements}
        missing = sorted(required_metrics - planned_metrics)
        issues: list[dict[str, Any]] = []
        if len(required_analysis_types) > 1:
            issues.append(
                {
                    "code": "H1_PHASE3_MULTI_ANALYSIS_UNSUPPORTED",
                    "analysis_types": sorted(required_analysis_types),
                }
            )
        if required_analysis_types and plan.analysis_type.value not in required_analysis_types:
            issues.append(
                {
                    "code": "H1_ANALYSIS_TYPE_MISMATCH",
                    "plan_analysis_type": plan.analysis_type.value,
                    "required_analysis_types": sorted(required_analysis_types),
                }
            )
        if missing:
            issues.append({"code": "H1_MISSING_EXECUTABLE_METRICS", "metrics": missing})
        return {
            "status": "VALID" if not issues else "INVALID",
            "issues": issues,
            "required_executable_metrics": sorted(required_metrics),
            "planned_metrics": sorted(planned_metrics),
            "required_analysis_types": sorted(required_analysis_types),
            "plan_analysis_type": plan.analysis_type.value,
        }

    @staticmethod
    def _forbidden_fields(raw: Any, prefix: str = "$") -> list[str]:
        found: list[str] = []
        if isinstance(raw, dict):
            for key, value in raw.items():
                path = f"{prefix}.{key}"
                if str(key).lower() in _FORBIDDEN_PLAN_KEYS:
                    found.append(path)
                found.extend(RepairingHybridVerificationService._forbidden_fields(value, path))
        elif isinstance(raw, list):
            for index, value in enumerate(raw):
                found.extend(
                    RepairingHybridVerificationService._forbidden_fields(
                        value, f"{prefix}[{index}]"
                    )
                )
        return found

    def _stamp_framework_provenance(self, plan: TestbenchPlan) -> TestbenchPlan:
        stamped = plan.model_copy(deep=True)
        stamped.provider_mode = str(getattr(self.provider, "mode", "UNKNOWN"))
        stamped.scientific_llm_evidence = bool(
            getattr(self.provider, "scientific_llm_evidence", False)
        )
        return stamped

    def _inject_controlled_fault(
        self, plan: TestbenchPlan, attempt_id: int
    ) -> tuple[TestbenchPlan, Optional[dict[str, Any]]]:
        if attempt_id != 0 or self.fault_injection == "none":
            return plan, None
        mutated = plan.model_copy(deep=True)
        if self.fault_injection == "validator_unknown_node_once":
            mutated.observed_nodes = ["H1_CONTROLLED_UNKNOWN_NODE"]
            return mutated, {
                "fault_id": self.fault_injection,
                "stage": "validator",
                "description": "Replace observed_nodes with one non-existent node on attempt 0 only.",
            }
        if self.fault_injection == "contract_missing_metric_once":
            if len(mutated.measurements) < 2:
                raise RuntimeError(
                    "contract_missing_metric_once requires at least two planned measurements"
                )
            removed = mutated.measurements[-1].metric_name
            mutated.measurements = mutated.measurements[:-1]
            return mutated, {
                "fault_id": self.fault_injection,
                "stage": "contract_gate",
                "description": "Drop one executable metric from attempt 0 only.",
                "removed_metric": removed,
            }
        if self.fault_injection == "spice_invalid_ac_start_once":
            if mutated.analysis_type.value != "AC":
                raise RuntimeError(
                    "spice_invalid_ac_start_once requires an AC verification plan"
                )
            original = mutated.simulation_parameters.frequency_start_hz
            mutated.simulation_parameters.frequency_start_hz = 0.0
            return mutated, {
                "fault_id": self.fault_injection,
                "stage": "spice",
                "description": (
                    "Set AC start frequency to 0 Hz on attempt 0 only. "
                    "The structural validator and contract gate intentionally do not "
                    "repair this; ngspice must expose the execution failure."
                ),
                "original_frequency_start_hz": original,
                "injected_frequency_start_hz": 0.0,
            }
        return mutated, None

    @staticmethod
    def _metrics_from_criteria(criteria: list[Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for row in criteria:
            metric = getattr(row, "metric", None)
            value = getattr(row, "measured_value", None)
            if metric and value is not None:
                out[str(metric)] = value
        return out

    @staticmethod
    def _repair_feedback(
        *,
        trigger: str,
        attempt_id: int,
        previous_plan: Optional[TestbenchPlan],
        issues: Optional[list[dict[str, Any]]] = None,
        simulation_result: Optional[dict[str, Any]] = None,
        missing_metrics: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        feedback: dict[str, Any] = {
            "trigger": trigger,
            "failed_attempt": attempt_id,
            "instruction": (
                "Return a complete corrected TestbenchPlan. Repair only the verification "
                "plan issue described here. Do not alter DUT, thresholds, operators, or verdicts."
            ),
            "issues": issues or [],
            "missing_runtime_metrics": missing_metrics or [],
        }
        if previous_plan is not None:
            feedback["previous_plan"] = previous_plan.model_dump(mode="json")
        if simulation_result:
            feedback["spice"] = {
                "execution_status": simulation_result.get("execution_status"),
                "error_type": simulation_result.get("error_type"),
                "error_message": simulation_result.get("error_message"),
            }
        return feedback

    @staticmethod
    def _attempt_record(
        *,
        attempt_id: int,
        raw_response: Any,
        provider_metadata: dict[str, Any],
        plan: Optional[TestbenchPlan],
        validation: dict[str, Any],
        contract_gate: dict[str, Any],
        simulation_result: Optional[dict[str, Any]],
        metrics_obtained: dict[str, Any],
        incoming_repair_trigger: Optional[str],
        outgoing_repair_trigger: Optional[str],
        repair_action: Optional[str],
        fault_injection: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "attempt_id": attempt_id,
            "request_sha256": provider_metadata.get("request_sha256"),
            "response_sha256": provider_metadata.get("response_sha256"),
            "plan_sha256": (
                RepairingHybridVerificationService._canonical_sha256(
                    plan.model_dump(mode="json")
                )
                if plan is not None
                else None
            ),
            "validation_status": validation.get("status"),
            "validation_issues": validation.get("issues", []),
            "contract_gate_status": contract_gate.get("status"),
            "contract_gate_issues": contract_gate.get("issues", []),
            "spice_execution_status": (
                simulation_result.get("execution_status") if simulation_result else "NOT_RUN"
            ),
            "spice_error_type": (
                simulation_result.get("error_type") if simulation_result else None
            ),
            "spice_error_message": (
                simulation_result.get("error_message") if simulation_result else None
            ),
            "metrics_obtained": metrics_obtained,
            "incoming_repair_trigger": incoming_repair_trigger,
            "repair_trigger": outgoing_repair_trigger,
            "repair_action": repair_action,
            "tokens": provider_metadata.get("usage", {}),
            "provider_metadata": provider_metadata,
            "fault_injection": fault_injection,
            "raw_response": raw_response,
            "parsed_plan": plan.model_dump(mode="json") if plan is not None else None,
        }

    @staticmethod
    def _summary(attempts: list[dict[str, Any]], stopping_condition: str) -> dict[str, Any]:
        n = len(attempts)
        valid = sum(a.get("validation_status") == "VALID" for a in attempts)
        spice_attempts = [a for a in attempts if a.get("spice_execution_status") != "NOT_RUN"]
        spice_success = sum(a.get("spice_execution_status") == "SUCCESS" for a in spice_attempts)
        repairs = max(0, n - 1)
        final_success = stopping_condition == "verification_success"
        return {
            "attempt_count": n,
            "repair_attempt_count": repairs,
            "plan_validity_rate": (valid / n) if n else 0.0,
            "execution_success_rate": (
                spice_success / len(spice_attempts) if spice_attempts else 0.0
            ),
            "repair_success_rate": (
                1.0 if repairs and final_success else 0.0 if repairs else None
            ),
            "first_repair_success_rate": (
                1.0 if repairs == 1 and final_success else 0.0 if repairs else None
            ),
            "mean_retries": float(repairs),
            "unsafe_repair_rejection_rate": (
                1.0 if stopping_condition == "unsafe_repair_rejected" else 0.0
            ),
        }

    def run(
        self,
        specification: Specification,
        netlist_path: Path,
        output_dir: Path,
        deterministic_plan: dict[str, Any],
    ) -> RepairingHybridVerificationOutcome:
        netlist_path = Path(netlist_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        spec_sha_before = specification.sha256()
        dut_sha_before = sha256_file(netlist_path)
        expected_dut_sha = (specification.provenance.get("dut") or {}).get("sha256")
        immutable_inputs = {
            "specification_sha256_before": spec_sha_before,
            "netlist_sha256_before": dut_sha_before,
            "expected_netlist_sha256": expected_dut_sha,
            "dut_hash_matches_frozen_spec": expected_dut_sha is None
            or expected_dut_sha == dut_sha_before,
        }

        if not immutable_inputs["dut_hash_matches_frozen_spec"]:
            return RepairingHybridVerificationOutcome(
                attempts=[],
                stopping_condition="unsafe_repair_rejected",
                immutable_inputs=immutable_inputs,
                repair_summary=self._summary([], "unsafe_repair_rejected"),
            )

        base_payload = {
            "case_id": specification.case_id,
            "specification": specification.canonical_dict(),
            "deterministic_plan": deterministic_plan,
        }
        repair_feedback: Optional[dict[str, Any]] = None
        incoming_trigger: Optional[str] = None
        attempts: list[dict[str, Any]] = []
        final_plan: Optional[TestbenchPlan] = None
        final_validation: dict[str, Any] = {"status": "NOT_RUN", "issues": []}
        final_gate: dict[str, Any] = {"status": "NOT_RUN", "issues": []}
        final_compiled: Optional[CompiledTestbenchPlan] = None
        final_simulation: dict[str, Any] = {}
        final_criteria: list[Any] = []
        final_compliance = "NOT_EVALUATED"
        stopping_condition = "max_retries_reached"

        for attempt_id in range(self.max_retries + 1):
            if specification.sha256() != spec_sha_before or sha256_file(netlist_path) != dut_sha_before:
                stopping_condition = "unsafe_repair_rejected"
                break

            payload = dict(base_payload)
            if repair_feedback is not None:
                payload["repair"] = repair_feedback

            raw = self.provider.generate(payload)
            metadata = dict(getattr(self.provider, "last_call_metadata", {}) or {})
            forbidden = self._forbidden_fields(raw)
            if forbidden:
                validation = {
                    "status": "INVALID",
                    "issues": [
                        {"code": "UNSAFE_REPAIR_FIELD", "fields": forbidden}
                    ],
                }
                record = self._attempt_record(
                    attempt_id=attempt_id,
                    raw_response=raw,
                    provider_metadata=metadata,
                    plan=None,
                    validation=validation,
                    contract_gate={"status": "NOT_RUN", "issues": []},
                    simulation_result=None,
                    metrics_obtained={},
                    incoming_repair_trigger=incoming_trigger,
                    outgoing_repair_trigger=None,
                    repair_action=(
                        f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                    ),
                    fault_injection=None,
                )
                attempts.append(record)
                final_validation = validation
                stopping_condition = "unsafe_repair_rejected"
                break

            try:
                plan = (
                    TestbenchPlan.model_validate_json(raw)
                    if isinstance(raw, str)
                    else TestbenchPlan.model_validate(raw)
                )
                plan = self._stamp_framework_provenance(plan)
            except Exception as exc:
                validation = {
                    "status": "INVALID",
                    "issues": [{"code": "JSON_SCHEMA_ERROR", "message": str(exc)}],
                }
                trigger = "validator_rejection"
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=None,
                        validation=validation,
                        contract_gate={"status": "NOT_RUN", "issues": []},
                        simulation_result=None,
                        metrics_obtained={},
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=trigger,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=None,
                    )
                )
                final_validation = validation
                if attempt_id >= self.max_retries:
                    stopping_condition = "max_retries_reached"
                    break
                repair_feedback = self._repair_feedback(
                    trigger=trigger,
                    attempt_id=attempt_id,
                    previous_plan=None,
                    issues=validation["issues"],
                )
                incoming_trigger = trigger
                continue

            plan, injected_fault = self._inject_controlled_fault(plan, attempt_id)
            validation = self.validator.validate(plan, specification, netlist_path)
            final_plan = plan
            final_validation = validation
            if validation.get("status") != "VALID":
                trigger = "validator_rejection"
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=plan,
                        validation=validation,
                        contract_gate={"status": "NOT_RUN", "issues": []},
                        simulation_result=None,
                        metrics_obtained={},
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=trigger,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=injected_fault,
                    )
                )
                if attempt_id >= self.max_retries:
                    stopping_condition = "max_retries_reached"
                    break
                repair_feedback = self._repair_feedback(
                    trigger=trigger,
                    attempt_id=attempt_id,
                    previous_plan=plan,
                    issues=validation.get("issues", []),
                )
                incoming_trigger = trigger
                continue

            gate = self._contract_gate(specification, plan)
            final_gate = gate
            if gate.get("status") != "VALID":
                trigger = "contract_gate_rejection"
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=plan,
                        validation=validation,
                        contract_gate=gate,
                        simulation_result=None,
                        metrics_obtained={},
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=trigger,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=injected_fault,
                    )
                )
                if attempt_id >= self.max_retries:
                    stopping_condition = "max_retries_reached"
                    break
                repair_feedback = self._repair_feedback(
                    trigger=trigger,
                    attempt_id=attempt_id,
                    previous_plan=plan,
                    issues=gate.get("issues", []),
                )
                incoming_trigger = trigger
                continue

            compiled = self.compiler.compile(plan, specification, netlist_path)
            simulation = self.simulator.run(
                netlist_path,
                compiled.testbench,
                output_dir=output_dir / f"attempt_{attempt_id}" / "simulation",
            )
            final_compiled = compiled
            final_simulation = dict(simulation)

            spec_sha_after = specification.sha256()
            dut_sha_after = sha256_file(netlist_path)
            immutable_inputs.update(
                {
                    "specification_sha256_after": spec_sha_after,
                    "netlist_sha256_after": dut_sha_after,
                    "specification_unchanged": spec_sha_before == spec_sha_after,
                    "dut_unchanged": dut_sha_before == dut_sha_after,
                }
            )
            if not immutable_inputs["specification_unchanged"] or not immutable_inputs["dut_unchanged"]:
                final_simulation.update(
                    {
                        "success": False,
                        "execution_status": "ERROR",
                        "error_type": "immutable_input_changed",
                        "error_message": "Specification or DUT changed during H1.3 execution.",
                    }
                )
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=plan,
                        validation=validation,
                        contract_gate=gate,
                        simulation_result=final_simulation,
                        metrics_obtained={},
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=None,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=injected_fault,
                    )
                )
                stopping_condition = "unsafe_repair_rejected"
                break

            execution_status = str(final_simulation.get("execution_status", "ERROR"))
            criteria = evaluate_contract(specification, final_simulation, execution_status)
            compliance = circuit_compliance(criteria)
            metrics_obtained = self._metrics_from_criteria(criteria)
            final_criteria = criteria
            final_compliance = compliance

            if execution_status != "SUCCESS":
                trigger = "spice_execution_error"
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=plan,
                        validation=validation,
                        contract_gate=gate,
                        simulation_result=final_simulation,
                        metrics_obtained=metrics_obtained,
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=trigger,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=injected_fault,
                    )
                )
                if attempt_id >= self.max_retries:
                    stopping_condition = "max_retries_reached"
                    break
                repair_feedback = self._repair_feedback(
                    trigger=trigger,
                    attempt_id=attempt_id,
                    previous_plan=plan,
                    simulation_result=final_simulation,
                )
                incoming_trigger = trigger
                continue

            required_metrics, _ = self._executable_contract(specification)
            missing_runtime = sorted(required_metrics - set(metrics_obtained))
            if missing_runtime:
                trigger = "missing_runtime_evidence"
                attempts.append(
                    self._attempt_record(
                        attempt_id=attempt_id,
                        raw_response=raw,
                        provider_metadata=metadata,
                        plan=plan,
                        validation=validation,
                        contract_gate=gate,
                        simulation_result=final_simulation,
                        metrics_obtained=metrics_obtained,
                        incoming_repair_trigger=incoming_trigger,
                        outgoing_repair_trigger=trigger,
                        repair_action=(
                            f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                        ),
                        fault_injection=injected_fault,
                    )
                )
                if attempt_id >= self.max_retries:
                    stopping_condition = "max_retries_reached"
                    break
                repair_feedback = self._repair_feedback(
                    trigger=trigger,
                    attempt_id=attempt_id,
                    previous_plan=plan,
                    missing_metrics=missing_runtime,
                )
                incoming_trigger = trigger
                continue

            attempts.append(
                self._attempt_record(
                    attempt_id=attempt_id,
                    raw_response=raw,
                    provider_metadata=metadata,
                    plan=plan,
                    validation=validation,
                    contract_gate=gate,
                    simulation_result=final_simulation,
                    metrics_obtained=metrics_obtained,
                    incoming_repair_trigger=incoming_trigger,
                    outgoing_repair_trigger=None,
                    repair_action=(
                        f"llm_replan_from_{incoming_trigger}" if incoming_trigger else None
                    ),
                    fault_injection=injected_fault,
                )
            )
            # A deterministic NONCOMPLIANT verdict is final evidence, not a repair trigger.
            stopping_condition = "verification_success"
            break

        return RepairingHybridVerificationOutcome(
            attempts=attempts,
            stopping_condition=stopping_condition,
            final_plan=final_plan,
            final_validation=final_validation,
            final_contract_gate=final_gate,
            compiled=final_compiled,
            simulation_result=final_simulation,
            criteria=final_criteria,
            compliance_status=final_compliance,
            immutable_inputs=immutable_inputs,
            repair_summary=self._summary(attempts, stopping_condition),
        )
