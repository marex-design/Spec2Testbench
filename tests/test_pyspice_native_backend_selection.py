from __future__ import annotations

from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, TestBench
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench.llm_guided_synthesis import NetlistInspector


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


def _mixed_ac_tran_testbench() -> TestBench:
    return TestBench(
        name="mixed_ac_tran_tb",
        category="mixed",
        circuit_name="demo",
        analyses=[
            AnalysisConfig(type=AnalysisType.AC, parameters={"start_freq": 1, "stop_freq": 1e6}),
            AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={"step_time": "1n", "end_time": "1u"}),
        ],
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


def test_native_control_block_selects_ac_plot_and_uses_vin_then_vout_columns():
    simulator = PySpiceSimulator(allow_mock=True)
    commands = simulator._native_control_block(_ac_testbench(), vectors_file=__import__("pathlib").Path("vectors.dat"))

    assert "setplot ac1" in commands
    assert any("real(v(vin)) imag(v(vin)) real(v(vout)) imag(v(vout))" in command.lower() for command in commands)
    assert not any(command.strip().lower().startswith("meas ") for command in commands)


def test_wrdata_hydration_does_not_invent_transient_for_mixed_ac_and_tran(tmp_path):
    simulator = PySpiceSimulator(allow_mock=True)
    vectors_path = tmp_path / "vectors.dat"
    vectors_path.write_text(
        "\n".join(
            [
                "1 1 0 10 0",
                "10 1 0 7.0710678118654755 -7.0710678118654755",
            ]
        ),
        encoding="utf-8",
    )
    results = {
        "ac": {},
        "tran": {},
        "transient": {},
        "dc": {},
        "currents": {},
        "fourier": {},
    }

    simulator._hydrate_results_from_vectors(results, _mixed_ac_tran_testbench(), vectors_path)

    assert results["tran"] == {}
    assert results["transient"] == {}


def test_guided_source_renders_multimode_pulse_with_ac_and_dc():
    simulator = PySpiceSimulator(allow_mock=True)
    rendered = simulator._render_guided_source(
        {
            "target_name": "in",
            "new_source": {
                "kind": "voltage",
                "type": "pulse",
                "node_positive": "Vin",
                "node_negative": "0",
                "dc_value": 2.5,
                "ac_magnitude": 1.0,
                "transient": {"v1": 1.25, "v2": 3.75, "rise": "1n", "fall": "1n", "width": "10u", "period": "20u"},
            },
        }
    )

    assert rendered == "Vin Vin 0 DC 2.5 AC 1.0 PULSE(1.25 3.75 0 1n 1n 10u 20u)"


def test_netlist_inspector_parses_spice_scaled_ac_magnitude():
    inspection = NetlistInspector.inspect_text("Vin Vin 0 DC 1.0 AC 1n\n")

    assert inspection.sources[0].dc_value == 1.0
    assert inspection.sources[0].ac_magnitude == 1e-9
