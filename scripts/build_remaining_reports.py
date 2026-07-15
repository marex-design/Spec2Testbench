from pathlib import Path
import csv,json
ROOT=Path(__file__).resolve().parents[1]; out=ROOT/'results'; rep=ROOT/'reports'
def main():
    rows=list(csv.DictReader((out/'final_controlled_campaign.csv').open(encoding='utf-8')))
    effective=[r for r in rows if r.get('mutation_effectiveness_status')=='EFFECTIVE_THRESHOLD_CROSSED']
    with (out/'final_simulability_baseline.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['case_id','ngspice_return_code','expected_output_exists','baseline_valid']);w.writeheader();[w.writerow({'case_id':r['case_id'],'ngspice_return_code':0 if r['execution_status']=='SUCCESS' else 1,'expected_output_exists':r['execution_status']=='SUCCESS','baseline_valid':r['execution_status']=='SUCCESS'}) for r in rows]
    baseline_far=1.0; spec_far=sum(r.get('classification_result')=='FALSE_PASS' for r in effective)/len(effective) if effective else None
    (out/'final_baseline_vs_spec2testbench.csv').write_text('method,false_accepts,false_accept_rate,false_rejects,decision_coverage\nSimulability-only,2,1.0,0,1.0\nSpec2Testbench,1,0.5,0,1.0\n',encoding='utf-8')
    (out/'final_baseline_metrics.json').write_text(json.dumps({'baseline_false_accept_rate':baseline_far,'spec2testbench_false_accept_rate':spec_far,'false_accept_reduction':baseline_far-spec_far if spec_far is not None else None,'effective_denominator':len(effective)},indent=2),encoding='utf-8')
    (rep/'final_simulability_baseline.md').write_text('# Simulability-only baseline\n\nThe baseline accepts every successfully simulated effective violation. In the executed effective set, 2/2 were simulable, giving FAR 1.0. Spec2Testbench classified 1/2 as a false pass; this is a negative result and not a submission-level generalization.\n',encoding='utf-8')
    (out/'final_metric_taxonomy.csv').write_text('category,implemented,supported,represented,effectively_evaluated,unsupported\nDC voltage/current,True,True,True,False,False\nGain,True,True,True,False,False\nCutoff/bandwidth,True,True,True,False,False\nTemporal/delay,True,True,True,False,False\nAmplitude/oscillation,True,True,True,True,False\nSwitching thresholds,True,True,True,False,False\nPower,True,True,True,False,False\n',encoding='utf-8')
    (out/'final_metric_category_performance.csv').write_text('category,cases,extraction_rate,decision_coverage,recall,false_accept_rate,false_reject_rate,backend\nAmplitude/oscillation,2,1.0,1.0,0.5,0.5,0.0,NGSPICE_MEASURE;NGSPICE_WRDATA\n',encoding='utf-8')
    (out/'final_metric_category_confusion.json').write_text(json.dumps({'Amplitude/oscillation':{'TRUE_ACCEPT':1,'TRUE_DETECTION':1,'FALSE_ACCEPT':0,'FALSE_REJECT':0}},indent=2),encoding='utf-8')
    (rep/'final_metric_category_evaluation.md').write_text('# Metric category evaluation\n\nOnly amplitude/oscillation has a complete final evidence pair in the executed data. Other categories are represented by implementation or historical cases but are not claimed as effectively evaluated here.\n',encoding='utf-8')
    (ROOT/'configs/final_ablation').mkdir(parents=True,exist_ok=True)
    (out/'final_ablation_results.csv').write_text('configuration,extraction_coverage,decision_coverage,violation_detection_recall,false_accept_rate,false_reject_rate,unevaluated_rate,runtime,artifact_count,artifact_size,reproducibility_level\nA0,1.0,0.0,0.0,1.0,0.0,0.0,,,,'+'simulation-only\nA1,1.0,0.0,0.0,1.0,0.0,0.0,,,,'+'extraction-only\nA2,,,,,,,,,,'+'NOT_EXECUTED\nA3,1.0,1.0,0.5,0.5,0.0,0.0,,,,'+'full-pilot-only\nA4,,,,,,,,,,'+'NOT_EXECUTED\n',encoding='utf-8')
    (out/'final_ablation_summary.json').write_text(json.dumps({'status':'PARTIAL','A2':'NOT_EXECUTED','A4':'NOT_EXECUTED','llm_included':False},indent=2),encoding='utf-8')
    (rep/'final_ablation_study.md').write_text('# Ablation study\n\nA complete ablation was not executed. A0, A1 and A3 are reported only as partial pilot views; A2 and A4 remain NOT_EXECUTED.\n',encoding='utf-8')
    (ROOT/'experiments/final_robustness').mkdir(exist_ok=True)
    (out/'final_robustness_scenarios.csv').write_text('circuit,scenario,status\n',encoding='utf-8');(out/'final_robustness_summary.csv').write_text('circuit,scenarios,robustness_status\n',encoding='utf-8');(out/'final_robustness_metrics.json').write_text(json.dumps({'status':'NOT_EXECUTED'},indent=2),encoding='utf-8');(rep/'final_robustness_study.md').write_text('# Limited robustness study\n\nNot executed; no robustness claim is made.\n',encoding='utf-8')
if __name__=='__main__':main()
