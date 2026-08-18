from pathlib import Path

from spec2testbench.application.services.hybrid_verification_service import HybridVerificationService
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench.llm_guided_synthesis import FrameworkGenerator


class FakeProvider:
    mode = "DEEPSEEK_LIVE"
    scientific_llm_evidence = True

    def __init__(self, response):
        self.response = response
        self.last_call_metadata = {
            "provider": "deepseek",
            "provider_mode": "DEEPSEEK_LIVE",
            "response_model": "deepseek-v4-flash",
        }

    def generate(self, payload):
        return self.response


class FakeSimulator:
    is_available = True
    allow_mock = False

    def __init__(self):
        self.calls = 0
        self.last_testbench = None

    def run(self, netlist_path, testbench, output_dir=None):
        self.calls += 1
        self.last_testbench = testbench
        return {
            "success": True,
            "execution_status": "SUCCESS",
            "simulation_mode": "REAL",
            "metrics": {},
            "native_metrics": {},
            "ac": {
                "frequency": [1.0, 10.0, 100.0, 1000.0],
                "magnitude": [1.0, 0.8, 0.3, 0.05],
                "phase": [0.0, -10.0, -40.0, -80.0],
            },
            "dc": {},
            "tran": {},
            "transient": {},
            "fourier": {},
            "currents": {},
            "artifact_dir": str(output_dir),
            "executed_deck_path": str(Path(output_dir or ".") / "executed_testbench.ckt"),
        }


def p10_context():
    spec_path = Path("benchmark/analogcoder_pro/specs/p10_lowpass.yaml")
    netlist = Path("benchmark/analogcoder_pro/p10_lowpass.cir")
    spec = Specification.from_yaml(spec_path)
    seed = FrameworkGenerator().build_plan(spec)
    plan = seed.model_copy(deep=True)
    plan.provider_mode = "DETERMINISTIC"
    plan.scientific_llm_evidence = False
    if "lowpass_monotonicity_percent" not in {m.metric_name for m in plan.measurements}:
        first = plan.measurements[0].model_copy(deep=True)
        first.metric_name = "lowpass_monotonicity_percent"
        first.expected_unit = "%"
        plan.measurements.append(first)
    return spec, netlist, seed, plan


def test_h1_phase2_valid_plan_executes_spice_and_deterministic_checker(tmp_path):
    spec, netlist, seed, plan = p10_context()
    simulator = FakeSimulator()
    out = HybridVerificationService(
        FakeProvider(plan.model_dump(mode="json")),
        simulator=simulator,
        max_plan_retries=0,
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.plan_outcome.validation["status"] == "VALID"
    assert out.contract_gate["status"] == "VALID"
    assert out.plan_outcome.parsed_plan.provider_mode == "DEEPSEEK_LIVE"
    assert out.plan_outcome.parsed_plan.scientific_llm_evidence is True
    assert simulator.calls == 1
    assert out.simulation_result["execution_status"] == "SUCCESS"
    assert out.compliance_status == "COMPLIANT"
    statuses = {row.metric: row.criterion_status for row in out.criteria}
    assert statuses["lowpass_attenuation_db"] == "PASS"
    assert statuses["lowpass_monotonicity_percent"] == "PASS"
    assert out.immutable_inputs["dut_unchanged"] is True
    assert out.immutable_inputs["specification_unchanged"] is True


def test_h1_phase2_missing_contract_metric_blocks_spice(tmp_path):
    spec, netlist, seed, plan = p10_context()
    plan.measurements = [m for m in plan.measurements if m.metric_name == "lowpass_attenuation_db"]
    simulator = FakeSimulator()
    out = HybridVerificationService(
        FakeProvider(plan.model_dump(mode="json")),
        simulator=simulator,
        max_plan_retries=0,
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.plan_outcome.validation["status"] == "VALID"
    assert out.contract_gate["status"] == "INVALID"
    assert any(i["code"] == "H1_MISSING_EXECUTABLE_METRICS" for i in out.contract_gate["issues"])
    assert simulator.calls == 0
    assert out.spice_executed is False


def test_h1_phase2_invalid_node_blocks_compilation_and_spice(tmp_path):
    spec, netlist, seed, plan = p10_context()
    plan.observed_nodes = ["hallucinated_node"]
    simulator = FakeSimulator()
    out = HybridVerificationService(
        FakeProvider(plan.model_dump(mode="json")),
        simulator=simulator,
        max_plan_retries=0,
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    assert out.plan_outcome.validation["status"] == "INVALID"
    assert simulator.calls == 0
    assert out.spice_executed is False


def test_h1_phase2_compiler_uses_only_validated_plan_measurements(tmp_path):
    spec, netlist, seed, plan = p10_context()
    simulator = FakeSimulator()
    out = HybridVerificationService(
        FakeProvider(plan.model_dump(mode="json")),
        simulator=simulator,
        max_plan_retries=0,
    ).run(spec, netlist, tmp_path, seed.model_dump(mode="json"))

    names = {m.name for m in simulator.last_testbench.measurements}
    assert names == {"lowpass_attenuation_db", "lowpass_monotonicity_percent"}
    assert simulator.last_testbench.metadata["compiled_from_llm_plan"] is True
