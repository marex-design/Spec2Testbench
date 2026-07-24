from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from ..value_objects.circuit_type import CircuitType


class VerificationTestId(Enum):
    T01_DC_OPERATING_POINT = "T01"
    T02_DC_TRANSFER_CURVE = "T02"
    T03_BIAS_POINT_SEARCH = "T03"
    T04_QUIESCENT_CURRENT_POWER = "T04"
    T05_AC_GAIN_BANDWIDTH_GBW = "T05"
    T06_PHASE_GAIN_MARGIN = "T06"
    T07_UNITY_GAIN_FREQUENCY = "T07"
    T08_CMRR = "T08"
    T09_PSRR = "T09"
    T10_INPUT_OUTPUT_IMPEDANCE = "T10"
    T11_STEP_RESPONSE = "T11"
    T12_SINE_RESPONSE = "T12"
    T13_SQUARE_RESPONSE = "T13"
    T14_OSCILLATOR_STARTUP_STEADY_STATE = "T14"
    T15_INTEGRATOR_RAMP = "T15"
    T16_DIFFERENTIATOR_IMPULSE = "T16"
    T17_COMPARATOR_PROPAGATION = "T17"
    T18_FFT_THD = "T18"
    T19_SFDR = "T19"
    T20_OSCILLATOR_FREQUENCY_ACCURACY = "T20"
    T21_MIXER_CONVERSION_SPURS = "T21"
    T22_INPUT_COMMON_MODE_RANGE = "T22"
    T23_DIFFERENTIAL_GAIN_PHASE = "T23"
    T24_SCHMITT_HYSTERESIS = "T24"
    T25_CURRENT_MIRROR_MATCHING = "T25"
    T26_PROCESS_CORNERS = "T26"
    T27_TEMPERATURE_SWEEP = "T27"
    T28_SUPPLY_VARIATION = "T28"


class VerificationApplicabilityStatus(Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_CONFIGURATION = "UNSUPPORTED_CONFIGURATION"
    MISSING_REQUIRED_METADATA = "MISSING_REQUIRED_METADATA"


@dataclass(frozen=True)
class VerificationTestDefinition:
    test_id: VerificationTestId
    name: str
    category: str
    description: str
    applicable_circuit_types: tuple[str, ...]
    required_port_roles: tuple[str, ...]
    required_spec_fields: tuple[str, ...]
    optional_spec_fields: tuple[str, ...]
    analysis_types: tuple[str, ...]
    harness_policy: str
    metric_definitions: tuple[str, ...]
    checker_definitions: tuple[str, ...]
    plot_definition: str
    diagnostic_definition: str
    pyspice_template: str
    negative_case_strategy: str
    not_evaluated_reasons: tuple[str, ...]
    semantic_guards: tuple[str, ...]
    version: str = "1.0"


def _all_circuit_values() -> tuple[str, ...]:
    return tuple(circuit_type.value for circuit_type in CircuitType)


def _definition(
    test_id: VerificationTestId,
    *,
    name: str,
    category: str,
    description: str,
    metric_definitions: tuple[str, ...],
    analysis_types: tuple[str, ...],
    applicable_circuit_types: tuple[str, ...] | None = None,
    required_port_roles: tuple[str, ...] = (),
    required_spec_fields: tuple[str, ...] = (),
    optional_spec_fields: tuple[str, ...] = (),
    harness_policy: str = "canonical_ngspice_and_pyspice_artifacts",
    checker_definitions: tuple[str, ...] = (),
    plot_definition: str = "",
    diagnostic_definition: str = "structured_metric_and_verdict_diagnostic",
    pyspice_template: str = "canonical_deck_adapter",
    negative_case_strategy: str = "controlled_spec_or_netlist_violation",
    not_evaluated_reasons: tuple[str, ...] = (),
    semantic_guards: tuple[str, ...] = (),
) -> VerificationTestDefinition:
    return VerificationTestDefinition(
        test_id=test_id,
        name=name,
        category=category,
        description=description,
        applicable_circuit_types=applicable_circuit_types or _all_circuit_values(),
        required_port_roles=required_port_roles,
        required_spec_fields=required_spec_fields,
        optional_spec_fields=optional_spec_fields,
        analysis_types=analysis_types,
        harness_policy=harness_policy,
        metric_definitions=metric_definitions,
        checker_definitions=checker_definitions,
        plot_definition=plot_definition,
        diagnostic_definition=diagnostic_definition,
        pyspice_template=pyspice_template,
        negative_case_strategy=negative_case_strategy,
        not_evaluated_reasons=not_evaluated_reasons,
        semantic_guards=semantic_guards,
    )


@lru_cache(maxsize=1)
def get_verification_test_registry() -> tuple[VerificationTestDefinition, ...]:
    amplifier_like = (
        CircuitType.AMPLIFIER.value,
        CircuitType.OPERATIONAL_AMPLIFIER.value,
        CircuitType.DIFFERENTIAL_AMPLIFIER.value,
        CircuitType.INSTRUMENTATION_AMPLIFIER.value,
        CircuitType.OPAMP_FILTER.value,
        CircuitType.OPAMP_COMPARATOR.value,
        CircuitType.OPAMP_SCHMITT.value,
        CircuitType.COMPOSITE.value,
    )
    oscillator_like = tuple(circuit_type.value for circuit_type in CircuitType.oscillator_types())
    filter_like = tuple(circuit_type.value for circuit_type in CircuitType.filter_types())
    differential_like = (
        CircuitType.DIFFERENTIAL_AMPLIFIER.value,
        CircuitType.INSTRUMENTATION_AMPLIFIER.value,
        CircuitType.OPERATIONAL_AMPLIFIER.value,
        CircuitType.COMPARATOR.value,
        CircuitType.OPAMP_COMPARATOR.value,
        CircuitType.SCHMITT_TRIGGER.value,
        CircuitType.OPAMP_SCHMITT.value,
    )
    comparator_like = (
        CircuitType.COMPARATOR.value,
        CircuitType.OPAMP_COMPARATOR.value,
        CircuitType.SCHMITT_TRIGGER.value,
        CircuitType.OPAMP_SCHMITT.value,
    )
    return (
        _definition(
            VerificationTestId.T01_DC_OPERATING_POINT,
            name="DC operating point",
            category="DC",
            description="Validate node voltages, branch currents, and device bias conditions from an .op run.",
            metric_definitions=("operating_point", "vout_dc"),
            analysis_types=("dc",),
            required_port_roles=("output",),
            plot_definition="dc_bias_summary",
            checker_definitions=("bias_region_guard", "output_target_guard"),
            semantic_guards=("real_op_run_required", "missing_metric_remains_not_evaluated"),
        ),
        _definition(
            VerificationTestId.T02_DC_TRANSFER_CURVE,
            name="DC transfer curve",
            category="DC",
            description="Sweep the primary input and validate the transfer characteristic and monotonicity.",
            metric_definitions=("dc_transfer_curve", "local_gain", "linear_range"),
            analysis_types=("dc",),
            required_port_roles=("input", "output"),
            required_spec_fields=("test_requirements.T02",),
            plot_definition="vin_vout_transfer_curve",
            checker_definitions=("dc_sweep_guard", "monotonicity_guard"),
        ),
        _definition(
            VerificationTestId.T03_BIAS_POINT_SEARCH,
            name="Bias point search",
            category="DC",
            description="Perform a deterministic coarse-to-fine search over a declared bias control.",
            metric_definitions=("selected_bias", "bias_objective_score"),
            analysis_types=("dc",),
            applicable_circuit_types=amplifier_like,
            required_port_roles=("bias", "output"),
            required_spec_fields=("test_requirements.T03",),
            optional_spec_fields=("test_requirements.T03.objective",),
            plot_definition="bias_search_objective_curve",
            checker_definitions=("bias_search_reproducibility_guard",),
            semantic_guards=("deterministic_search_only",),
        ),
        _definition(
            VerificationTestId.T04_QUIESCENT_CURRENT_POWER,
            name="Quiescent current and power",
            category="DC",
            description="Measure quiescent rail current and absorbed power with explicit sign conventions.",
            metric_definitions=("quiescent_current", "idd", "power"),
            analysis_types=("dc",),
            required_port_roles=("supply_positive",),
            plot_definition="per_rail_current_power_summary",
            checker_definitions=("supply_sign_convention_guard",),
        ),
        _definition(
            VerificationTestId.T05_AC_GAIN_BANDWIDTH_GBW,
            name="AC gain, bandwidth, and GBW",
            category="AC",
            description="Measure transfer gain, -3 dB bandwidth, and gain-bandwidth product from a real AC sweep.",
            metric_definitions=("dc_gain_db", "bandwidth", "cutoff_frequency_hz", "ugbw"),
            analysis_types=("ac",),
            applicable_circuit_types=amplifier_like + filter_like,
            required_port_roles=("input", "output"),
            plot_definition="bode_magnitude_phase",
            checker_definitions=("ac_input_magnitude_guard", "transfer_vs_dbv_guard"),
        ),
        _definition(
            VerificationTestId.T06_PHASE_GAIN_MARGIN,
            name="Phase and gain margin",
            category="AC",
            description="Evaluate stability margins from a loop-broken or explicitly injected AC test harness.",
            metric_definitions=("phase_margin", "gain_margin"),
            analysis_types=("ac",),
            applicable_circuit_types=amplifier_like + (CircuitType.PLL.value,),
            required_port_roles=("loop_break",),
            optional_spec_fields=("ports.loop_injection",),
            plot_definition="stability_margin_bode_plot",
            checker_definitions=("loop_break_presence_guard",),
            not_evaluated_reasons=("loop_break_missing",),
        ),
        _definition(
            VerificationTestId.T07_UNITY_GAIN_FREQUENCY,
            name="Unity gain frequency",
            category="AC",
            description="Extract the unity-gain crossing frequency from the open-loop transfer function.",
            metric_definitions=("unity_gain_frequency", "ugbw"),
            analysis_types=("ac",),
            applicable_circuit_types=amplifier_like,
            required_port_roles=("input", "output"),
            plot_definition="unity_gain_crossing_plot",
            checker_definitions=("gain_crossing_guard",),
        ),
        _definition(
            VerificationTestId.T08_CMRR,
            name="Common-mode rejection ratio",
            category="AC",
            description="Compare differential gain against common-mode gain for declared differential inputs.",
            metric_definitions=("cmrr",),
            analysis_types=("ac",),
            applicable_circuit_types=differential_like,
            required_port_roles=("differential_positive", "differential_negative", "output"),
            plot_definition="cmrr_bode_plot",
            checker_definitions=("differential_port_pair_guard",),
        ),
        _definition(
            VerificationTestId.T09_PSRR,
            name="Power supply rejection ratio",
            category="AC",
            description="Inject supply perturbations and measure output rejection across frequency.",
            metric_definitions=("psrr",),
            analysis_types=("ac",),
            required_port_roles=("supply_positive", "output"),
            plot_definition="psrr_bode_plot",
            checker_definitions=("identifiable_supply_guard",),
        ),
        _definition(
            VerificationTestId.T10_INPUT_OUTPUT_IMPEDANCE,
            name="Input and output impedance",
            category="AC",
            description="Estimate Zin and Zout with an AC harness and explicit port probing.",
            metric_definitions=("input_impedance", "output_impedance"),
            analysis_types=("ac",),
            required_port_roles=("input", "output"),
            optional_spec_fields=("ports.current_probe",),
            plot_definition="impedance_vs_frequency",
            checker_definitions=("port_probe_guard",),
        ),
        _definition(
            VerificationTestId.T11_STEP_RESPONSE,
            name="Step response",
            category="Transient",
            description="Measure transient response to a deterministic input step.",
            metric_definitions=("slew_rate", "settling_time", "overshoot"),
            analysis_types=("tran",),
            required_port_roles=("input", "output"),
            plot_definition="step_response_waveform",
            checker_definitions=("transient_waveform_guard",),
        ),
        _definition(
            VerificationTestId.T12_SINE_RESPONSE,
            name="Sine response",
            category="Transient",
            description="Exercise the DUT with a sinusoidal waveform and validate time-domain behavior.",
            metric_definitions=("sine_response_amplitude", "sine_response_phase"),
            analysis_types=("tran",),
            required_port_roles=("input", "output"),
            plot_definition="sine_response_waveform",
            checker_definitions=("periodic_steady_state_guard",),
        ),
        _definition(
            VerificationTestId.T13_SQUARE_RESPONSE,
            name="Square response",
            category="Transient",
            description="Validate rise, fall, and switching quality under a square-wave stimulus.",
            metric_definitions=("rise_time", "fall_time", "ringing"),
            analysis_types=("tran",),
            required_port_roles=("input", "output"),
            plot_definition="square_response_waveform",
            checker_definitions=("edge_detection_guard",),
        ),
        _definition(
            VerificationTestId.T14_OSCILLATOR_STARTUP_STEADY_STATE,
            name="Oscillator startup and steady state",
            category="Transient",
            description="Detect startup, validate sustained oscillation, and quantify steady-state amplitude.",
            metric_definitions=("startup_amplitude", "oscillation_detected"),
            analysis_types=("tran",),
            applicable_circuit_types=oscillator_like,
            required_port_roles=("output",),
            plot_definition="oscillator_startup_envelope",
            checker_definitions=("oscillation_validation_guard",),
            not_evaluated_reasons=("physical_oscillation_absent",),
        ),
        _definition(
            VerificationTestId.T15_INTEGRATOR_RAMP,
            name="Integrator ramp",
            category="Transient",
            description="Verify ramp linearity and sign for an integrator topology.",
            metric_definitions=("integrator_ramp_slope", "integrator_linearity"),
            analysis_types=("tran",),
            applicable_circuit_types=(CircuitType.INTEGRATOR.value, CircuitType.OPAMP_INTEGRATOR.value),
            required_port_roles=("input", "output"),
            plot_definition="integrator_ramp_plot",
            checker_definitions=("integrator_behavior_guard",),
        ),
        _definition(
            VerificationTestId.T16_DIFFERENTIATOR_IMPULSE,
            name="Differentiator impulse",
            category="Transient",
            description="Verify impulse-like output response for a differentiator topology.",
            metric_definitions=("differentiator_peak", "differentiator_pulse_width"),
            analysis_types=("tran",),
            applicable_circuit_types=(CircuitType.DIFFERENTIATOR.value, CircuitType.OPAMP_DIFFERENTIATOR.value),
            required_port_roles=("input", "output"),
            plot_definition="differentiator_impulse_plot",
            checker_definitions=("differentiator_behavior_guard",),
        ),
        _definition(
            VerificationTestId.T17_COMPARATOR_PROPAGATION,
            name="Comparator propagation",
            category="Transient",
            description="Measure propagation delay from input threshold crossing to output transition.",
            metric_definitions=("propagation_delay", "propagation_delay_s"),
            analysis_types=("tran",),
            applicable_circuit_types=comparator_like,
            required_port_roles=("input", "output"),
            plot_definition="comparator_delay_plot",
            checker_definitions=("threshold_crossing_guard",),
        ),
        _definition(
            VerificationTestId.T18_FFT_THD,
            name="FFT and THD",
            category="Spectral",
            description="Run a spectral analysis and compute THD from harmonic content.",
            metric_definitions=("thd", "thd_percent", "fundamental_frequency"),
            analysis_types=("tran", "fourier"),
            required_port_roles=("output",),
            plot_definition="fft_magnitude_spectrum",
            checker_definitions=("harmonic_presence_guard",),
        ),
        _definition(
            VerificationTestId.T19_SFDR,
            name="SFDR",
            category="Spectral",
            description="Measure the spur-free dynamic range from the output spectrum.",
            metric_definitions=("sfdr",),
            analysis_types=("tran", "fourier"),
            required_port_roles=("output",),
            plot_definition="sfdr_spectrum_plot",
            checker_definitions=("spur_identification_guard",),
        ),
        _definition(
            VerificationTestId.T20_OSCILLATOR_FREQUENCY_ACCURACY,
            name="Oscillator frequency accuracy",
            category="Spectral",
            description="Measure oscillation frequency only when startup validation confirms a real oscillation.",
            metric_definitions=("oscillator_frequency", "frequency_hz"),
            analysis_types=("tran", "fourier"),
            applicable_circuit_types=oscillator_like,
            required_port_roles=("output",),
            plot_definition="oscillator_frequency_plot",
            checker_definitions=("oscillation_validation_guard", "frequency_extraction_guard"),
            not_evaluated_reasons=("oscillation_not_validated",),
        ),
        _definition(
            VerificationTestId.T21_MIXER_CONVERSION_SPURS,
            name="Mixer conversion and spurs",
            category="Spectral",
            description="Evaluate conversion gain and spur content for a mixer with explicit RF, LO, and IF roles.",
            metric_definitions=("conversion_gain", "spurious_components"),
            analysis_types=("tran", "fourier"),
            applicable_circuit_types=(CircuitType.MIXER.value,),
            required_port_roles=("input", "reference", "output"),
            required_spec_fields=("test_requirements.T21",),
            plot_definition="mixer_spectrum_plot",
            checker_definitions=("rf_lo_if_role_guard",),
        ),
        _definition(
            VerificationTestId.T22_INPUT_COMMON_MODE_RANGE,
            name="Input common-mode range",
            category="Differential",
            description="Sweep common-mode input level and identify the region where the DUT remains valid.",
            metric_definitions=("input_common_mode_range",),
            analysis_types=("dc",),
            applicable_circuit_types=differential_like,
            required_port_roles=("common_mode", "output"),
            plot_definition="icmr_sweep_plot",
            checker_definitions=("common_mode_sweep_guard",),
        ),
        _definition(
            VerificationTestId.T23_DIFFERENTIAL_GAIN_PHASE,
            name="Differential gain and phase",
            category="Differential",
            description="Measure differential transfer gain and phase for declared differential ports.",
            metric_definitions=("differential_gain", "differential_phase"),
            analysis_types=("ac",),
            applicable_circuit_types=differential_like,
            required_port_roles=("differential_positive", "differential_negative", "output"),
            plot_definition="differential_bode_plot",
            checker_definitions=("differential_port_pair_guard",),
        ),
        _definition(
            VerificationTestId.T24_SCHMITT_HYSTERESIS,
            name="Schmitt hysteresis",
            category="Differential",
            description="Measure rising and falling thresholds and compute hysteresis width.",
            metric_definitions=("v_t_plus", "v_t_minus", "hysteresis_width"),
            analysis_types=("tran",),
            applicable_circuit_types=(CircuitType.SCHMITT_TRIGGER.value, CircuitType.OPAMP_SCHMITT.value),
            required_port_roles=("input", "output"),
            plot_definition="schmitt_hysteresis_plot",
            checker_definitions=("threshold_crossing_guard",),
        ),
        _definition(
            VerificationTestId.T25_CURRENT_MIRROR_MATCHING,
            name="Current mirror matching",
            category="Differential",
            description="Compare mirrored branch currents and quantify matching error.",
            metric_definitions=("current_mirror_matching_error",),
            analysis_types=("dc",),
            applicable_circuit_types=(CircuitType.CURRENT_MIRROR.value,),
            required_port_roles=("current_probe",),
            plot_definition="current_mirror_branch_comparison",
            checker_definitions=("branch_current_guard",),
        ),
        _definition(
            VerificationTestId.T26_PROCESS_CORNERS,
            name="Process corners",
            category="PVT",
            description="Replay the nominal harness across multiple declared process corners.",
            metric_definitions=("pvt_dc_gain_variation", "pvt_vout_variation", "pvt_power_variation"),
            analysis_types=("pvt",),
            required_spec_fields=("process_corners",),
            optional_spec_fields=("operating_conditions.process_corner",),
            plot_definition="process_corner_spread_plot",
            checker_definitions=("multi_corner_presence_guard",),
        ),
        _definition(
            VerificationTestId.T27_TEMPERATURE_SWEEP,
            name="Temperature sweep",
            category="PVT",
            description="Measure metric spread across a declared temperature sweep.",
            metric_definitions=("pvt_frequency_variation", "pvt_delay_variation", "pvt_thd_variation"),
            analysis_types=("pvt",),
            required_spec_fields=("temperature_range",),
            optional_spec_fields=("operating_conditions.nominal_temperature",),
            plot_definition="temperature_sweep_plot",
            checker_definitions=("temperature_schedule_guard",),
        ),
        _definition(
            VerificationTestId.T28_SUPPLY_VARIATION,
            name="Supply variation",
            category="PVT",
            description="Measure worst-case metric variation under declared supply scaling.",
            metric_definitions=("pvt_vout_variation", "pvt_power_variation"),
            analysis_types=("pvt",),
            required_port_roles=("supply_positive",),
            required_spec_fields=("supply_variation",),
            optional_spec_fields=("operating_conditions.nominal_supply",),
            plot_definition="supply_variation_plot",
            checker_definitions=("supply_scaling_guard",),
        ),
    )


def get_verification_test_definition(test_id: VerificationTestId) -> VerificationTestDefinition:
    for definition in get_verification_test_registry():
        if definition.test_id == test_id:
            return definition
    raise KeyError(f"Unknown verification test: {test_id}")
