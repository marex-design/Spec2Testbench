from __future__ import annotations

from pathlib import Path

import yaml


BENCH_DIR = Path("benchmark") / "reference_28"
SPEC_DIR = Path("examples") / "reference_28_specs"
SPEC_DIR.mkdir(parents=True, exist_ok=True)


def metric(*, min_value=None, max_value=None, unit=""):
    payload = {}
    if min_value is not None:
        payload["min"] = min_value
    if max_value is not None:
        payload["max"] = max_value
    if unit:
        payload["unit"] = unit
    return payload


def case(
    *,
    name: str,
    filename: str,
    circuit_type: str,
    description: str,
    include_test: str,
    test_categories: list[str],
    performance_targets: dict,
    ports: dict,
    input_conditions: dict | None = None,
    test_requirements: dict | None = None,
    pvt_config: dict | None = None,
    operating_conditions: dict | None = None,
) -> dict:
    resolved_pvt = pvt_config or {
        "corners": ["tt"],
        "temperature_range": "commercial",
        "supply_variation": 0.1,
    }
    return {
        "name": name,
        "case_id": name,
        "circuit_type": circuit_type,
        "technology": "reference_28_behavioral",
        "description": description,
        "source": {
            "benchmark": "reference_28",
            "netlist": str(BENCH_DIR / filename).replace("\\", "/"),
        },
        "performance_targets": performance_targets,
        "input_conditions": {
            "vdd": 5.0,
            "vss": 0.0,
            "vcm": 2.5,
            "input_frequency": 1e3,
            **(input_conditions or {}),
        },
        "ports": ports,
        "verification": {
            "include_tests": [include_test],
            "auto_select": False,
        },
        "test_categories": test_categories,
        "test_requirements": test_requirements or {},
        "process_corners": list(resolved_pvt.get("corners", ["tt"])),
        "temperature_range": resolved_pvt.get("temperature_range", "commercial"),
        "supply_variation": resolved_pvt.get("supply_variation", 0.1),
        "operating_conditions": operating_conditions or {
            "nominal_temperature": 27,
            "nominal_supply": 5.0,
            "process_corner": "tt",
        },
        "pvt_config": resolved_pvt,
    }


REFERENCE_CASES = [
    case(
        name="reference_28_t01_dc_operating_point",
        filename="common_source_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T01 DC operating point.",
        include_test="T01",
        test_categories=["dc"],
        performance_targets={
            "operating_point": metric(min_value=0.5, max_value=4.5, unit="V"),
            "vout_dc": metric(min_value=0.5, max_value=4.5, unit="V"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t02_dc_transfer_curve",
        filename="three_stage_common_source_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T02 DC transfer curve.",
        include_test="T02",
        test_categories=["dc"],
        performance_targets={
            "dc_transfer_curve": metric(min_value=0.5, unit="V"),
            "local_gain": metric(min_value=0.01, unit="V/V"),
            "linear_range": metric(min_value=0.1, unit="V"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
        test_requirements={"T02": {"sweep_source": "vin", "sweep_start": 0.0, "sweep_stop": 5.0, "sweep_step": 0.05}},
    ),
    case(
        name="reference_28_t03_bias_point_search",
        filename="common_gate_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T03 bias point search.",
        include_test="T03",
        test_categories=["dc"],
        performance_targets={
            "selected_bias": metric(min_value=0.5, max_value=4.5, unit="V"),
            "bias_objective_score": metric(min_value=0.1, max_value=1.0, unit="score"),
        },
        ports={"input": ["in"], "output": ["out"], "bias": ["gate"], "supply_positive": ["vdd"]},
        test_requirements={"T03": {"objective": "vout_mid_supply", "coarse_step": 0.1, "fine_step": 0.01}},
    ),
    case(
        name="reference_28_t04_quiescent_current_power",
        filename="cascode_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T04 quiescent current and power.",
        include_test="T04",
        test_categories=["dc"],
        performance_targets={
            "quiescent_current": metric(max_value=0.01, unit="A"),
            "power": metric(max_value=0.1, unit="W"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t05_ac_gain_bandwidth_gbw",
        filename="common_source_diode_connected_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T05 AC gain, bandwidth and GBW.",
        include_test="T05",
        test_categories=["ac"],
        performance_targets={
            "dc_gain_db": metric(min_value=-60.0, max_value=120.0, unit="dB"),
            "bandwidth": metric(min_value=1.0, unit="Hz"),
            "ugbw": metric(min_value=1.0, unit="Hz"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t06_phase_gain_margin",
        filename="two_stage_miller_compensated_amplifier.cir",
        circuit_type="opamp",
        description="Reference coverage case for T06 phase and gain margin.",
        include_test="T06",
        test_categories=["ac"],
        performance_targets={
            "phase_margin": metric(min_value=0.0, max_value=180.0, unit="deg"),
            "gain_margin": metric(min_value=0.0, unit="dB"),
        },
        ports={"input": ["inp"], "output": ["out"], "loop_break": ["n1"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t07_unity_gain_frequency",
        filename="cascode_opamp_cascode_loads.cir",
        circuit_type="opamp",
        description="Reference coverage case for T07 unity gain frequency.",
        include_test="T07",
        test_categories=["ac"],
        performance_targets={"unity_gain_frequency": metric(min_value=1.0, unit="Hz")},
        ports={"input": ["inp"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t08_cmrr",
        filename="opamp_active_current_mirror_loads.cir",
        circuit_type="opamp",
        description="Reference coverage case for T08 CMRR.",
        include_test="T08",
        test_categories=["ac", "differential"],
        performance_targets={"cmrr": metric(min_value=0.0, unit="dB")},
        ports={
            "differential_positive": ["inp"],
            "differential_negative": ["inn"],
            "output": ["out"],
            "supply_positive": ["vdd"],
        },
    ),
    case(
        name="reference_28_t09_psrr",
        filename="common_source_resistive_load_opamp.cir",
        circuit_type="opamp",
        description="Reference coverage case for T09 PSRR.",
        include_test="T09",
        test_categories=["ac"],
        performance_targets={"psrr": metric(min_value=0.0, unit="dB")},
        ports={"input": ["inp"], "output": ["outn"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t10_input_output_impedance",
        filename="two_stage_opamp_active_loads.cir",
        circuit_type="opamp",
        description="Reference coverage case for T10 input and output impedance.",
        include_test="T10",
        test_categories=["ac"],
        performance_targets={
            "input_impedance": metric(min_value=1.0, unit="Ohm"),
            "output_impedance": metric(min_value=1.0, unit="Ohm"),
        },
        ports={"input": ["inp"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t11_step_response",
        filename="passive_lowpass_filter.cir",
        circuit_type="low_pass_filter",
        description="Reference coverage case for T11 step response.",
        include_test="T11",
        test_categories=["transient"],
        performance_targets={
            "slew_rate": metric(min_value=1e-6, unit="V/s"),
            "settling_time": metric(max_value=1.0, unit="s"),
            "overshoot": metric(max_value=200.0, unit="%"),
        },
        ports={"input": ["in"], "output": ["out"]},
    ),
    case(
        name="reference_28_t12_sine_response",
        filename="passive_highpass_filter.cir",
        circuit_type="high_pass_filter",
        description="Reference coverage case for T12 sine response.",
        include_test="T12",
        test_categories=["transient"],
        performance_targets={
            "sine_response_amplitude": metric(min_value=0.0, unit="V"),
            "sine_response_phase": metric(min_value=-180.0, max_value=180.0, unit="deg"),
        },
        ports={"input": ["in"], "output": ["out"]},
        input_conditions={"input_frequency": 1e3},
    ),
    case(
        name="reference_28_t13_square_response",
        filename="cmos_logical_inverter.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T13 square response.",
        include_test="T13",
        test_categories=["transient"],
        performance_targets={
            "rise_time": metric(min_value=0.0, unit="s"),
            "fall_time": metric(min_value=0.0, unit="s"),
            "ringing": metric(max_value=200.0, unit="%"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t14_oscillator_startup",
        filename="wien_bridge_oscillator.cir",
        circuit_type="oscillator",
        description="Reference coverage case for T14 oscillator startup and steady state.",
        include_test="T14",
        test_categories=["transient"],
        performance_targets={
            "startup_amplitude": metric(min_value=1e-6, unit="V"),
            "oscillation_detected": metric(min_value=0.0, max_value=1.0, unit="score"),
        },
        ports={"output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t15_integrator_ramp",
        filename="opamp_integrator.cir",
        circuit_type="opamp_integrator",
        description="Reference coverage case for T15 integrator ramp.",
        include_test="T15",
        test_categories=["transient"],
        performance_targets={
            "integrator_ramp_slope": metric(min_value=1e-6, unit="V/s"),
            "integrator_linearity": metric(min_value=0.0, max_value=1.0, unit="score"),
        },
        ports={"input": ["in"], "output": ["out"]},
    ),
    case(
        name="reference_28_t16_differentiator_impulse",
        filename="opamp_differentiator.cir",
        circuit_type="opamp_differentiator",
        description="Reference coverage case for T16 differentiator impulse.",
        include_test="T16",
        test_categories=["transient"],
        performance_targets={
            "differentiator_peak": metric(min_value=0.0, unit="V"),
            "differentiator_pulse_width": metric(min_value=0.0, unit="s"),
        },
        ports={"input": ["in"], "output": ["out"]},
    ),
    case(
        name="reference_28_t17_comparator_propagation",
        filename="opamp_comparator.cir",
        circuit_type="comparator",
        description="Reference coverage case for T17 comparator propagation.",
        include_test="T17",
        test_categories=["transient"],
        performance_targets={"propagation_delay": metric(max_value=1.0, unit="s")},
        ports={"input": ["inp"], "output": ["out"], "reference": ["inn"]},
    ),
    case(
        name="reference_28_t18_fft_thd",
        filename="passive_bandpass_filter.cir",
        circuit_type="band_pass_filter",
        description="Reference coverage case for T18 FFT and THD.",
        include_test="T18",
        test_categories=["spectral"],
        performance_targets={
            "thd": metric(max_value=100.0, unit="%"),
            "fundamental_frequency": metric(min_value=1.0, unit="Hz"),
        },
        ports={"input": ["in"], "output": ["out"]},
        input_conditions={"input_frequency": 1e3},
    ),
    case(
        name="reference_28_t19_sfdr",
        filename="opamp_adder.cir",
        circuit_type="composite",
        description="Reference coverage case for T19 SFDR.",
        include_test="T19",
        test_categories=["spectral"],
        performance_targets={"sfdr": metric(min_value=0.0, unit="dB")},
        ports={"input": ["in1"], "output": ["out"]},
        input_conditions={"input_frequency": 1e3},
    ),
    case(
        name="reference_28_t20_oscillator_frequency_accuracy",
        filename="rc_shift_oscillator.cir",
        circuit_type="oscillator",
        description="Reference coverage case for T20 oscillator frequency accuracy.",
        include_test="T20",
        test_categories=["transient", "spectral"],
        performance_targets={"oscillator_frequency": metric(min_value=1.0, unit="Hz")},
        ports={"output": ["out"]},
    ),
    case(
        name="reference_28_t21_mixer_conversion_spurs",
        filename="gilbert_cell_mixer.cir",
        circuit_type="mixer",
        description="Reference coverage case for T21 mixer conversion gain and spurs.",
        include_test="T21",
        test_categories=["spectral", "transient"],
        performance_targets={
            "conversion_gain": metric(min_value=-120.0, max_value=120.0, unit="dB"),
            "spurious_components": metric(max_value=0.0, unit="dBc"),
        },
        ports={"input": ["rf"], "reference": ["lo"], "output": ["out"]},
        test_requirements={"T21": {"rf_node": "rf", "lo_node": "lo", "if_node": "out"}},
        input_conditions={"input_frequency": 1e7},
    ),
    case(
        name="reference_28_t22_input_common_mode_range",
        filename="opamp_active_current_mirror_loads.cir",
        circuit_type="opamp",
        description="Reference coverage case for T22 input common-mode range.",
        include_test="T22",
        test_categories=["dc", "differential"],
        performance_targets={"input_common_mode_range": metric(min_value=0.1, unit="V")},
        ports={
            "common_mode": ["inp", "inn"],
            "output": ["out"],
            "differential_positive": ["inp"],
            "differential_negative": ["inn"],
            "supply_positive": ["vdd"],
        },
    ),
    case(
        name="reference_28_t23_differential_gain_phase",
        filename="common_source_resistive_load_opamp.cir",
        circuit_type="opamp",
        description="Reference coverage case for T23 differential gain and phase.",
        include_test="T23",
        test_categories=["ac", "differential"],
        performance_targets={
            "differential_gain": metric(min_value=-120.0, max_value=120.0, unit="dB"),
            "differential_phase": metric(min_value=-180.0, max_value=180.0, unit="deg"),
        },
        ports={
            "differential_positive": ["inp"],
            "differential_negative": ["inn"],
            "output": ["outp"],
            "supply_positive": ["vdd"],
        },
    ),
    case(
        name="reference_28_t24_schmitt_hysteresis",
        filename="non_inverting_schmitt_trigger.cir",
        circuit_type="schmitt_trigger",
        description="Reference coverage case for T24 Schmitt hysteresis.",
        include_test="T24",
        test_categories=["transient", "differential"],
        performance_targets={
            "v_t_plus": metric(min_value=0.0, max_value=5.0, unit="V"),
            "v_t_minus": metric(min_value=0.0, max_value=5.0, unit="V"),
            "hysteresis_width": metric(min_value=0.0, unit="V"),
        },
        ports={"input": ["in"], "output": ["out"]},
    ),
    case(
        name="reference_28_t25_current_mirror_matching",
        filename="cascode_current_mirror.cir",
        circuit_type="current_mirror",
        description="Reference coverage case for T25 current mirror matching.",
        include_test="T25",
        test_categories=["dc"],
        performance_targets={"current_mirror_matching_error": metric(max_value=1.0, unit="ratio")},
        ports={"current_probe": ["ref", "out"], "output": ["out"], "supply_positive": ["vdd"]},
    ),
    case(
        name="reference_28_t26_process_corners",
        filename="common_source_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T26 process corners.",
        include_test="T26",
        test_categories=["dc", "ac", "pvt"],
        performance_targets={
            "pvt_dc_gain_variation": metric(max_value=200.0, unit="dB"),
            "pvt_vout_variation": metric(max_value=5.0, unit="V"),
            "pvt_power_variation": metric(max_value=1.0, unit="W"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
        pvt_config={"corners": ["tt", "ff", "ss", "fs", "sf"], "temperature_range": "commercial", "supply_variation": 0.1},
    ),
    case(
        name="reference_28_t27_temperature_sweep",
        filename="rc_shift_oscillator.cir",
        circuit_type="oscillator",
        description="Reference coverage case for T27 temperature sweep.",
        include_test="T27",
        test_categories=["transient", "spectral", "pvt"],
        performance_targets={
            "pvt_frequency_variation": metric(max_value=1e9, unit="Hz"),
            "pvt_delay_variation": metric(max_value=1.0, unit="s"),
            "pvt_thd_variation": metric(max_value=100.0, unit="%"),
        },
        ports={"output": ["out"], "input": ["out"]},
        pvt_config={"corners": ["tt", "ff"], "temperature_range": "extended", "supply_variation": 0.1},
    ),
    case(
        name="reference_28_t28_supply_variation",
        filename="common_drain_resistive_load_amplifier.cir",
        circuit_type="amplifier",
        description="Reference coverage case for T28 supply variation.",
        include_test="T28",
        test_categories=["dc", "pvt"],
        performance_targets={
            "pvt_vout_variation": metric(max_value=5.0, unit="V"),
            "pvt_power_variation": metric(max_value=1.0, unit="W"),
        },
        ports={"input": ["in"], "output": ["out"], "supply_positive": ["vdd"]},
        pvt_config={"corners": ["tt", "ff"], "temperature_range": "commercial", "supply_variation": 0.1},
    ),
]


def main():
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    for payload in REFERENCE_CASES:
        spec_path = SPEC_DIR / f"{payload['name']}.yaml"
        spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    print(f"Generated {len(REFERENCE_CASES)} reference specs in {SPEC_DIR}")


if __name__ == "__main__":
    main()
