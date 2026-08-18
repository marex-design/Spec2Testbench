from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import TestBench, Stimulus, AnalysisConfig, AnalysisType as TBAnalysisType, Measurement
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan, AnalysisType

@dataclass
class CompiledTestbenchPlan:
    """Deterministic compilation result used by hybrid experiments."""
    testbench: TestBench
    measurement_requests: list[dict[str,Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __getattr__(self,name: str):
        # Backwards-compatible convenience for callers that treated compile()
        # as returning the TestBench directly.
        return getattr(self.testbench,name)

class TestbenchPlanCompiler:
    def compile(self, plan: TestbenchPlan, specification: Specification, netlist_path: Optional[Path]=None) -> CompiledTestbenchPlan:
        amap={AnalysisType.OP:TBAnalysisType.OP,AnalysisType.DC:TBAnalysisType.DC,AnalysisType.AC:TBAnalysisType.AC,AnalysisType.TRAN:TBAnalysisType.TRANSIENT,AnalysisType.FOURIER:TBAnalysisType.FOURIER}
        sp=plan.simulation_parameters
        params={k:v for k,v in {'start_freq':sp.frequency_start_hz,'stop_freq':sp.frequency_stop_hz,'points_per_decade':sp.points_per_decade,
                                'source':sp.dc_source,'start':sp.dc_start,'stop':sp.dc_stop,'step':sp.dc_step,
                                'start_time':sp.start_time_s,'end_time':sp.stop_time_s,'step_time':sp.time_step_s}.items() if v is not None}
        stimuli=[Stimulus(name=s.source_name,type=s.stimulus_type.lower(),parameters=dict(s.parameters),node_positive=s.target_node,node_negative=s.reference_node) for s in plan.stimuli]
        measurements=[Measurement(name=m.metric_name,expression=m.metric_name,unit=m.expected_unit,node=m.output_node) for m in plan.measurements]
        input_node=(specification.ports.get('input') or [None])[0]
        output_node=(specification.ports.get('output') or [None])[0]
        if plan.measurements:
            input_node=plan.measurements[0].input_node or input_node
            output_node=plan.measurements[0].output_node or output_node
        tb=TestBench(name=f'{plan.case_id}_llm_compiled',category='llm_plan',circuit_name=specification.name,netlist_path=str(netlist_path) if netlist_path else None,stimuli=stimuli,
                     analyses=[AnalysisConfig(type=amap[plan.analysis_type],parameters=params)],measurements=measurements,temperature=specification.nominal_temperature,
                     metadata={'case_id':plan.case_id,'required_metrics':[m.name for m in measurements],'compiled_from_llm_plan':True,
                               'llm_plan':plan.model_dump(mode='json'),'input_node':input_node,'output_node':output_node,
                               'measurement_context':{'input_node':input_node,'output_node':output_node},
                               'needs_op_bias_probe':'minimum_device_drain_current_a' in {m.name for m in measurements}})
        requests=[]
        for m in plan.measurements:
            req={'metric_name':m.metric_name,'analysis_type':m.analysis_type.value,'backend_preference':m.backend_preference,
                 'input_node':m.input_node,'output_node':m.output_node,'expected_unit':m.expected_unit}
            if m.metric_name in {'dc_gain','dc_gain_db','cutoff_frequency_hz','bandwidth','lowpass_attenuation_db','lowpass_monotonicity_percent','highpass_attenuation_db','highpass_monotonicity_percent','bandpass_peak_separation_db','bandstop_notch_depth_db'}:
                req.update({'in_real_column':1,'in_imag_column':2,'out_real_column':3,'out_imag_column':4})
            requests.append(req)
        tb.metadata['measurement_requests']=requests
        return CompiledTestbenchPlan(testbench=tb,measurement_requests=requests)
