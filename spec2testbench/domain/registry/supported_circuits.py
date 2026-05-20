SUPPORTED_CIRCUITS = [
    "lowpass_filter",
    "highpass_filter",
    "bandpass_filter",
    "notch_filter",
    "rc_integrator",
    "rc_differentiator",
    "common_source_amplifier",
    "common_drain_amplifier",
    "common_gate_amplifier",
    "differential_amplifier",
    "operational_amplifier",
    "current_mirror",
    "cascode_current_mirror",
    "widlar_current_source",
    "bandgap_reference",
    "voltage_reference",
    "comparator",
    "schmitt_trigger",
    "ring_oscillator",
    "lc_oscillator",
    "relaxation_oscillator",
    "mixer",
    "rectifier",
    "peak_detector",
    "sample_and_hold",
    "charge_pump",
    "lna",
    "vco",
    "ota",
    "folded_cascode_opamp",
    "two_stage_opamp",
    "instrumentation_amplifier",
    "active_load_amplifier",
    "source_follower",
    "transimpedance_amplifier",
]


def get_supported_circuits():
    return SUPPORTED_CIRCUITS


def is_supported_circuit(circuit_type: str) -> bool:
    return circuit_type in SUPPORTED_CIRCUITS