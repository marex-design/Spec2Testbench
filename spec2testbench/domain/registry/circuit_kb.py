"""Basic circuit knowledge base for semantic classification and metric hints.

This file maps known circuit stem names to a functional `type`, preferred
nodes (heuristics for input/output), and relevant metrics to extract.
"""

CIRCUIT_KB = {
    # filters
    'lowpass_filter': {
        'type': 'filter',
        'nodes': {'in': ['in','vin'], 'out': ['out','vout']},
        'metrics': ['cutoff_frequency','dc_gain_db']
    },
    'highpass_filter': {
        'type': 'filter',
        'nodes': {'in': ['in','vin'], 'out': ['out','vout']},
        'metrics': ['cutoff_frequency','dc_gain_db']
    },
    'bandpass_filter': {
        'type': 'filter',
        'nodes': {'in': ['in','vin'], 'out': ['out','vout']},
        'metrics': ['center_frequency','bandwidth']
    },
    'notch_filter': {
        'type': 'filter',
        'nodes': {'in': ['in','vin'], 'out': ['out','vout']},
        'metrics': ['notch_frequency']
    },

    # amplifiers
    'common_source_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain','bandwidth']},
    'common_drain_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'common_gate_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'differential_amplifier': {'type':'amplifier','nodes':{'in':['in+','in-','vin'],'out':['out','vout']},'metrics':['gain','common_mode_rejection']},
    'operational_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain','bandwidth']},
    'two_stage_opamp': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain','bandwidth']},

    # oscillators & vco
    'ring_oscillator': {'type':'oscillator','nodes':{'in':['vdd'],'out':['out','vout']},'metrics':['frequency','amplitude']},
    'lc_oscillator': {'type':'oscillator','nodes':{'in':['vdd'],'out':['out','vout']},'metrics':['frequency','amplitude']},
    'vco': {'type':'vco','nodes':{'in':['ctrl'],'out':['out','vout']},'metrics':['tuning_range','frequency']},
    'relaxation_oscillator': {'type':'oscillator','nodes':{'out':['out','vout']},'metrics':['frequency']},

    # references
    'bandgap_reference': {'type':'bandgap','nodes':{'out':['out','vout']},'metrics':['vout','thermal_drift']},
    'voltage_reference': {'type':'reference','nodes':{'out':['out','vout']},'metrics':['vout']},

    # comparators / digital-ish
    'comparator': {'type':'comparator','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['propagation_delay']},
    'schmitt_trigger': {'type':'comparator','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['hysteresis','propagation_delay']},

    # current sources / mirrors
    'current_mirror': {'type':'current_source','nodes':{'out':['out','vout']},'metrics':['current_error']},
    'cascode_current_mirror': {'type':'current_source','nodes':{'out':['out','vout']},'metrics':['current_error']},
    'widlar_current_source': {'type':'current_source','nodes':{'out':['out','vout']},'metrics':['current_error']},

    # others
    'mixer': {'type':'mixer','nodes':{'in':['rf','vin'],'out':['out','vout']},'metrics':['conversion_gain']},
    'rectifier': {'type':'rectifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['detection_efficiency']},
    'peak_detector': {'type':'detector','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['peak_voltage']},
    'sample_and_hold': {'type':'sah','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['hold_error']},
    'charge_pump': {'type':'charge_pump','nodes':{'out':['out','vout']},'metrics':['pump_current']},
    'lna': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain','noise_figure']},
    'ota': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'folded_cascode_opamp': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'instrumentation_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'active_load_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'source_follower': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['gain']},
    'transimpedance_amplifier': {'type':'amplifier','nodes':{'in':['in','vin'],'out':['out','vout']},'metrics':['transimpedance']},
}


def classify_from_stem(stem: str):
    """Return KB entry for a given netlist stem if available."""
    return CIRCUIT_KB.get(stem)


def heuristic_classify(netlist_text: str):
    t = netlist_text.lower()
    if 'osc' in t or 'vco' in t:
        return 'oscillator'
    if '.ac' in t or 'ac ' in t:
        return 'filter'
    if 'bandgap' in t or 'reference' in t:
        return 'bandgap'
    if 'mirror' in t or 'current' in t:
        return 'current_source'
    if 'comparator' in t or 'schmitt' in t:
        return 'comparator'
    # fallback
    return 'unknown'
