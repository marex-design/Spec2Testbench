import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.llm.deepseek_plan_provider import DeepSeekPlanProvider
from spec2testbench.infrastructure.testbench.llm_guided_synthesis import FrameworkGenerator


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None
    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            model="deepseek-v4-pro",
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.content)))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        )


class _FakeClient:
    def __init__(self, content):
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


def _p10_seed():
    sp=Path('benchmark/analogcoder_pro/specs/p10_lowpass.yaml')
    np=Path('benchmark/analogcoder_pro/p10_lowpass.cir')
    spec=Specification.from_yaml(sp)
    seed=FrameworkGenerator().build_plan(spec).model_dump(mode='json')
    return sp,np,spec,seed


def test_deepseek_h1_rejects_retired_model_name():
    with pytest.raises(ValueError):
        DeepSeekPlanProvider(api_key='dummy', model='deepseek-chat', client=_FakeClient({}))


def test_deepseek_h1_uses_json_mode_and_explicit_non_thinking():
    _,_,spec,seed=_p10_seed()
    fake=_FakeClient(seed)
    provider=DeepSeekPlanProvider(api_key='dummy',model='deepseek-v4-pro',client=fake,thinking=False)
    result=provider.generate({'case_id':spec.case_id,'specification':spec.canonical_dict(),'deterministic_plan':seed})
    assert result['case_id']==spec.case_id
    kwargs=fake.chat.completions.kwargs
    assert kwargs['response_format']=={'type':'json_object'}
    assert kwargs['extra_body']=={'thinking':{'type':'disabled'}}
    assert provider.last_call_metadata['usage']['total_tokens']==18
    assert provider.last_call_metadata['request_sha256']
    assert provider.last_call_metadata['response_sha256']


def test_deepseek_h1_plan_passes_deterministic_validator():
    _,np,spec,seed=_p10_seed()
    provider=DeepSeekPlanProvider(api_key='dummy',model='deepseek-v4-pro',client=_FakeClient(seed))
    out=LLMGenerationService(provider,max_retries=0).generate_plan(spec,np,seed)
    assert out.validation['status']=='VALID'
    assert out.provider_metadata['provider']=='deepseek'
    assert out.parsed_plan.case_id==spec.case_id


def test_deepseek_h1_provider_prompt_forbids_verdict_and_dut_changes():
    provider=DeepSeekPlanProvider(api_key='dummy',model='deepseek-v4-flash',client=_FakeClient({}))
    prompt=provider._system_prompt().lower()
    assert 'must not modify the dut' in prompt
    assert 'must not modify specification thresholds' in prompt
    assert 'must not decide pass/fail' in prompt



def test_deepseek_h1_framework_stamps_live_provenance_and_preserves_raw_response():
    _,np,spec,seed=_p10_seed()
    # Simulate a model copying provenance fields from the deterministic seed.
    raw=dict(seed)
    raw['provider_mode']='DETERMINISTIC'
    raw['scientific_llm_evidence']=False
    provider=DeepSeekPlanProvider(api_key='dummy',model='deepseek-v4-pro',client=_FakeClient(raw))
    out=LLMGenerationService(provider,max_retries=0).generate_plan(spec,np,seed)
    assert out.validation['status']=='VALID'
    assert out.raw_response['provider_mode']=='DETERMINISTIC'
    assert out.raw_response['scientific_llm_evidence'] is False
    assert out.parsed_plan.provider_mode=='DEEPSEEK_LIVE'
    assert out.parsed_plan.scientific_llm_evidence is True


def test_deepseek_h1_prompt_schema_excludes_framework_owned_provenance_fields():
    _,_,spec,seed=_p10_seed()
    fake=_FakeClient(seed)
    provider=DeepSeekPlanProvider(api_key='dummy',model='deepseek-v4-pro',client=fake)
    provider.generate({'case_id':spec.case_id,'specification':spec.canonical_dict(),'deterministic_plan':seed})
    user_message=fake.chat.completions.kwargs['messages'][1]['content']
    request=json.loads(user_message)
    props=request['testbench_plan_json_schema']['properties']
    assert 'provider_mode' not in props
    assert 'scientific_llm_evidence' not in props
    prompt=provider._system_prompt().lower()
    assert 'do not set provider_mode or scientific_llm_evidence' in prompt
