from __future__ import annotations
from pathlib import Path
from typing import Optional
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import TestBench
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan, AnalysisType, StimulusPlan, MeasurementPlan, SimulationParameters, MeasurementBackendPreference
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator
from spec2testbench.application.services.llm_metric_registry import get_metric_definition

class FrameworkGenerator:
    """Deterministic plan builder; optional LLM planning is layered above this object."""
    def __init__(self,use_llm:bool=False): self.use_llm=use_llm
    def generate(self,specification:Specification,netlist_path:Optional[Path]=None)->TestBench:
        tb=TestBenchGenerator(use_llm=False).generate(specification,netlist_path=netlist_path)
        if specification.is_v2 and netlist_path:
            plan=self.build_plan(specification)
            tb.metadata['llm_guided_plan']=plan.model_dump(mode='json')
        return tb
    def build_plan(self,specification:Specification)->TestbenchPlan:
        metric=specification.verification_metric_names()[0] if specification.verification_metric_names() else 'operating_point'
        req=specification.requirement_for_metric(metric) or {}; analysis_id=req.get('analysis'); decl=next((a for a in specification.analyses if a.get('id')==analysis_id), specification.analyses[0] if specification.analyses else {'type':'OP','parameters':{}})
        at=AnalysisType(str(decl.get('type','OP')).upper()); params=decl.get('parameters',{}) or {}
        sims=SimulationParameters(frequency_start_hz=params.get('start_freq'),frequency_stop_hz=params.get('stop_freq'),points_per_decade=params.get('points_per_decade'),dc_source=params.get('source'),dc_start=params.get('start'),dc_stop=params.get('stop'),dc_step=params.get('step'),start_time_s=params.get('start_time'),stop_time_s=params.get('end_time'),time_step_s=params.get('step_time'))
        st=[]
        for s in specification.stimuli:
            p=dict(s.get('parameters') or {}); typ=str(s.get('kind','DC')).upper();
            if typ=='AC' and 'dc_value' in p: p.setdefault('dc_value',p['dc_value'])
            st.append(StimulusPlan(source_name=str(s.get('source') or s.get('id')),target_node=str(s.get('node_positive') or '1'),reference_node=str(s.get('node_negative') or '0'),stimulus_type=typ,parameters=p))
        definition=get_metric_definition(metric); backend=definition.preferred_backend if definition else MeasurementBackendPreference.AUTO
        inp=(specification.ports.get('input') or [None])[0]; out=(specification.ports.get('output') or [None])[0]
        mp=[MeasurementPlan(metric_name=metric,analysis_type=at,input_node=inp,output_node=out,expected_unit=(definition.expected_unit if definition else specification.get_metric_unit(metric)),backend_preference=backend)]
        return TestbenchPlan(case_id=specification.case_id or specification.name,analysis_type=at,provider_mode='DETERMINISTIC',stimuli=st,observed_nodes=[n for n in [out] if n],measurements=mp,simulation_parameters=sims,concise_rationale='Deterministic netlist-aware plan generated from the frozen verification contract.')
