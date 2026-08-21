from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from spec2testbench.domain.entities.testbench_plan import AnalysisType, MeasurementBackendPreference

@dataclass(frozen=True)
class MetricDefinition:
    metric_name: str
    compatible_analysis_types: tuple[AnalysisType,...]
    expected_unit: str
    preferred_backend: MeasurementBackendPreference
    semantic_definition: str=''
    measurement_expression_id: str=''

_DEFS={}
def _add(name, analyses, unit, backend=MeasurementBackendPreference.NGSPICE_WRDATA, definition=''):
    _DEFS[name]=MetricDefinition(name,tuple(analyses),unit,backend,definition,name.upper())

_add('minimum_device_drain_current_a',[AnalysisType.OP,AnalysisType.DC],'A',MeasurementBackendPreference.NGSPICE_MEASURE,'min_i(abs(Id_i)) at operating point')
for n in ['inverter_low_input_output_v','inverter_high_input_output_v','inverter_output_separation_v','comparator_output_separation_v']:_add(n,[AnalysisType.DC],'V')
_add('comparator_monotonicity_percent',[AnalysisType.DC],'%')
for n in ['current_stability_delta_a','minimum_output_current_a']:_add(n,[AnalysisType.DC],'A')
_add('dc_gain_db',[AnalysisType.AC],'dB')

_add(
    'differential_gain_db',
    [AnalysisType.AC],
    'dB',
    MeasurementBackendPreference.NGSPICE_WRDATA,
    'single-ended differential gain at reference frequency: '
    '20*log10(abs(Vout/(Vin_pos-Vin_neg)))'
)


for n in ['lowpass_attenuation_db','highpass_attenuation_db','bandpass_peak_separation_db','bandstop_notch_depth_db']:_add(n,[AnalysisType.AC],'dB')
for n in ['lowpass_monotonicity_percent','highpass_monotonicity_percent']:_add(n,[AnalysisType.AC],'%')
for n in ['oscillation_cycle_count','oscillation_period_cv']:_add(n,[AnalysisType.TRAN],'')
for n in ['output_swing_v','differentiator_output_amplitude_v']:_add(n,[AnalysisType.TRAN],'V')
_add('integrator_ramp_slope',[AnalysisType.TRAN],'V/s'); _add('integrator_linearity',[AnalysisType.TRAN],'')
_add('hysteresis_width',[AnalysisType.TRAN],'V')

def get_metric_definition(name: str) -> Optional[MetricDefinition]: return _DEFS.get(str(name))
def implemented_metric_names(): return tuple(sorted(_DEFS))
