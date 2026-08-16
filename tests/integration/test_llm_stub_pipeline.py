from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator as FrameworkGenerator


@pytest.mark.llm_stub
@pytest.mark.ngspice
@pytest.mark.parametrize(
    ("spec_path", "netlist_path", "required_metric"),
        [
            ("benchmark/analogcoder_pro/specs/p07_inverter.yaml", "benchmark/analogcoder_pro/p07_inverter.cir", "operating_point"),
            ("benchmark/analogcoder_pro/specs/p01_amplifier.yaml", "benchmark/analogcoder_pro/p01_amplifier.cir", "dc_gain_db"),
            ("benchmark/analogcoder_pro/specs/p10_lowpass.yaml", "benchmark/analogcoder_pro/p10_lowpass.cir", "cutoff_frequency_hz"),
            ("benchmark/analogcoder_pro/specs/p09_comparator.yaml", "benchmark/analogcoder_pro/p09_comparator.cir", "propagation_delay"),
            ("benchmark/analogcoder_pro/specs/p22_oscillator.yaml", "benchmark/analogcoder_pro/p22_oscillator.cir", "oscillator_frequency"),
            ("benchmark/analogcoder_pro/specs/p28_schmitt.yaml", "benchmark/analogcoder_pro/p28_schmitt.cir", "hysteresis_width"),
        ],
    )
def test_llm_stub_runs_real_ngspice(spec_path, netlist_path, required_metric):
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")
    specification = Specification.from_yaml(Path(spec_path))
    specification.case_id = Path(spec_path).stem
    specification.performance_targets = {
        required_metric: specification.performance_targets[required_metric]
    }
    deterministic_tb = FrameworkGenerator(use_llm=False).generate(specification, netlist_path=Path(netlist_path))

    outcome = LLMGenerationService(DeterministicStubProvider()).generate_plan(
        specification=specification,
        netlist_path=Path(netlist_path),
        deterministic_testbench=deterministic_tb,
        model="deepseek-stub-v1",
        temperature=0.1,
        max_tokens=512,
        timeout_seconds=60.0,
        include_deterministic_summary=True,
    )
    assert outcome.parsed_plan is not None, outcome.validation.to_dict()
    compiled = TestbenchPlanCompiler().compile(outcome.parsed_plan, specification=specification)
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.testbench_gen.generate = lambda specification, netlist_path=None: compiled.testbench
    simulation_results = pipeline._run_simulation_with_ngspice(Path(netlist_path), compiled.testbench)
    report = pipeline.verify(specification, netlist_path=Path(netlist_path), simulation_results=simulation_results)

    assert report.execution_status.value == "SUCCESS"
    assert report.simulation_mode is not None and report.simulation_mode.value == "REAL"
    assert required_metric in simulation_results.get("metrics", {}) or any(result.test_name == required_metric for result in report.spec_results)


@pytest.mark.llm_live
@pytest.mark.ngspice
@pytest.mark.skipif(not bool(__import__("os").getenv("RUN_LLM_LIVE")), reason="RUN_LLM_LIVE is not enabled")
@pytest.mark.parametrize(
    ("spec_path", "netlist_path"),
    [
        ("benchmark/analogcoder_pro/specs/p01_amplifier.yaml", "benchmark/analogcoder_pro/p01_amplifier.cir"),
        ("benchmark/analogcoder_pro/specs/p10_lowpass.yaml", "benchmark/analogcoder_pro/p10_lowpass.cir"),
        ("benchmark/analogcoder_pro/specs/p09_comparator.yaml", "benchmark/analogcoder_pro/p09_comparator.cir"),
        ("benchmark/analogcoder_pro/specs/p22_oscillator.yaml", "benchmark/analogcoder_pro/p22_oscillator.cir"),
        ("benchmark/analogcoder_pro/specs/p28_schmitt.yaml", "benchmark/analogcoder_pro/p28_schmitt.cir"),
    ],
)
def test_llm_live_placeholder(spec_path, netlist_path):
    # This test acts as the live harness entrypoint. It remains opt-in by design.
    specification = Specification.from_yaml(Path(spec_path))
    assert specification is not None
    assert Path(netlist_path).exists()
