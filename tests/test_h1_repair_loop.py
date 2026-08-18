from pathlib import Path

from spec2testbench.application.services.repairing_hybrid_verification_service import (
    RepairingHybridVerificationService,
)
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench.llm_guided_synthesis import FrameworkGenerator


class SequenceProvider:
    mode = "DEEPSEEK_LIVE"
    scientific_llm_evidence = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.last_call_metadata = {}

    def generate(self, payload):
        self.calls.append(payload)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        self.last_call_metadata = {
            "provider": "deepseek",
            "provider_mode": "DEEPSEEK_LIVE",
            "response_model": "deepseek-v4-flash",
            "request_sha256": f"req-{len(self.calls)}",
            "response_sha256": f"res-{len(self.calls)}",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        response = self.responses[index]
        return response() if callable(response) else response


class SequenceSimulator:
    is_available = True
    allow_mock = False

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def run(self, netlist_path, testbench, output_dir=None):
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        result = dict(self.results[index])
        result.setdefault("artifact_dir", str(output_dir))
        result.setdefault("executed_deck_path", str(Path(output_dir or ".") / "executed_testbench.ckt"))
        return result


def p10_context():
    spec_path = Path("benchmark/analogcoder_pro/specs/p10_lowpass.yaml")
    netlist = Path("benchmark/analogcoder_pro/p10_lowpass.cir")
    spec = Specification.from_yaml(spec_path)
    seed = FrameworkGenerator().build_plan(spec)
    plan = seed.model_copy(deep=True)
    if "lowpass_monotonicity_percent" not in {m.metric_name for m in plan.measurements}:
        second = plan.measurements[0].model_copy(deep=True)
        second.metric_name = "lowpass_monotonicity_percent"
        second.expected_unit = "%"
        plan.measurements.append(second)
    return spec, netlist, seed, plan


def success_result(attenuation=115.0, monotonicity=100.0):
    return {
        "success": True,
        "execution_status": "SUCCESS",
        "simulation_mode": "REAL",
        "metrics": {
            "lowpass_attenuation_db": attenuation,
            "lowpass_monotonicity_percent": monotonicity,
        },
        "native_metrics": {},
        "ac": {},
        "dc": {},
        "tran": {},
        "transient": {},
        "fourier": {},
        "currents": {},
    }


def error_result():
    return {
        "success": False,
        "execution_status": "ERROR",
        "simulation_mode": "REAL",
        "error_type": "ngspice_error",
        "error_message": "controlled ngspice failure",
        "metrics": {},
        "native_metrics": {},
        "ac": {},
        "dc": {},
        "tran": {},
        "transient": {},
        "fourier": {},
        "currents": {},
    }


def test_contract_gate_rejection_is_repaired_before_spice(tmp_path):
    spec, netlist, seed, plan = p10_context()
    bad = plan.model_copy(deep=True)
    bad.measurements = bad.measurements[:1]
    provider = SequenceProvider([
        bad.model_dump(mode="json"),
        plan.model_dump(mode="json"),
    ])
    simulator = SequenceSimulator([success_result()])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert len(out.attempts) == 2
    assert out.attempts[0]["repair_trigger"] == "contract_gate_rejection"
    assert out.attempts[1]["incoming_repair_trigger"] == "contract_gate_rejection"
    assert simulator.calls == 1
    assert out.compliance_status == "COMPLIANT"


def test_validator_rejection_is_repaired_before_spice(tmp_path):
    spec, netlist, seed, plan = p10_context()
    bad = plan.model_copy(deep=True)
    bad.observed_nodes = ["hallucinated_node"]
    provider = SequenceProvider([bad.model_dump(mode="json"), plan.model_dump(mode="json")])
    simulator = SequenceSimulator([success_result()])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert out.attempts[0]["repair_trigger"] == "validator_rejection"
    assert simulator.calls == 1


def test_spice_error_feedback_retries_and_succeeds(tmp_path):
    spec, netlist, seed, plan = p10_context()
    provider = SequenceProvider([plan.model_dump(mode="json"), plan.model_dump(mode="json")])
    simulator = SequenceSimulator([error_result(), success_result()])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert out.attempts[0]["repair_trigger"] == "spice_execution_error"
    assert out.attempts[1]["incoming_repair_trigger"] == "spice_execution_error"
    assert simulator.calls == 2


def test_missing_runtime_evidence_triggers_repair(tmp_path):
    spec, netlist, seed, plan = p10_context()
    provider = SequenceProvider([plan.model_dump(mode="json"), plan.model_dump(mode="json")])
    incomplete = success_result()
    incomplete["metrics"] = {"lowpass_attenuation_db": 115.0}
    simulator = SequenceSimulator([incomplete, success_result()])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert out.attempts[0]["repair_trigger"] == "missing_runtime_evidence"
    assert simulator.calls == 2


def test_noncompliant_is_final_and_never_repaired(tmp_path):
    spec, netlist, seed, plan = p10_context()
    provider = SequenceProvider([plan.model_dump(mode="json")])
    simulator = SequenceSimulator([success_result(attenuation=1.0, monotonicity=50.0)])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert out.compliance_status == "NONCOMPLIANT"
    assert len(out.attempts) == 1
    assert out.attempts[0]["repair_trigger"] is None
    assert len(provider.calls) == 1


def test_max_retries_is_hard_stop(tmp_path):
    spec, netlist, seed, plan = p10_context()
    provider = SequenceProvider([plan.model_dump(mode="json")] * 3)
    simulator = SequenceSimulator([error_result()] * 3)
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "max_retries_reached"
    assert len(out.attempts) == 3
    assert simulator.calls == 3
    assert len(provider.calls) == 3


def test_unsafe_plan_field_is_rejected_without_spice(tmp_path):
    spec, netlist, seed, plan = p10_context()
    raw = plan.model_dump(mode="json")
    raw["threshold"] = 0.0
    provider = SequenceProvider([raw])
    simulator = SequenceSimulator([success_result()])
    out = RepairingHybridVerificationService(
        provider, simulator=simulator, max_retries=2
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "unsafe_repair_rejected"
    assert simulator.calls == 0
    assert out.attempts[0]["validation_issues"][0]["code"] == "UNSAFE_REPAIR_FIELD"


def test_controlled_contract_fault_is_applied_once_then_repaired(tmp_path):
    spec, netlist, seed, plan = p10_context()
    provider = SequenceProvider([plan.model_dump(mode="json"), plan.model_dump(mode="json")])
    simulator = SequenceSimulator([success_result()])
    out = RepairingHybridVerificationService(
        provider,
        simulator=simulator,
        max_retries=2,
        fault_injection="contract_missing_metric_once",
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.stopping_condition == "verification_success"
    assert out.attempts[0]["fault_injection"]["fault_id"] == "contract_missing_metric_once"
    assert out.attempts[0]["repair_trigger"] == "contract_gate_rejection"
    assert out.attempts[1]["fault_injection"] is None
    assert simulator.calls == 1
