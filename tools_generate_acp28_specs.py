from pathlib import Path
import csv, hashlib, re, yaml

ROOT=Path(__file__).resolve().parent
MAN=ROOT/'benchmark_analogcoder_pro_28/manifest.csv'
OLD=ROOT/'examples/analogcoder_pro_28_specs'
DST=ROOT/'benchmark/analogcoder_pro/specs'
DST.mkdir(parents=True,exist_ok=True)

OP_CASES={1,2,3,4,5,14,15,16,18,20,21}
AMP_CASES={1,2,3,4,5,14,15}
OPAMP_CASES={16,18,20,21}

def split_nodes(v):
    if v is None: return []
    if isinstance(v,list): return v
    s=str(v).strip()
    if s in {'','-','NA','N/A'}: return []
    return [x.strip() for x in s.split(',') if x.strip() and x.strip()!='-']

def source_dc_values(text):
    out={}
    for line in text.splitlines():
        m=re.match(r'^\s*(V\w+)\s+\S+\s+\S+\s+(.*)$',line,re.I)
        if not m: continue
        rest=m.group(2).strip()
        dm=re.search(r'(?i)\bDC\s+([-+0-9.eE]+)',rest)
        if dm:
            try: out[m.group(1).lower()]=float(dm.group(1))
            except: pass
        else:
            sm=re.match(r'([-+0-9.eE]+)',rest)
            if sm:
                try: out[m.group(1).lower()]=float(sm.group(1))
                except: pass
    return out

def req(i,desc,metric,analysis,operator,threshold=None,minimum=None,maximum=None,unit='',status='executable',equiv='exact',notes=''):
    return dict(id=i,description=desc,metric=metric,analysis=analysis,operator=operator,
                threshold=threshold,minimum=minimum,maximum=maximum,unit=unit,mandatory=True,
                criterion_source='official_checker',equivalence=equiv,
                implementation_status=status,executable_metric=(metric if status=='executable' else None),notes=notes)

def targets(reqs,vdd=5.0):
    d={'operating_point':{'min':0.0,'max':vdd,'unit':'V','diagnostic_only':True,'requirement_ids':[]}}
    for r in reqs:
        if r['implementation_status']!='executable': continue
        t={'unit':r['unit'],'diagnostic_only':False,'requirement_ids':[r['id']]}
        op=r['operator']
        if op in ('>','>='): t['min']=r['threshold']
        elif op in ('<','<='): t['max']=r['threshold']
        elif op=='between':
            t['min']=r['minimum'];t['max']=r['maximum']
        d[r['metric']]=t
    return d

def analyses_for(task):
    if task in AMP_CASES:
        return [
            {'id':'op_bias','type':'OP','parameters':{},'purpose':'Check active-device operating point.'},
            {'id':'ac_gain','type':'AC','parameters':{'sweep_type':'dec','points_per_decade':2,'start_freq':100.0,'stop_freq':1000.0},'purpose':'Measure low-frequency transfer gain.'},
        ]
    if task in {6,7}:
        return [{'id':'dc_logic','type':'DC','parameters':{'source':'Vin','start':0.0,'stop':5.0,'step':0.01},'purpose':'Evaluate inverter logic transfer.'}]
    if task in {8,17}:
        return [{'id':'dc_compliance','type':'DC','parameters':{'source':'Vload','start':0.5,'stop':4.5,'step':1.0},'purpose':'Immutable-DUT compliance-voltage sweep equivalent to the checker load sweep.'}]
    if task==9:
        return [{'id':'dc_transfer','type':'DC','parameters':{'source':'Vin','start':0.0,'stop':5.0,'step':0.01},'purpose':'Comparator transfer characteristic.'}]
    if task in {10,11,12,13}:
        return [{'id':'ac_filter','type':'AC','parameters':{'sweep_type':'dec','points_per_decade':100,'start_freq':1.0,'stop_freq':1e9},'purpose':'Filter magnitude response.'}]
    if task in OPAMP_CASES:
        return [
            {'id':'op_bias','type':'OP','parameters':{},'purpose':'Check MOS operating point.'},
            {'id':'ac_modes','type':'AC','parameters':{'sweep_type':'dec','points_per_decade':2,'start_freq':100.0,'stop_freq':1000.0},'purpose':'Official differential/common-mode gain semantics.'},
        ]
    if task==19:
        return [{'id':'fft_mix','type':'TRAN','parameters':{'step_time':1/(20*1200),'end_time':0.02,'start_time':0.0},'purpose':'Mixer transient followed by FFT.'}]
    if task in {22,23}:
        return [{'id':'tran_osc','type':'TRAN','parameters':{'step_time':1e-6,'end_time':0.02,'start_time':0.0},'purpose':'Oscillator startup and sustained oscillation.'}]
    if task==24:
        return [{'id':'tran_integrator','type':'TRAN','parameters':{'step_time':1e-6,'end_time':1.0,'start_time':0.8},'purpose':'Square-wave input and linear ramp output.'}]
    if task==25:
        return [{'id':'tran_diff','type':'TRAN','parameters':{'step_time':1e-6,'end_time':0.2,'start_time':0.0},'purpose':'Triangle-wave input and square-like differentiator output.'}]
    if task in {26,27}:
        return [{'id':'dc_grid','type':'OP','parameters':{},'purpose':'Multiple deterministic DC operating-point perturbations.'}]
    if task==28:
        return [{'id':'tran_hyst','type':'TRAN','parameters':{'step_time':1e-5,'end_time':0.05,'start_time':0.0,'use_initial_conditions':True},'purpose':'Schmitt hysteresis loop under sinusoidal input.'}]
    return []

def stimuli_for(task,ins,dcvals):
    if task in AMP_CASES:
        node='Vin'; dc=dcvals.get('vin',1.0)
        return [{'id':'ac_input','kind':'AC','source':'Vin','node_positive':node,'node_negative':'0','parameters':{'magnitude':1.0,'phase':0,'dc_value':dc},'purpose':'Small-signal excitation; transfer ratio is amplitude invariant.'}]
    if task in {6,7,9}:
        return [{'id':'dc_input','kind':'DC','source':'Vin','node_positive':'Vin','node_negative':'0','parameters':{'start':0.0,'stop':5.0,'step':0.01},'purpose':'DC transfer sweep.'}]
    if task in {10,11,12,13}:
        return [{'id':'ac_input','kind':'AC','source':'Vin','node_positive':'Vin','node_negative':'0','parameters':{'magnitude':1.0,'phase':0,'dc_value':2.5},'purpose':'Official filter AC excitation.'}]
    if task in OPAMP_CASES:
        return [
            {'id':'diff_input_p','kind':'AC','source':'Vinp','node_positive':'Vinp','node_negative':'0','parameters':{'magnitude':1.0,'phase':0,'dc_value':dcvals.get('vinp',1.0)},'purpose':'Differential/common-mode plan input.'},
            {'id':'diff_input_n','kind':'AC','source':'Vinn','node_positive':'Vinn','node_negative':'0','parameters':{'magnitude':1.0,'phase':180,'dc_value':dcvals.get('vinn',1.0)},'purpose':'Differential/common-mode plan input.'},
        ]
    if task==24:
        return [{'id':'square_input','kind':'PULSE','source':'Vin','node_positive':'Vin','node_negative':'0','parameters':{'v1':2.0,'v2':3.0,'delay':1e-6,'rise':1e-6,'fall':1e-6,'width':0.01,'period':0.02,'dc_value':2.5},'purpose':'Official integrator checker stimulus.'}]
    if task==25:
        return [{'id':'triangle_input','kind':'PULSE','source':'Vin','node_positive':'Vin','node_negative':'0','parameters':{'v1':2.0,'v2':3.0,'delay':0.0,'rise':0.05,'fall':0.05,'width':1e-9,'period':0.1,'dc_value':2.5},'purpose':'Official differentiator checker triangular-wave construction.'}]
    if task==28:
        return [{'id':'hysteresis_input','kind':'SIN','source':'Vin','node_positive':'Vin','node_negative':'0','parameters':{'offset':2.5,'amplitude':0.8,'frequency':100.0},'purpose':'Official Schmitt checker input.'}]
    return []

def requirements(task):
    if task in AMP_CASES:
        return [
            req('ACP_AMP_ID_FLOOR','Every MOS drain current must exceed 10 uA at the operating point.','minimum_device_drain_current_a','op_bias','>',1e-5,unit='A',status='executable',notes='Auxiliary ngspice OP-bias probe evaluates min(abs(Id)).'),
            req('ACP_AMP_GAIN','Low-frequency voltage gain magnitude must exceed 1e-5 V/V.','dc_gain_db','ac_gain','>',-100.0,unit='dB',equiv='semantic',notes='-100 dB = 20log10(1e-5); transfer ratio is amplitude invariant.'),
        ]
    if task in {6,7}:
        return [
            req('ACP_INV_HIGH','With Vin=5 V, Vout must be at or below 2.5 V.','inverter_high_input_output_v','dc_logic','<=',2.5,unit='V'),
            req('ACP_INV_LOW','With Vin=0 V, Vout must be at or above 2.5 V.','inverter_low_input_output_v','dc_logic','>=',2.5,unit='V'),
            req('ACP_INV_SEPARATION','The low-input and high-input output levels must differ by at least 1 V.','inverter_output_separation_v','dc_logic','>=',1.0,unit='V'),
        ]
    if task in {8,17}:
        r=[
            req('ACP_CM_STABILITY','Output current must remain approximately constant across the compliance sweep.','current_stability_delta_a','dc_compliance','<',1e-6,unit='A',equiv='adapted',notes='Immutable-DUT adaptation of the official resistive-load sweep.'),
            req('ACP_CM_FLOOR','Output current must remain above 10 uA.','minimum_output_current_a','dc_compliance','>',1e-5,unit='A',equiv='adapted',notes='Evaluated on the immutable-DUT compliance sweep.'),
        ]
        if task==17:
            r.append(req('ACP_CM_IREF','Changing Iref must measurably change the output current.','iref_replication_error_a','dc_compliance','>=',1e-6,unit='A',status='metadata_only',equiv='adapted',notes='Official checker mutates Iref; frozen deterministic baseline keeps the DUT/spec immutable and does not execute this perturbation.'))
        return r
    if task==9:
        return [
            req('ACP_COMP_SEPARATION','Average high-region output must exceed low-region output by at least 2 V.','comparator_output_separation_v','dc_transfer','>=',2.0,unit='V'),
            req('ACP_COMP_MONOTONIC','Comparator transfer must be at least 90% monotonic under the checker tolerance.','comparator_monotonicity_percent','dc_transfer','>=',90.0,unit='% ',equiv='semantic'),
        ]
    if task==10:
        return [req('ACP_LP_ATTENUATION','High-frequency attenuation relative to low-frequency gain must exceed 2 dB.','lowpass_attenuation_db','ac_filter','>',2.0,unit='dB'),req('ACP_LP_MONOTONIC','Low-pass response must be at least 90% monotonically decreasing.','lowpass_monotonicity_percent','ac_filter','>=',90.0,unit='%')]
    if task==11:
        return [req('ACP_HP_ATTENUATION','Low-frequency attenuation relative to high-frequency gain must exceed 2 dB.','highpass_attenuation_db','ac_filter','>',2.0,unit='dB'),req('ACP_HP_MONOTONIC','High-pass response must be at least 90% monotonically increasing.','highpass_monotonicity_percent','ac_filter','>=',90.0,unit='%')]
    if task==12:
        return [req('ACP_BP_PEAK','Band-pass peak must stand at least 10 dB above both stopband sides.','bandpass_peak_separation_db','ac_filter','>=',10.0,unit='dB',equiv='semantic')]
    if task==13:
        return [req('ACP_BS_NOTCH','Band-stop notch must be at least 10 dB below both passband sides.','bandstop_notch_depth_db','ac_filter','>=',10.0,unit='dB',equiv='semantic')]
    if task in OPAMP_CASES:
        return [
            req('ACP_OP_ID_FLOOR','Every MOS drain current must exceed 10 uA at the operating point.','minimum_device_drain_current_a','op_bias','>',1e-5,unit='A',status='executable',notes='Auxiliary ngspice OP-bias probe evaluates min(abs(Id)).'),
            req('ACP_OP_DIFF_GAIN','Differential-mode gain magnitude must exceed 1e-5 V/V.','differential_gain_linear','ac_modes','>',1e-5,unit='V/V',status='metadata_only'),
            req('ACP_OP_MODE_REJECTION','Differential gain must exceed common-mode gain by at least 1e-5.','differential_minus_common_gain','ac_modes','>',1e-5,unit='V/V',status='metadata_only'),
        ]
    if task==19:
        return [req('ACP_MIX_IF_DOWN','Down-conversion IF magnitude near 200 Hz must exceed 1 mV.','mixer_if_down_magnitude_v','fft_mix','>',1e-3,unit='V',status='metadata_only'),req('ACP_MIX_IF_UP','Up-conversion IF magnitude near 2.2 kHz must exceed 1 mV.','mixer_if_up_magnitude_v','fft_mix','>',1e-3,unit='V',status='metadata_only')]
    if task in {22,23}:
        return [req('ACP_OSC_CYCLES','More than two peaks must be detected in the latter half of the waveform.','oscillation_cycle_count','tran_osc','>',2.0,unit='cycles',equiv='semantic'),req('ACP_OSC_SWING','Peak-to-peak oscillator output must exceed 5 uV.','output_swing_v','tran_osc','>',5e-6,unit='V'),req('ACP_OSC_PERIOD_CV','Coefficient of variation of detected periods must be below 0.2.','oscillation_period_cv','tran_osc','<',0.2,unit='')]
    if task==24:
        exp=0.5/0.03
        return [req('ACP_INT_SLOPE','Integrator ramp slope must match 0.5/(10k*3u) within 30%.','integrator_ramp_slope','tran_integrator','between',minimum=exp*0.7,maximum=exp*1.3,unit='V/s',equiv='semantic'),req('ACP_INT_LINEAR','The fitted integration ramp must have R^2 >= 0.9.','integrator_linearity','tran_integrator','>=',0.9,unit='')]
    if task==25:
        return [req('ACP_DIFF_AMPLITUDE','Differentiator output level magnitude around the 2.5 V bias must be 0.6 V within 20%.','differentiator_output_amplitude_v','tran_diff','between',minimum=0.48,maximum=0.72,unit='V',equiv='semantic'),req('ACP_DIFF_SHAPE','Differentiator output must exhibit the square-wave shape test used by the checker.','differentiator_square_wave_score','tran_diff','>=',0.9,unit='',status='metadata_only',equiv='adapted')]
    if task==26:
        return [req('ACP_ADD_EFFECT1','Increasing Vin1 by 0.5 V must decrease Vout by at least 0.05 V.','adder_vin1_effect','dc_grid','<=',-0.05,unit='V',status='metadata_only',equiv='semantic'),req('ACP_ADD_EFFECT2','Increasing Vin2 by 0.5 V must decrease Vout by at least 0.05 V.','adder_vin2_effect','dc_grid','<=',-0.05,unit='V',status='metadata_only',equiv='semantic'),req('ACP_ADD_BALANCE','Magnitude ratio of Vin1 and Vin2 effects must lie within 20% of unity.','adder_effect_ratio','dc_grid','between',minimum=0.8,maximum=1.2,unit='',status='metadata_only'),req('ACP_ADD_FORMULA','Adder grid points must follow the fitted inverting-adder formula within 20%.','adder_formula_error','dc_grid','<=',0.2,unit='relative',status='metadata_only',equiv='semantic')]
    if task==27:
        return [req('ACP_SUB_FORMULA','Subtractor output must match Vout=Vin2-Vin1 within the checker 20% tolerance.','subtractor_formula_error','dc_grid','<=',0.2,unit='relative',status='metadata_only',equiv='semantic')]
    if task==28:
        return [req('ACP_SCH_HYST','Rising and falling trigger points must differ by more than 10 mV.','hysteresis_width','tran_hyst','>',0.01,unit='V'),req('ACP_SCH_SWING','Output swing must be at least 2.5 V.','output_swing_v','tran_hyst','>=',2.5,unit='V')]
    raise KeyError(task)

rows=list(csv.DictReader(MAN.open(newline='',encoding='utf-8')))
manifest={'schema_version':'1.0','benchmark':'AnalogCoder-Pro','benchmark_subset':'ACP-28 adapted p01-p28','immutable_dut':True,'cases':[]}
for row in rows:
    task=int(row['id']); specname=row['spec']; netname=row['netlist']
    old=yaml.safe_load((OLD/specname).read_text())
    net=ROOT/'benchmark/analogcoder_pro'/netname
    text=net.read_text(encoding='utf-8',errors='replace')
    ins=split_nodes(old.get('input_conditions',{}).get('input_nodes'))
    outs=split_nodes(old.get('input_conditions',{}).get('output_nodes'))
    dcvals=source_dc_values(text)
    vdd=dcvals.get('vdd',5.0)
    typ=row['type']
    ctype=old['circuit_type']
    rs=requirements(task)
    # Strict role map
    ports={'input':ins,'output':outs,'differential_positive':[],'differential_negative':[], 'common_mode':[],
           'supply_positive':['Vdd'] if re.search(r'(?im)^Vdd\s+Vdd\s+0\s+',text) else [],'supply_negative':['0'],
           'bias':[n for n in ins if 'bias' in n.lower()], 'reference':[n for n in ins if 'ref' in n.lower()],
           'loop_break':[],'loop_injection':[],'current_probe':[]}
    if task in OPAMP_CASES:
        ports['differential_positive']=['Vinp']; ports['differential_negative']=['Vinn']; ports['input']=[n for n in ins if n not in {'Vbias','Vbias1','Vbias2','Vbias3','Vbias4'}]
        ports['bias']=[n for n in ins if 'bias' in n.lower()]
    if task==17: ports['current_probe']=['Iref','Iout']
    spec={
      'schema_version':'2.0','case_id':f'acp28-p{task:02d}','name':f'analogcoder_pro_p{task:02d}_{Path(netname).stem.split("_",1)[1]}',
      'circuit_type':ctype,'technology':'AnalogCoder-Pro generic Level-1 benchmark models','description':row['description'],
      'provenance':{
        'benchmark':'AnalogCoder-Pro','benchmark_subset':'ACP-28','upstream_repository':'https://github.com/laiyao1/AnalogCoderPro',
        'upstream_task_id':task,'upstream_level':row['level'],'upstream_type':typ,'upstream_task_description':row['description'],
        'upstream_testbench_description':old.get('input_conditions',{}).get('testbench_note',''),
        'official_checker':{'path':f'problem_check/{typ}.py','criterion_summary':[r['description'] for r in rs],
                            'upstream_mutates_dut': task in {8,17,24,25,26,27,28},
                            'notes':'Criterion semantics reconstructed from the local pinned AnalogCoder-Pro checker shipped with the uploaded base.'},
        'dut':{'path':f'benchmark/analogcoder_pro/{netname}','sha256':hashlib.sha256(net.read_bytes()).hexdigest(),
               'canonicalization':'Uploaded ACP-28 DUT bytes preserved; embedded analyses/output directives are externalized at execution.',
               'topology_and_values_preserved':True},
      },
      'ports':ports,
      'operating_conditions':{'nominal_temperature':25.0,'nominal_supply':vdd if vdd else None,'process_corner':'tt'},
      'stimuli':stimuli_for(task,ins,dcvals), 'analyses':analyses_for(task), 'functional_requirements':rs,
      'performance_targets':targets(rs,vdd or 5.0),
      'input_conditions':{'vdd':vdd or 5.0,'vss':0.0,'vcm':old.get('input_conditions',{}).get('vcm',2.5),'input_nodes':ins,'output_nodes':outs,'temperature':25.0,'original_source_dc_values':dcvals},
      'measurement':{'backend':'AUTO','allow_fallback':True},
      'verification':{'auto_select':True,'include_tests':[],'exclude_tests':[],'required_policy':'all','immutable_dut':True,'not_evaluated_on_missing_mandatory_metric':True,'require_full_contract_for_compliance':True},
      'test_requirements':{'dc_sweep_step_v':0.01},'test_categories':sorted({a['type'].lower().replace('op','dc') for a in analyses_for(task)}),
      'pvt_config':{'corners':['tt'],'temperature_range':'commercial','supply_variation':0.0},
    }
    (DST/specname).write_text(yaml.safe_dump(spec,sort_keys=False,allow_unicode=True),encoding='utf-8')
    manifest['cases'].append({'case_id':spec['case_id'],'task_id':task,'level':row['level'],'type':typ,'spec_path':f'benchmark/analogcoder_pro/specs/{specname}','netlist_path':f'benchmark/analogcoder_pro/{netname}','netlist_sha256':spec['provenance']['dut']['sha256']})

(ROOT/'benchmark/analogcoder_pro/acp28_manifest.yaml').write_text(yaml.safe_dump(manifest,sort_keys=False,allow_unicode=True),encoding='utf-8')
print('wrote',len(rows),'specs')
print('mandatory',sum(len(requirements(i)) for i in range(1,29)))
print('metadata_only',sum(sum(r['implementation_status']=='metadata_only' for r in requirements(i)) for i in range(1,29)))
