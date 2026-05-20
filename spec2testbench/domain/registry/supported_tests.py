SUPPORTED_TESTS = {
    "DC": [
        "operating_point",
        "dc_transfer",
        "bias_point_search",
        "quiescent_current",
    ],
    "AC": [
        "open_loop_gain",
        "phase_margin",
        "unity_gain_frequency",
        "cmrr",
        "psrr",
        "input_output_impedance",
    ],
    "Transient": [
        "step_response",
        "sine_response",
        "square_response",
        "oscillator_startup",
        "integrator_ramp",
        "differentiator_impulse",
        "comparator_delay",
    ],
    "Spectral": [
        "fft_thd",
        "sfdr",
        "oscillator_frequency",
        "mixer_conversion_gain",
    ],
    "Differential": [
        "common_mode_input_range",
        "differential_gain_phase",
        "schmitt_hysteresis",
        "current_mirror_matching",
    ],
    "PVT": [
        "process_corners",
        "temperature_sweep",
        "supply_variation",
    ],
}


def get_supported_tests():
    return SUPPORTED_TESTS


def get_all_tests():
    tests = []
    for category, names in SUPPORTED_TESTS.items():
        for name in names:
            tests.append({"category": category, "name": name})
    return tests


def count_supported_tests():
    return sum(len(names) for names in SUPPORTED_TESTS.values())