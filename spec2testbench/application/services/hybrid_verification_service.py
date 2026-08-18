from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from spec2testbench.application.services.acp_benchmark_runner import (
    circuit_compliance,
    evaluate_contract,
    sha256_file,
)
from spec2testbench.application.services.llm_generation_service import (
    LLMGenerationOutcome,
    LLMGenerationService,
)
from spec2testbench.application.services.testbench_plan_compiler import (
    CompiledTestbenchPlan,
    TestbenchPlanCompiler,
)
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


@dataclass
class HybridVerificationOutcome:
    """One H1.2 hybrid execution with deterministic safety boundaries."""

    plan_outcome: LLMGenerationOutcome
    contract_gate: dict[str, Any]
    compiled: Optional[CompiledTestbenchPlan] = None
    simulation_result: dict[str, Any] = field(default_factory=dict)
    criteria: list[Any] = field(default_factory=list)
    compliance_status: str = "NOT_EVALUATED"
    immutable_inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def plan_valid(self) -> bool:
        return self.plan_outcome.validation.get("status") == "VALID"

    @property
    def gate_valid(self) -> bool:
        return self.contract_gate.get("status") == "VALID"

    @property
    def spice_executed(self) -> bool:
        return bool(self.simulation_result)

    def criteria_dicts(self) -> list[dict[str, Any]]:
        return [asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row) for row in self.criteria]


class HybridVerificationService:
    """H1.2: DeepSeek plan -> validator -> compiler -> ngspice -> deterministic verdict.

    Phase 2 deliberately supports a single analysis type per case. This keeps the
    first live hybrid experiment auditable. Multi-analysis planning belongs to a
    later phase and is rejected rather than silently approximated.
    """

    def __init__(
        self,
        provider: Any,
        *,
        simulator: Optional[Any] = None,
        compiler: Optional[TestbenchPlanCompiler] = None,
        max_plan_retries: int = 1,
        ngspice_path: Optional[str] = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.provider = provider
        self.simulator = simulator or PySpiceSimulator(
            ngspice_path=ngspice_path,
            allow_mock=False,
            timeout_seconds=timeout_seconds,
        )
        self.compiler = compiler or TestbenchPlanCompiler()
        self.max_plan_retries = int(max_plan_retries)

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

    def _contract_gate(self, specification: Specification, plan: Any) -> dict[str, Any]:
        required_metrics, required_analysis_types = self._executable_contract(specification)
        planned_metrics = {m.metric_name for m in plan.measurements}
        missing = sorted(required_metrics - planned_metrics)
        issues: list[dict[str, Any]] = []
        if len(required_analysis_types) > 1:
            issues.append(
                {
                    "code": "H1_PHASE2_MULTI_ANALYSIS_UNSUPPORTED",
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

    def run(
        self,
        specification: Specification,
        netlist_path: Path,
        output_dir: Path,
        deterministic_plan: dict[str, Any],
    ) -> HybridVerificationOutcome:
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
            "dut_hash_matches_frozen_spec": expected_dut_sha is None or expected_dut_sha == dut_sha_before,
        }

        if not immutable_inputs["dut_hash_matches_frozen_spec"]:
            invalid = LLMGenerationOutcome(
                parsed_plan=None,
                validation={"status": "INVALID", "issues": [{"code": "DUT_HASH_MISMATCH"}]},
                repair_history=[],
                raw_response=None,
                provider_metadata={},
            )
            return HybridVerificationOutcome(
                plan_outcome=invalid,
                contract_gate={"status": "INVALID", "issues": [{"code": "DUT_HASH_MISMATCH"}]},
                immutable_inputs=immutable_inputs,
            )

        plan_outcome = LLMGenerationService(
            self.provider,
            max_retries=self.max_plan_retries,
        ).generate_plan(specification, netlist_path, deterministic_plan)

        if plan_outcome.validation.get("status") != "VALID" or plan_outcome.parsed_plan is None:
            return HybridVerificationOutcome(
                plan_outcome=plan_outcome,
                contract_gate={"status": "NOT_RUN", "issues": []},
                immutable_inputs=immutable_inputs,
            )

        gate = self._contract_gate(specification, plan_outcome.parsed_plan)
        if gate["status"] != "VALID":
            return HybridVerificationOutcome(
                plan_outcome=plan_outcome,
                contract_gate=gate,
                immutable_inputs=immutable_inputs,
            )

        compiled = self.compiler.compile(plan_outcome.parsed_plan, specification, netlist_path)
        simulation_result = self.simulator.run(
            netlist_path,
            compiled.testbench,
            output_dir=output_dir / "simulation",
        )

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
            simulation_result = dict(simulation_result)
            simulation_result.update(
                {
                    "success": False,
                    "execution_status": "ERROR",
                    "error_type": "immutable_input_changed",
                    "error_message": "Specification or DUT changed during H1 execution.",
                }
            )

        execution_status = str(simulation_result.get("execution_status", "ERROR"))
        criteria = evaluate_contract(specification, simulation_result, execution_status)
        compliance = circuit_compliance(criteria)

        return HybridVerificationOutcome(
            plan_outcome=plan_outcome,
            contract_gate=gate,
            compiled=compiled,
            simulation_result=simulation_result,
            criteria=criteria,
            compliance_status=compliance,
            immutable_inputs=immutable_inputs,
        )
