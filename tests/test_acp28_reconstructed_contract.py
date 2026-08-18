from pathlib import Path
from collections import Counter
import yaml, pytest
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.specification_schema_v2 import load_acp_yaml_v2
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator

ROOT=Path('benchmark/analogcoder_pro/specs')

def specs(): return [Specification.from_yaml(p) for p in sorted(ROOT.glob('*.yaml'))]

def test_all_28_strict_specs_validate():
    files=sorted(ROOT.glob('*.yaml')); assert len(files)==28
    for p in files: assert load_acp_yaml_v2(p).schema_version=='2.0'

def test_frozen_contract_has_64_mandatory_criteria_and_17_metadata_only():
    ss=specs(); req=[r for s in ss for r in s.mandatory_requirements()]
    assert len(req)==64
    assert Counter(r['implementation_status'] for r in req)==Counter({'executable':47,'metadata_only':17})

def test_op_bias_is_executable_for_exactly_11_cases():
    cases=[]
    for s in specs():
        if any(r.get('executable_metric')=='minimum_device_drain_current_a' for r in s.mandatory_requirements()): cases.append(s.case_id)
    assert cases==['acp28-p01','acp28-p02','acp28-p03','acp28-p04','acp28-p05','acp28-p14','acp28-p15','acp28-p16','acp28-p18','acp28-p20','acp28-p21']

def test_p01_strict_generator_keeps_op_and_ac_evidence():
    s=Specification.from_yaml(ROOT/'p01_amplifier.yaml'); tb=TestBenchGenerator(use_llm=False).generate(s,Path('benchmark/analogcoder_pro/p01_amplifier.cir'))
    assert [m.name for m in tb.measurements]==['minimum_device_drain_current_a','dc_gain_db']
    assert [a.type.value for a in tb.analyses]==['op','ac']
    assert tb.metadata['needs_op_bias_probe'] is True

def test_metadata_only_metrics_are_not_promoted_to_runtime_measurements():
    s=Specification.from_yaml(ROOT/'p16_opamp.yaml'); tb=TestBenchGenerator(use_llm=False).generate(s,Path('benchmark/analogcoder_pro/p16_opamp.cir'))
    assert [m.name for m in tb.measurements]==['minimum_device_drain_current_a']
    assert 'differential_gain_linear' not in s.verification_metric_names()
