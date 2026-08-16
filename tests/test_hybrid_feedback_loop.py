from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from spec2testbench.application.ports.llm_provider import LLMRequest, LLMResponse
from spec2testbench.application.services.evaluation_metrics import (
    compute_coverage,
    confusion_from_rows,
    llm_quality_summary,
)
from spec2testbench.application.services.hybrid_feedback_loop import (
    FeedbackKind,
    HybridFeedbackLoop,
    RetryPolicy,
)
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus
from spec2testbench.domain.value_objects.verdict import Verdict


P10_SPEC = Path("benchmark/analogcoder_pro/specs/p10_lowpass.yaml")
P10_NETLIST = Path("benchmark/analogcoder_pro/p10_lowpass.cir")


def load_spec() -> Specification:
    specification = Specification.from_yaml(P10_SPEC)
    specification.case_id = "hybrid_p10"
    specification.parent_circuit_id = "p10_lowpass"
    return specification


def valid_plan(*, output_node: str = "Vout") -> str:
    return json.dumps(
        {
            "case_id": "hybrid_p10",
            "analysis_type": "AC",
            "provider_mode": "STUB",
            "scientific_llm_evidence": False,
            "stimuli": [
                {
                    "source_name": "vin",
                    "target_node": "Vin",
                    "stimulus_type": "AC",
                    "parameters": {"magnitude": 1.0, "dc_value": 1.0},
                }
            ],
            "observed_nodes": [output_node],
            "measurements": [
                {
                    "metric_name": "lowpass_attenuation_db",
                    "analysis_type": "AC",
                    "input_node": "Vin",
                    "output_node": output_node,
                    "expected_unit": "dB",
                    "backend_preference": "NGSPICE_WRDATA",
                    "measurement_parameters": {},
                },
                {
                    "metric_name": "lowpass_monotonicity_percent",
                    "analysis_type": "AC",
                    "input_node": "Vin",
                    "output_node": output_node,
                    "expected_unit": "%",
                    "backend_preference": "NGSPICE_WRDATA",
                    "measurement_parameters": {},
                },
            ],
            "simulation_parameters": {
                "frequency_start_hz": 1.0,
                "frequency_stop_hz": 1_000_000_000.0,
                "points_per_decade": 20,
            },
            "concise_rationale": "Measure ACP low-pass attenuation and monotonicity from SPICE vectors.",
        }
    )



class SequenceProvider:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def list_models(self):
        return ["stub"]

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        content = self.responses.pop(0)
        return LLMResponse(
            content=content,
            provider="deepseek_stub",
            model=request.model,
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            latency_seconds=0.01,
            raw_metadata={"attempts": [{"attempt_number": 1, "final_status": "SUCCESS"}]},
        )


class FakePipeline:
    def __init__(self, simulations: list[dict], compliance: ComplianceStatus):
        self._simulations = simulations
        self._compliance = compliance
        self.testbench_gen = SimpleNamespace(generate=None)

    def _run_simulation_with_ngspice(self, netlist_path, testbench):
        return self._simulations.pop(0)

    def verify(self, specification, netlist_path=None, simulation_results=None, spec_path=None):
        overall = Verdict.FAIL if self._compliance == ComplianceStatus.FAIL else Verdict.PASS
        return SimpleNamespace(
            compliance_status=self._compliance,
            overall_verdict=overall,
            failed_metrics=["lowpass_attenuation_db"] if overall == Verdict.FAIL else [],
        )


def success_simulation():
    return {
        "success": True,
        "execution_status": "SUCCESS",
        "measurement_status": "SUCCESS",
        "measurement_backend": "NGSPICE_WRDATA",
        "metrics": {"lowpass_attenuation_db": 3.0, "lowpass_monotonicity_percent": 95.0},
        "errors": [],
    }


def test_spice_error_is_returned_to_llm_and_recovered():
    provider = SequenceProvider([valid_plan(), valid_plan()])
    simulations = [
        {
            "success": False,
            "execution_status": "ERROR",
            "error_type": "ngspice_error",
            "errors": ["Error: no such vector as v(vout_bad)"],
            "metrics": {},
        },
        success_simulation(),
    ]
    pipeline = FakePipeline(simulations, ComplianceStatus.PASS)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )

    result = loop.run(
        specification=load_spec(),
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
        provider_mode="STUB",
    )

    assert result.final_status == FeedbackKind.SUCCESS
    assert result.repair_count == 1
    assert result.llm_call_count == 2
    assert result.invariants_ok is True
    assert result.attempts[0].feedback.kind == FeedbackKind.SIMULATION_ERROR
    assert "no such vector" in json.dumps(provider.requests[1].user_payload).lower()


def test_unknown_node_plan_is_repaired_before_spice():
    provider = SequenceProvider([valid_plan(output_node="MadeUpNode"), valid_plan()])
    pipeline = FakePipeline([success_simulation()], ComplianceStatus.PASS)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )
    result = loop.run(
        specification=load_spec(),
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.SUCCESS
    assert result.repair_count == 1
    assert result.attempts[0].feedback.kind == FeedbackKind.PLAN_VALIDATION_ERROR
    assert "UNKNOWN_NODE" in json.dumps(result.attempts[0].feedback.details)


def test_electrical_fail_is_terminal_and_never_sent_for_design_repair():
    provider = SequenceProvider([valid_plan()])
    pipeline = FakePipeline([success_simulation()], ComplianceStatus.FAIL)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )
    result = loop.run(
        specification=load_spec(),
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.ELECTRICAL_NONCOMPLIANCE
    assert result.stopped_on_electrical_fail is True
    assert result.repair_count == 0
    assert result.llm_call_count == 1
    assert len(provider.requests) == 1


def test_retry_budget_is_finite():
    provider = SequenceProvider([valid_plan(output_node="MadeUpNode")] * 4)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: FakePipeline([], ComplianceStatus.PASS),
    )
    result = loop.run(
        specification=load_spec(),
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.RETRY_EXHAUSTED
    assert result.repair_count == 3
    assert result.llm_call_count == 4
    assert len(provider.requests) == 4


def test_coverage_confusion_and_llm_quality_metrics():
    rows = [
        {
            "case_id": "a",
            "requested_metric_count": 2,
            "evaluated_metric_count": 2,
            "requested_analysis_count": 1,
            "executed_analysis_count": 1,
            "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
            "compliance_status": "FAIL",
            "json_valid": True,
            "final_plan_valid": True,
            "execution_status": "SUCCESS",
            "repair_count": 1,
            "llm_call_count": 2,
            "total_tokens": 100,
            "total_llm_latency_seconds": 1.0,
            "issues": "UNKNOWN_NODE",
        },
        {
            "case_id": "b",
            "requested_metric_count": 2,
            "evaluated_metric_count": 1,
            "requested_analysis_count": 1,
            "executed_analysis_count": 0,
            "ground_truth_label": "GROUND_TRUTH_COMPLIANT",
            "compliance_status": "PASS",
            "json_valid": True,
            "final_plan_valid": True,
            "execution_status": "ERROR",
            "repair_count": 0,
            "llm_call_count": 1,
            "total_tokens": 50,
            "total_llm_latency_seconds": 0.5,
            "issues": "",
        },
    ]
    coverage = compute_coverage(rows)
    assert coverage.cov_circuits == 1.0
    assert coverage.cov_metrics == 0.75
    assert coverage.cov_analyses == 0.5

    matrix = confusion_from_rows(rows)
    assert matrix.tp == 1
    assert matrix.tn == 1
    assert matrix.fp == 0
    assert matrix.fn == 0

    quality = llm_quality_summary(rows)
    assert quality["runs"] == 2
    assert quality["json_valid_rate"] == 1.0
    assert quality["feedback_recovery_rate"] == 1.0
    assert quality["total_tokens"] == 150


def test_extraction_error_is_returned_to_llm_and_recovered():
    provider = SequenceProvider([valid_plan(), valid_plan()])
    simulations = [
        {
            "success": True,
            "execution_status": "SUCCESS",
            "measurement_status": "ERROR",
            "measurement_backend": "NGSPICE_WRDATA",
            "metrics": {},
            "errors": ["cutoff_frequency_hz was not extracted"],
        },
        success_simulation(),
    ]
    pipeline = FakePipeline(simulations, ComplianceStatus.PASS)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )
    result = loop.run(
        specification=load_spec(),
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.SUCCESS
    assert result.repair_count == 1
    assert result.attempts[0].feedback.kind == FeedbackKind.EXTRACTION_ERROR
    assert "missing_metrics" in json.dumps(provider.requests[1].user_payload)


def test_dut_mutation_is_terminal(tmp_path):
    copied_netlist = tmp_path / "dut.cir"
    copied_netlist.write_bytes(P10_NETLIST.read_bytes())
    provider = SequenceProvider([valid_plan()])

    class MutatingPipeline(FakePipeline):
        def _run_simulation_with_ngspice(self, netlist_path, testbench):
            Path(netlist_path).write_text(Path(netlist_path).read_text(encoding="utf-8") + "\n* forbidden mutation\n", encoding="utf-8")
            return success_simulation()

    pipeline = MutatingPipeline([], ComplianceStatus.PASS)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )
    result = loop.run(
        specification=load_spec(),
        netlist_path=copied_netlist,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.DUT_MUTATION_ERROR
    assert result.invariants_ok is False
    assert result.repair_count == 0
    assert len(provider.requests) == 1


def test_threshold_mutation_is_terminal():
    specification = load_spec()
    provider = SequenceProvider([valid_plan()])

    class ThresholdMutatingPipeline(FakePipeline):
        def _run_simulation_with_ngspice(self, netlist_path, testbench):
            specification.performance_targets["lowpass_attenuation_db"]["min"] = 0.0
            return success_simulation()

    pipeline = ThresholdMutatingPipeline([], ComplianceStatus.PASS)
    loop = HybridFeedbackLoop(
        LLMGenerationService(provider),
        retry_policy=RetryPolicy(max_retries=3),
        pipeline_factory=lambda timeout: pipeline,
    )
    result = loop.run(
        specification=specification,
        netlist_path=P10_NETLIST,
        model="stub",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=10,
    )
    assert result.final_status == FeedbackKind.SPECIFICATION_MUTATION_ERROR
    assert result.invariants_ok is False
    assert result.repair_count == 0


def test_confusion_excludes_uncertain_non_simulable_and_not_evaluated_rows():
    rows = [
        {"ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
        {"ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "FAIL"},
        {"ground_truth_label": "GROUND_TRUTH_NON_SIMULABLE", "compliance_status": "FAIL"},
        {"ground_truth_label": "GROUND_TRUTH_UNCERTAIN", "compliance_status": "PASS"},
        {"ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "NOT_EVALUATED"},
    ]
    matrix = confusion_from_rows(rows)
    assert (matrix.tp, matrix.tn, matrix.fp, matrix.fn) == (1, 1, 0, 0)
    assert matrix.excluded == 3
