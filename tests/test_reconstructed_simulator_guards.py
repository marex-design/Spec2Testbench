from pathlib import Path
import pytest
from spec2testbench.infrastructure.simulator.netlist_parser import NetlistParser
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.op_bias_probe import extract_mos_device_names_from_runnable
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator
from spec2testbench.domain.entities.testbench import TestBench, AnalysisConfig, AnalysisType, Measurement

def test_mos_parameters_are_not_nodes():
    p=NetlistParser().parse_content('M1 out in 0 0 nmos W=10u L=1u\n.MODEL nmos NMOS (LEVEL=1)')
    m=p.components[0]; assert m.nodes==['out','in','0','0']; assert m.parameters=={'W':'10u','L':'1u'}; assert '0' not in p.nodes

def test_op_bias_detects_hierarchical_mos_names():
    assert extract_mos_device_names_from_runnable('m1 out in 0 0 nmos\nm.xop.m2 a b 0 0 nmos\nr1 a 0 1k')==['m1','m.xop.m2']

def test_multimode_ac_source_preserves_dc_bias():
    s=Specification.from_yaml(Path('benchmark/analogcoder_pro/specs/p01_amplifier.yaml')); tb=TestBenchGenerator(use_llm=False).generate(s,Path('benchmark/analogcoder_pro/p01_amplifier.cir'))
    sim=PySpiceSimulator(allow_mock=True); deck=sim._generate_spice_deck(Path('benchmark/analogcoder_pro/p01_amplifier.cir'),tb)
    assert 'Vin Vin 0 DC 1.0 AC 1.0 0' in deck
    assert deck.lower().count('.ac ')==1

def test_upstream_analysis_directives_are_externalized():
    s=Specification.from_yaml(Path('benchmark/analogcoder_pro/specs/p06_inverter.yaml')); tb=TestBenchGenerator(use_llm=False).generate(s,Path('benchmark/analogcoder_pro/p06_inverter.cir'))
    deck=PySpiceSimulator(allow_mock=True)._generate_spice_deck(Path('benchmark/analogcoder_pro/p06_inverter.cir'),tb)
    assert deck.lower().count('.dc ')==1

def test_transient_completion_rejects_partial_waveform():
    sim=PySpiceSimulator(allow_mock=True); tb=TestBench(name='x',category='tran',circuit_name='x',analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT,parameters={'end_time':'50m','step_time':'10u'})],measurements=[Measurement(name='output_swing_v',expression='swing')])
    st=sim._transient_completion_status({'transient':{'time':[0,50e-6,99.7e-6],'vout':[0,1,0]}},tb)
    assert st['complete'] is False and st['completion_ratio']<.01
