from __future__ import annotations

from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, TestBench
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


def _ac_testbench() -> TestBench:
    return TestBench(
        name="ac_gain_tb",
        category="ac",
        circuit_name="demo",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"start_freq": 1, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="20*log10(V(out)/V(in))", unit="dB")],
        metadata={
            "measurement_context": {"input_node": "vin", "output_node": "vout"},
            "measurement_requests": [
                {"name": "dc_gain_db", "preferred_backend": "NGSPICE_WRDATA", "unit": "dB"},
            ],
        },
    )


def test_native_measure_commands_use_transfer_ratio_for_dc_gain():
    simulator = PySpiceSimulator(allow_mock=True)
    commands = simulator._native_measure_commands(_ac_testbench())
    assert any("vin_mag" in command for command in commands)
    assert any("vout_mag" in command for command in commands)
    assert any("20*log10(vout_mag/vin_mag)" in command for command in commands)
    assert not any("vdb(" in command.lower() for command in commands)


def test_native_backend_selection_respects_wrdata_preference_when_vectors_exist():
    backend = PySpiceSimulator._select_native_backend(
        required_backend=None,
        has_measures=True,
        has_vectors=True,
        preferred_backends={"NGSPICE_WRDATA"},
    )
    assert backend == "NGSPICE_WRDATA"


def test_native_backend_selection_returns_mixed_only_for_conflicting_preferences():
    backend = PySpiceSimulator._select_native_backend(
        required_backend=None,
        has_measures=True,
        has_vectors=True,
        preferred_backends={"NGSPICE_MEASURE", "NGSPICE_WRDATA"},
    )
    assert backend == "MIXED"
