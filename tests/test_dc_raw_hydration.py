import numpy as np
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator

def test_dc_raw_hydration_preserves_sweep_and_current_trace():
    sim=PySpiceSimulator(allow_mock=True)
    dc,curr=sim._build_dc_results({'v-sweep':np.array([0.,1.,2.]),'v(vout)':np.array([5.,2.5,0.]),'i(vdd)':np.array([-1e-3,-1.2e-3,-1e-3])})
    assert dc['source_values']==[0.,1.,2.]
    assert dc['vout_values']==[5.,2.5,0.]
    assert dc['current_waveforms']['Vdd']==[-1e-3,-1.2e-3,-1e-3]
    assert curr['vdd']==-1e-3
