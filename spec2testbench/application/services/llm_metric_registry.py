from __future__ import annotations

from dataclasses import asdict, dataclass

from ...domain.entities.testbench_plan import (
    AnalysisType,
    MeasurementBackendPreference,
    StimulusType,
)
from ...domain.value_objects.metric_semantics import (
    ACQuantityType,
    TRANSFER_GAIN_V2,
)


@dataclass(frozen=True)
class MetricDefinition:
    metric_name: str
    semantic_definition: str
    compatible_analysis_types: tuple[AnalysisType, ...]
    expected_unit: str
    required_nodes: tuple[str, ...]
    preferred_backend: MeasurementBackendPreference
    definition_version: str
    quantity_type: str | None
    measurement_expression_id: str
    required_semantic_guards: dict[str, bool]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["compatible_analysis_types"] = [item.value for item in self.compatible_analysis_types]
        data["preferred_backend"] = self.preferred_backend.value
        if isinstance(self.quantity_type, ACQuantityType):
            data["quantity_type"] = self.quantity_type.value
        return data


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "operating_point": MetricDefinition(
        metric_name="operating_point",
        semantic_definition="DC or operating-point output voltage at the observed output node.",
        compatible_analysis_types=(AnalysisType.OP, AnalysisType.DC),
        expected_unit="V",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="operating_point_v1",
        quantity_type=None,
        measurement_expression_id="OPERATING_POINT_VOLTAGE",
        required_semantic_guards={},
    ),
    "vout_dc": MetricDefinition(
        metric_name="vout_dc",
        semantic_definition="Alias of the DC operating-point output voltage.",
        compatible_analysis_types=(AnalysisType.OP, AnalysisType.DC),
        expected_unit="V",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="operating_point_alias_v1",
        quantity_type=None,
        measurement_expression_id="OPERATING_POINT_VOLTAGE",
        required_semantic_guards={},
    ),
    "quiescent_current": MetricDefinition(
        metric_name="quiescent_current",
        semantic_definition="Supply current measured at operating point.",
        compatible_analysis_types=(AnalysisType.OP,),
        expected_unit="A",
        required_nodes=(),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="quiescent_current_v1",
        quantity_type=None,
        measurement_expression_id="QUIESCENT_CURRENT",
        required_semantic_guards={},
    ),
    "idd": MetricDefinition(
        metric_name="idd",
        semantic_definition="Alias of the quiescent supply current.",
        compatible_analysis_types=(AnalysisType.OP,),
        expected_unit="A",
        required_nodes=(),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="quiescent_current_alias_v1",
        quantity_type=None,
        measurement_expression_id="QUIESCENT_CURRENT",
        required_semantic_guards={},
    ),
    "power": MetricDefinition(
        metric_name="power",
        semantic_definition="DC power inferred from supply voltage and supply current.",
        compatible_analysis_types=(AnalysisType.OP,),
        expected_unit="W",
        required_nodes=(),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="power_v1",
        quantity_type=None,
        measurement_expression_id="POWER_FROM_SUPPLY_CURRENT",
        required_semantic_guards={},
    ),
    "dc_gain": MetricDefinition(
        metric_name="dc_gain",
        semantic_definition="Low-frequency voltage transfer gain defined as 20*log10(abs(Vout/Vin)).",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="dB",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version=TRANSFER_GAIN_V2,
        quantity_type=ACQuantityType.TRANSFER_GAIN_DB,
        measurement_expression_id="AC_TRANSFER_GAIN_DB",
        required_semantic_guards={
            "ac_input_exists": True,
            "ac_input_nonzero": True,
            "input_output_vectors_finite": True,
            "complex_transfer_ratio_valid": True,
        },
    ),
    "dc_gain_db": MetricDefinition(
        metric_name="dc_gain_db",
        semantic_definition="Low-frequency voltage transfer gain defined as 20*log10(abs(Vout/Vin)).",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="dB",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version=TRANSFER_GAIN_V2,
        quantity_type=ACQuantityType.TRANSFER_GAIN_DB,
        measurement_expression_id="AC_TRANSFER_GAIN_DB",
        required_semantic_guards={
            "ac_input_exists": True,
            "ac_input_nonzero": True,
            "input_output_vectors_finite": True,
            "complex_transfer_ratio_valid": True,
        },
    ),
    "absolute_output_dbv": MetricDefinition(
        metric_name="absolute_output_dbv",
        semantic_definition="Absolute output amplitude defined as 20*log10(abs(Vout)/1V).",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="dBV",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="absolute_output_dbv_v1",
        quantity_type=ACQuantityType.ABSOLUTE_OUTPUT_DBV,
        measurement_expression_id="AC_ABSOLUTE_OUTPUT_DBV",
        required_semantic_guards={"output_vector_finite": True},
    ),
    "absolute_input_dbv": MetricDefinition(
        metric_name="absolute_input_dbv",
        semantic_definition="Absolute input amplitude defined as 20*log10(abs(Vin)/1V).",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="dBV",
        required_nodes=("input",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="absolute_input_dbv_v1",
        quantity_type=ACQuantityType.ABSOLUTE_INPUT_DBV,
        measurement_expression_id="AC_ABSOLUTE_INPUT_DBV",
        required_semantic_guards={"input_vector_finite": True},
    ),
    "transfer_magnitude_linear": MetricDefinition(
        metric_name="transfer_magnitude_linear",
        semantic_definition="Low-frequency transfer magnitude defined as abs(Vout/Vin).",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="V/V",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="transfer_magnitude_linear_v1",
        quantity_type=ACQuantityType.TRANSFER_MAGNITUDE_LINEAR,
        measurement_expression_id="AC_TRANSFER_MAGNITUDE_LINEAR",
        required_semantic_guards={
            "ac_input_exists": True,
            "ac_input_nonzero": True,
            "input_output_vectors_finite": True,
            "complex_transfer_ratio_valid": True,
        },
    ),
    "transfer_phase_deg": MetricDefinition(
        metric_name="transfer_phase_deg",
        semantic_definition="Low-frequency transfer phase defined as angle(Vout/Vin) in degrees.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="deg",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="transfer_phase_deg_v1",
        quantity_type=ACQuantityType.TRANSFER_PHASE_DEG,
        measurement_expression_id="AC_TRANSFER_PHASE_DEG",
        required_semantic_guards={
            "ac_input_exists": True,
            "ac_input_nonzero": True,
            "input_output_vectors_finite": True,
            "complex_transfer_ratio_valid": True,
        },
    ),
    "cutoff_frequency_hz": MetricDefinition(
        metric_name="cutoff_frequency_hz",
        semantic_definition="Frequency where the output magnitude drops by 3 dB relative to the low-frequency gain.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="Hz",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="cutoff_frequency_v1",
        quantity_type=None,
        measurement_expression_id="AC_CUTOFF_FREQUENCY_HZ",
        required_semantic_guards={"requires_ac_sweep": True},
    ),
    "bandwidth": MetricDefinition(
        metric_name="bandwidth",
        semantic_definition="Alias of the AC cutoff frequency for single-pole and comparable benchmark circuits.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="Hz",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="bandwidth_alias_v1",
        quantity_type=None,
        measurement_expression_id="AC_CUTOFF_FREQUENCY_HZ",
        required_semantic_guards={"requires_ac_sweep": True},
    ),
    "unity_gain_frequency": MetricDefinition(
        metric_name="unity_gain_frequency",
        semantic_definition="Frequency where the magnitude of the transfer function reaches unity.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="Hz",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="unity_gain_frequency_v1",
        quantity_type=None,
        measurement_expression_id="AC_UNITY_GAIN_FREQUENCY",
        required_semantic_guards={"requires_ac_sweep": True},
    ),
    "ugbw": MetricDefinition(
        metric_name="ugbw",
        semantic_definition="Alias of the unity-gain frequency.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="Hz",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="unity_gain_frequency_alias_v1",
        quantity_type=None,
        measurement_expression_id="AC_UNITY_GAIN_FREQUENCY",
        required_semantic_guards={"requires_ac_sweep": True},
    ),
    "phase_margin": MetricDefinition(
        metric_name="phase_margin",
        semantic_definition="Phase margin measured near the unity-gain crossover.",
        compatible_analysis_types=(AnalysisType.AC,),
        expected_unit="deg",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="phase_margin_v1",
        quantity_type=None,
        measurement_expression_id="AC_PHASE_MARGIN",
        required_semantic_guards={"requires_ac_sweep": True},
    ),
    "slew_rate": MetricDefinition(
        metric_name="slew_rate",
        semantic_definition="Maximum absolute derivative of the output transient waveform.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="V/s",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="slew_rate_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_SLEW_RATE",
        required_semantic_guards={"requires_output_waveform": True},
    ),
    "settling_time": MetricDefinition(
        metric_name="settling_time",
        semantic_definition="Time required for the output to stay within the specified band around its final value.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="s",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="settling_time_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_SETTLING_TIME",
        required_semantic_guards={"requires_output_waveform": True},
    ),
    "propagation_delay": MetricDefinition(
        metric_name="propagation_delay",
        semantic_definition="Delay between an input transition and the corresponding output threshold crossing.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="s",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="propagation_delay_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_PROPAGATION_DELAY",
        required_semantic_guards={"requires_input_and_output_waveforms": True},
    ),
    "propagation_delay_s": MetricDefinition(
        metric_name="propagation_delay_s",
        semantic_definition="Alias of the propagation delay in seconds.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="s",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_MEASURE,
        definition_version="propagation_delay_alias_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_PROPAGATION_DELAY",
        required_semantic_guards={"requires_input_and_output_waveforms": True},
    ),
    "frequency_hz": MetricDefinition(
        metric_name="frequency_hz",
        semantic_definition="Oscillation frequency derived from a validated transient waveform.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="Hz",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="oscillator_frequency_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_OSCILLATOR_FREQUENCY",
        required_semantic_guards={"requires_valid_oscillation": True},
    ),
    "oscillator_frequency": MetricDefinition(
        metric_name="oscillator_frequency",
        semantic_definition="Alias of oscillator frequency derived from a validated transient waveform.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="Hz",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="oscillator_frequency_alias_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_OSCILLATOR_FREQUENCY",
        required_semantic_guards={"requires_valid_oscillation": True},
    ),
    "startup_amplitude": MetricDefinition(
        metric_name="startup_amplitude",
        semantic_definition="Steady-state oscillation amplitude estimated from the transient waveform tail.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="V",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="startup_amplitude_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_STARTUP_AMPLITUDE",
        required_semantic_guards={"requires_output_waveform": True},
    ),
    "v_t_plus": MetricDefinition(
        metric_name="v_t_plus",
        semantic_definition="Input voltage at the rising output threshold crossing.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="V",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="switching_threshold_rising_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_SWITCHING_THRESHOLD_RISING",
        required_semantic_guards={"requires_input_and_output_waveforms": True},
    ),
    "v_t_minus": MetricDefinition(
        metric_name="v_t_minus",
        semantic_definition="Input voltage at the falling output threshold crossing.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="V",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="switching_threshold_falling_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_SWITCHING_THRESHOLD_FALLING",
        required_semantic_guards={"requires_input_and_output_waveforms": True},
    ),
    "hysteresis_width": MetricDefinition(
        metric_name="hysteresis_width",
        semantic_definition="Absolute difference between the rising and falling switching thresholds.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="V",
        required_nodes=("input", "output"),
        preferred_backend=MeasurementBackendPreference.NGSPICE_WRDATA,
        definition_version="hysteresis_width_v1",
        quantity_type=None,
        measurement_expression_id="TRAN_HYSTERESIS_WIDTH",
        required_semantic_guards={"requires_input_and_output_waveforms": True},
    ),
    "thd": MetricDefinition(
        metric_name="thd",
        semantic_definition="Total harmonic distortion reported as a percentage.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="%",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="thd_v1",
        quantity_type=None,
        measurement_expression_id="FOURIER_THD_PERCENT",
        required_semantic_guards={"requires_output_waveform": True},
    ),
    "thd_percent": MetricDefinition(
        metric_name="thd_percent",
        semantic_definition="Alias of total harmonic distortion percentage.",
        compatible_analysis_types=(AnalysisType.TRAN,),
        expected_unit="%",
        required_nodes=("output",),
        preferred_backend=MeasurementBackendPreference.AUTO,
        definition_version="thd_alias_v1",
        quantity_type=None,
        measurement_expression_id="FOURIER_THD_PERCENT",
        required_semantic_guards={"requires_output_waveform": True},
    ),
}


ANALYSIS_BY_METRIC = {
    metric_name: definition.compatible_analysis_types[0]
    for metric_name, definition in METRIC_DEFINITIONS.items()
}


SUPPORTED_STIMULUS_TYPES: tuple[StimulusType, ...] = (
    StimulusType.DC,
    StimulusType.AC,
    StimulusType.PULSE,
    StimulusType.SIN,
    StimulusType.PWL,
    StimulusType.TRIANGLE,
)


def get_metric_definition(metric_name: str) -> MetricDefinition | None:
    return METRIC_DEFINITIONS.get(metric_name)


def require_metric_definition(metric_name: str) -> MetricDefinition:
    definition = get_metric_definition(metric_name)
    if definition is None:
        raise KeyError(f"Unsupported metric definition: {metric_name}")
    return definition
