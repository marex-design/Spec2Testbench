from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

class AnalysisType(str, Enum):
    OP='OP'; DC='DC'; AC='AC'; TRAN='TRAN'; FOURIER='FOURIER'
class MeasurementBackendPreference(str, Enum):
    AUTO='AUTO'; NGSPICE_MEASURE='NGSPICE_MEASURE'; NGSPICE_WRDATA='NGSPICE_WRDATA'

class StimulusPlan(BaseModel):
    model_config=ConfigDict(extra='allow')
    source_name: str
    target_node: str
    reference_node: str='0'
    stimulus_type: str
    parameters: Dict[str,Any]=Field(default_factory=dict)
class MeasurementPlan(BaseModel):
    model_config=ConfigDict(extra='allow')
    metric_name: str
    analysis_type: AnalysisType
    input_node: Optional[str]=None
    output_node: Optional[str]=None
    expected_unit: str=''
    backend_preference: MeasurementBackendPreference=MeasurementBackendPreference.AUTO
    measurement_parameters: Dict[str,Any]=Field(default_factory=dict)
class SimulationParameters(BaseModel):
    start_time_s: Optional[float]=None; stop_time_s: Optional[float]=None; time_step_s: Optional[float]=None
    frequency_start_hz: Optional[float]=None; frequency_stop_hz: Optional[float]=None; points_per_decade: Optional[int]=None
    dc_source: Optional[str]=None; dc_start: Optional[float]=None; dc_stop: Optional[float]=None; dc_step: Optional[float]=None
class TestbenchPlan(BaseModel):
    model_config=ConfigDict(extra='allow')
    case_id: str
    analysis_type: AnalysisType
    provider_mode: str='UNKNOWN'
    scientific_llm_evidence: bool=False
    knowledge_version: Optional[str]=None
    knowledge_bundle_sha256: Optional[str]=None
    stimuli: List[StimulusPlan]=Field(default_factory=list)
    observed_nodes: List[str]=Field(default_factory=list)
    measurements: List[MeasurementPlan]=Field(default_factory=list)
    simulation_parameters: SimulationParameters=Field(default_factory=SimulationParameters)
    concise_rationale: str=''
