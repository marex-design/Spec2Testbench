"""Canonical deterministic metric coverage registry.

A metric listed here is understood by the runtime.  ACP strict-contract
implementation status is still controlled by the YAML requirement, so merely
being in this registry never silently turns a metadata-only criterion into a
PASS.
"""
from __future__ import annotations

SUPPORTED_METRICS = {
    "operating_point", "vout_dc", "quiescent_current", "idd", "power",
    "dc_gain", "dc_gain_db", "cutoff_frequency_hz", "bandwidth",
    "unity_gain_frequency", "ugbw", "phase_margin",
    "propagation_delay", "propagation_delay_s", "slew_rate", "slew_rate_v_s",
    "settling_time", "frequency_hz", "oscillator_frequency", "startup_amplitude",
    "fundamental_frequency", "thd", "thd_percent", "output_swing_v",
    "oscillation_period_cv", "oscillation_cycle_count",
    "v_t_plus", "v_t_minus", "hysteresis_width",
    "inverter_high_input_output_v", "inverter_low_input_output_v", "inverter_output_separation_v",
    "comparator_output_separation_v", "comparator_monotonicity_percent",
    "current_stability_delta_a", "minimum_output_current_a",
    "lowpass_attenuation_db", "lowpass_monotonicity_percent",
    "highpass_attenuation_db", "highpass_monotonicity_percent",
    "bandpass_peak_separation_db", "bandstop_notch_depth_db",
    "integrator_linearity", "integrator_ramp_slope",
    "differentiator_output_amplitude_v",
    "minimum_device_drain_current_a",
    "differential_gain_db",
}

# Deliberately not implemented in the frozen deterministic baseline.
ACP28_METADATA_ONLY_METRICS = {
    "differential_gain_linear",
    "differential_minus_common_gain",
    "iref_replication_error_a",
    "mixer_if_down_magnitude_v",
    "mixer_if_up_magnitude_v",
    "differentiator_square_wave_score",
    "adder_vin1_effect",
    "adder_vin2_effect",
    "adder_effect_ratio",
    "adder_formula_error",
    "subtractor_formula_error",
}


def is_metric_supported(name: str) -> bool:
    return str(name).strip().lower() in SUPPORTED_METRICS
