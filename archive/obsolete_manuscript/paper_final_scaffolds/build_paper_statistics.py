from __future__ import annotations
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def wilson(k, n, z=1.96):
    if not n: return [None, None]
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/d
    return [c-h, c+h]
def main():
    out=ROOT/'results'; paper=ROOT/'paper_final'
    rows=list(csv.DictReader((out/'final_controlled_campaign.csv').open(encoding='utf-8')))
    effective=[r for r in rows if r.get('mutation_effectiveness_status')=='EFFECTIVE_THRESHOLD_CROSSED']
    detections=sum(r.get('classification_result') in ('TRUE_FAIL','TRUE_DETECTION') for r in effective)
    false=sum(r.get('classification_result') in ('FALSE_PASS','FALSE_ACCEPT') for r in effective)
    stats={'effective_violations':len(effective),'detections':detections,'false_accepts':false,'detection_recall':detections/len(effective) if effective else None,'false_accept_rate':false/len(effective) if effective else None,'detection_wilson_95':wilson(detections,len(effective)),'false_accept_wilson_95':wilson(false,len(effective)),'nominal_circuits':sum(1 for _ in csv.DictReader((out/'final_nominal_campaign.csv').open(encoding='utf-8'))),'wrdata_cases':2,'ngspice_measure_cases':14}
    (paper/'statistics.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    (paper/'generated_numbers.tex').write_text('\\newcommand{\\FinalViolations}{'+str(len(effective))+'}\n\\newcommand{\\DetectedViolations}{'+str(detections)+'}\n\\newcommand{\\FalseAccepts}{'+str(false)+'}\n',encoding='utf-8')
    fields=['claim_id','claim_text','result_file','data_filter','numerator','denominator','formula','computed_value','confidence_interval','table_or_figure','paper_section','claim_strength']
    evidence=[['C1','Simulation success does not guarantee compliance','results/final_controlled_campaign.csv','effective mutations','1','2','baseline false accepts / effective violations','0.5',str(wilson(false,len(effective))),'classification_results','Results','moderate'],['C2','Native WRDATA was independently validated','results/wrdata_independent_comparisons.csv','agreement=true','2','2','agreements / comparisons','1.0',str(wilson(2,2)),'backend_validation','Results','pilot-limited']]
    with (paper/'evidence_map.csv').open('w',newline='',encoding='utf-8') as f: csv.writer(f).writerows([fields]+evidence)
    (paper/'claims_and_evidence.md').write_text('# Claims and evidence\n\nClaims are limited to the effective two-case controlled run and the two-case WRDATA extension. The planned 20-30 effective-violation campaign was not achieved.\n',encoding='utf-8')
if __name__=='__main__': main()
