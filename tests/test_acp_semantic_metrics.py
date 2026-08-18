import math, pytest, numpy as np
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor

@pytest.fixture
def ex(): return MetricExtractor()

def test_dc_semantic_metrics(ex):
    data={'dc':{'source_values':[0,1,2,3,4,5],'vout_values':[5,4.9,4.5,.5,.1,0], 'current_waveforms':{'Vdd':[-1e-3,-1.0001e-3,-1.0002e-3,-1.00015e-3,-1.00005e-3,-1e-3]}}}
    assert ex.extract(data,'inverter_low_input_output_v')==5
    assert ex.extract(data,'inverter_high_input_output_v')==0
    assert ex.extract(data,'inverter_output_separation_v')==5
    assert ex.extract(data,'comparator_output_separation_v')==5
    assert ex.extract(data,'comparator_monotonicity_percent')==100
    assert ex.extract(data,'current_stability_delta_a')==pytest.approx(2e-7)
    assert ex.extract(data,'minimum_output_current_a')==pytest.approx(1e-3)

def test_filter_semantics(ex):
    lp={'ac':{'magnitude':[1,.9,.5,.1]}}
    assert ex.extract(lp,'lowpass_attenuation_db')>19
    assert ex.extract(lp,'lowpass_monotonicity_percent')==100
    hp={'ac':{'magnitude':[.1,.5,.9,1]}}
    assert ex.extract(hp,'highpass_attenuation_db')>19
    assert ex.extract(hp,'highpass_monotonicity_percent')==100

def test_bandpass_and_bandstop(ex):
    assert ex.extract({'ac':{'magnitude':[.1,.2,1,.2,.1]}},'bandpass_peak_separation_db')>10
    assert ex.extract({'ac':{'magnitude':[1,.8,.1,.8,1]}},'bandstop_notch_depth_db')>10

def test_oscillation_cycle_count_and_period_cv(ex):
    t=np.linspace(0,.01,1001); y=np.sin(2*np.pi*1000*t); data={'transient':{'time':t.tolist(),'vout':y.tolist()}}
    assert ex.extract(data,'oscillation_cycle_count')>=8
    assert ex.extract(data,'oscillation_period_cv')<.05
    assert ex.extract(data,'output_swing_v')==pytest.approx(2,rel=.01)

def test_integrator_fits_one_ramp_not_whole_triangle(ex):
    dt=1e-4; t=[i*dt for i in range(201)]; period=.01; half=period/2; y=[]
    for x in t:
        ph=x%period; y.append(500*ph if ph<=half else 500*(period-ph))
    data={'transient':{'time':t,'vout':y}}
    assert ex.extract(data,'integrator_ramp_slope')==pytest.approx(500,rel=.03)
    assert ex.extract(data,'integrator_linearity')>=.99

def test_minimum_device_current_is_exact_only(ex):
    assert ex.extract({'metrics':{'minimum_device_drain_current_a':2.5e-6}},'minimum_device_drain_current_a')==2.5e-6
    assert ex.extract({'currents':{'vdd':1e-3}},'minimum_device_drain_current_a') is None

def test_quiescent_current_is_magnitude(ex):
    assert ex.extract({'metrics':{'quiescent_current':-1e-3}},'quiescent_current')==1e-3
