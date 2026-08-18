from pathlib import Path
import yaml

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / 'benchmark' / 'analogcoder_pro' / 'specs'
DUTS = ROOT / 'benchmark' / 'analogcoder_pro'


def _load(name):
    return yaml.safe_load((SPECS / name).read_text())


def test_p22_declares_upstream_initial_condition_seed():
    data = _load('p22_oscillator.yaml')
    analysis = next(a for a in data['analyses'] if a['id'] == 'tran_osc')
    assert analysis['parameters']['initial_conditions'] == {'Vref': 2.51, 'Vinn': 2.5}


def test_p22_generated_deck_contains_ic_seed():
    spec = Specification.from_yaml(SPECS / 'p22_oscillator.yaml')
    tb = TestBenchGenerator(use_llm=False).generate(spec, DUTS / 'p22_oscillator.cir')
    sim = PySpiceSimulator(ngspice_path='ngspice')
    deck = sim._generate_spice_deck(DUTS / 'p22_oscillator.cir', tb)
    assert '.IC ' in deck
    assert 'V(Vref)=2.51' in deck
    assert 'V(Vinn)=2.5' in deck


def test_p24_immutable_dut_slope_contract():
    data = _load('p24_integrator.yaml')
    req = next(r for r in data['functional_requirements'] if r['metric'] == 'integrator_ramp_slope')
    assert req['equivalence'] == 'adapted'
    assert req['minimum'] == 350.0
    assert req['maximum'] == 650.0
    assert data['performance_targets']['integrator_ramp_slope']['min'] == 350.0
    assert data['performance_targets']['integrator_ramp_slope']['max'] == 650.0


def test_p25_immutable_dut_amplitude_contract_and_shape_stays_unimplemented():
    data = _load('p25_differentiator.yaml')
    amp = next(r for r in data['functional_requirements'] if r['metric'] == 'differentiator_output_amplitude_v')
    shape = next(r for r in data['functional_requirements'] if r['metric'] == 'differentiator_square_wave_score')
    assert amp['equivalence'] == 'adapted'
    assert amp['minimum'] == 0.0016
    assert amp['maximum'] == 0.0024
    assert shape['implementation_status'] == 'metadata_only'
    assert shape['executable_metric'] is None
