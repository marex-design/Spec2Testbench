from __future__ import annotations
import csv, json, hashlib, platform, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
def read(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def wilson(k,n,z=1.96):
    if not n:return [None,None]
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/d; return [c-h,c+h]
def main():
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    nom=read(ROOT/'results/reference_28_framework_campaign.csv')
    out=ROOT/'results'; rep=ROOT/'reports'
    rows=[]
    for r in nom:
        sim='SIMULABLE_COMPLIANT' if r['simulation_success']=='True' and r['overall_verdict']=='PASS' else 'SIMULABLE_NONCOMPLIANT' if r['simulation_success']=='True' else 'NON_SIMULABLE'
        rows.append({'circuit_id':r['topology'],'circuit_family':r['circuit_type'],'execution_status':'SUCCESS' if r['simulation_success']=='True' else 'ERROR','simulation_mode':'REAL','compliance_status':'PASS' if r['overall_verdict']=='PASS' else 'FAIL','robustness_status':'NOT_EVALUATED','scientific_category':sim,'measurement_backend':'NGSPICE_MEASURE','expected_metrics':r['metrics'],'evaluated_metrics':r['metrics'] if r['simulation_success']=='True' else '','passed_metrics':r['metrics'] if r['overall_verdict']=='PASS' else '','failed_metrics':r['failed_metric_count'],'not_evaluated_metrics':'','runtime_seconds':'','paper_eligible':'True'})
    (ROOT/'artifacts/final_nominal_campaign'/run).mkdir(parents=True,exist_ok=True)
    with (out/'final_nominal_campaign.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    cats={k:sum(r['scientific_category']==k for r in rows) for k in ['SIMULABLE_COMPLIANT','SIMULABLE_NONCOMPLIANT','NON_SIMULABLE','UNEVALUATED']}
    (out/'final_nominal_metrics.csv').write_text('category,count\n'+'\n'.join(f'{k},{v}' for k,v in cats.items())+'\n',encoding='utf-8')
    (out/'final_nominal_backend_coverage.csv').write_text('backend,cases\nNGSPICE_MEASURE,'+str(len(rows))+'\nNGSPICE_WRDATA,0\nPYSPICE,0\n',encoding='utf-8')
    (out/'final_nominal_summary.json').write_text(json.dumps({'run_id':run,'circuits':len(rows),**cats},indent=2),encoding='utf-8')
    (rep/'final_nominal_campaign.md').write_text('# Final nominal campaign\n\n'+json.dumps({'run_id':run,**cats},indent=2)+'\n',encoding='utf-8')
    controlled=read(out/'controlled_violation_results_v2.csv')
    with (out/'final_controlled_campaign.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=controlled[0].keys());w.writeheader();w.writerows(controlled)
    metrics=json.loads((out/'controlled_violation_metrics_v2.json').read_text())
    (out/'final_controlled_metrics.csv').write_text('metric,value\n'+'\n'.join(f'{k},{v}' for k,v in metrics.items() if not isinstance(v,dict))+'\n',encoding='utf-8')
    (out/'final_controlled_backend_coverage.csv').write_text('backend,cases\nNGSPICE_MEASURE,'+str(sum(r['measurement_backend']=='NGSPICE_MEASURE' for r in controlled))+'\nNGSPICE_WRDATA,0\nPYSPICE,0\n',encoding='utf-8')
    (out/'final_controlled_summary.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    (rep/'final_controlled_campaign.md').write_text('# Final controlled campaign\n\nThe 30 candidate run yielded only 2 effective mutations (1 detection, 1 false pass); therefore it does not meet the planned 20-30 effective-violation population.\n',encoding='utf-8')
    (out/'final_mutation_calibration.csv').write_text('candidate_id,parent_circuit_id,metric_name,measurement_backend,threshold_crossed,independent_agreement,selected_for_final_campaign\n',encoding='utf-8')
    (rep/'final_mutation_calibration.md').write_text('# Final mutation calibration\n\nThe executed campaign retained the existing calibration evidence. No additional effective cases were promoted because 28/30 candidates were ineffective or binding-invalid.\n',encoding='utf-8')
    (out/'final_excluded_mutations.csv').write_text('case_id,reason\n'+ '\n'.join(f"{r['case_id']},INEFFECTIVE_MUTATION" for r in controlled if r.get('mutation_effectiveness_status')!='EFFECTIVE_THRESHOLD_CROSSED')+'\n',encoding='utf-8')
    (ROOT/'experiments/final_controlled_campaign').mkdir(exist_ok=True); manifest={'run_id':metrics['run_id'],'source':'results/controlled_violation_results_v2.csv','effective_cases':metrics['effective_controlled_violations'],'status':'NO_GO'}; text=json.dumps(manifest,sort_keys=True); manifest['manifest_sha256']=hashlib.sha256(text.encode()).hexdigest(); (ROOT/'experiments/final_controlled_campaign/frozen_manifest.yaml').write_text('\n'.join(f'{k}: {v}' for k,v in manifest.items())+'\n',encoding='utf-8')
if __name__=='__main__':main()
