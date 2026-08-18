from pathlib import Path
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench.llm_guided_synthesis import FrameworkGenerator
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler

def test_deterministic_stub_plan_validates_for_lowpass():
    sp=Path('benchmark/analogcoder_pro/specs/p10_lowpass.yaml'); np=Path('benchmark/analogcoder_pro/p10_lowpass.cir'); s=Specification.from_yaml(sp)
    plan=FrameworkGenerator().build_plan(s); out=LLMGenerationService(DeterministicStubProvider()).generate_plan(s,np,plan.model_dump(mode='json'))
    assert out.validation['status']=='VALID'; assert out.parsed_plan.measurements[0].metric_name=='lowpass_attenuation_db'

def test_compiler_preserves_measurement_and_analysis():
    s=Specification.from_yaml(Path('benchmark/analogcoder_pro/specs/p10_lowpass.yaml')); plan=FrameworkGenerator().build_plan(s)
    tb=TestbenchPlanCompiler().compile(plan,s,Path('benchmark/analogcoder_pro/p10_lowpass.cir'))
    assert tb.measurements[0].name=='lowpass_attenuation_db'; assert tb.analyses[0].type.value=='ac'

def test_validator_rejects_hallucinated_node():
    s=Specification.from_yaml(Path('benchmark/analogcoder_pro/specs/p10_lowpass.yaml')); plan=FrameworkGenerator().build_plan(s); d=plan.model_dump(mode='json'); d['observed_nodes']=['NODE_DOES_NOT_EXIST']
    out=LLMGenerationService(DeterministicStubProvider(),max_retries=0).generate_plan(s,Path('benchmark/analogcoder_pro/p10_lowpass.cir'),d)
    assert out.validation['status']=='INVALID'; assert any(i['code']=='UNKNOWN_NODE' for i in out.validation['issues'])

def test_compiler_exposes_historical_testbench_wrapper_interface():
    s=Specification.from_yaml(Path('benchmark/analogcoder_pro/specs/p10_lowpass.yaml')); plan=FrameworkGenerator().build_plan(s)
    compiled=TestbenchPlanCompiler().compile(plan,s,Path('benchmark/analogcoder_pro/p10_lowpass.cir'))
    assert compiled.testbench.measurements[0].name=='lowpass_attenuation_db'
    assert compiled.measurement_requests[0]['backend_preference']=='NGSPICE_WRDATA'
