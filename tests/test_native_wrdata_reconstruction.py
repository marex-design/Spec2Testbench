from pathlib import Path
import numpy as np
from spec2testbench.domain.entities.testbench import TestBench, AnalysisConfig, AnalysisType, Measurement
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import compute_lowpass_attenuation_db


def test_native_dc_wrdata_hydration(tmp_path):
    p=tmp_path/'vectors.dat'; p.write_text('0 5 -0.001\n1 4 -0.0011\n2 1 -0.0012\n')
    tb=TestBench(name='dc',category='dc',analyses=[AnalysisConfig(AnalysisType.DC,{'source':'Vdd','start':0,'stop':2,'step':1})],measurements=[Measurement('current_stability_delta_a','x')],metadata={'measurement_context':{'output_node':'Vout'}})
    r={'dc':{},'currents':{}}; PySpiceSimulator(allow_mock=True)._hydrate_results_from_vectors(r,tb,p)
    assert r['dc']['source_values']==[0.,1.,2.]
    assert r['dc']['vout_values']==[5.,4.,1.]
    assert r['currents']['vdd']==-0.0012


def test_native_ac_wrdata_hydration(tmp_path):
    p=tmp_path/'vectors.dat'
    # f, Vin.real, Vin.imag, Vout.real, Vout.imag
    np.savetxt(p,np.array([[1,1,0,1,0],[10,1,0,.5,0],[100,1,0,.1,0]],float))
    tb=TestBench(name='ac',category='ac',analyses=[AnalysisConfig(AnalysisType.AC,{})],metadata={'measurement_context':{'input_node':'Vin','output_node':'Vout'}})
    r={'ac':{}}; PySpiceSimulator(allow_mock=True)._hydrate_results_from_vectors(r,tb,p)
    assert r['ac']['frequency']==[1.,10.,100.]
    assert abs(r['ac']['dc_gain_db'])<1e-12


def test_wrdata_backend_lowpass_semantics():
    data=np.array([[1,1,0,1,0],[10,1,0,.5,0],[100,1,0,.1,0]],float)
    assert compute_lowpass_attenuation_db({'data':data},{})>19.9
