"""Deterministic ACP-28 benchmark runner.

The runner keeps three domains separate:
1. ngspice execution status;
2. criterion evidence status;
3. circuit compliance status.
Simulation success is never treated as proof of compliance.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from collections import Counter
import csv, hashlib, json, math, time
import yaml

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import TestBench
from spec2testbench.domain.value_objects.scientific_status import CriterionStatus, ExecutionStatus
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor

@dataclass
class CriterionEvidence:
    case_id: str
    requirement_id: str
    metric: str
    analysis: str
    implementation_status: str
    criterion_status: str
    measured_value: Optional[float]
    unit: str
    operator: str
    threshold: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    criterion_source: str
    equivalence: str
    message: str


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()


def evaluate_operator(value: float, req: Dict[str, Any]) -> bool:
    op=str(req.get('operator','')).strip().lower(); threshold=req.get('threshold'); lo=req.get('minimum'); hi=req.get('maximum')
    if op in {'>','gt'}: return value > float(threshold)
    if op in {'>=','ge'}: return value >= float(threshold)
    if op in {'<','lt'}: return value < float(threshold)
    if op in {'<=','le'}: return value <= float(threshold)
    if op in {'==','=','eq'}: return math.isclose(value,float(threshold),rel_tol=1e-12,abs_tol=1e-15)
    if op=='between':
        return (lo is None or value>=float(lo)) and (hi is None or value<=float(hi))
    raise ValueError(f'Unsupported requirement operator: {op}')


def evaluate_contract(spec: Specification, results: Dict[str, Any], execution_status: str) -> list[CriterionEvidence]:
    ex=MetricExtractor(); out=[]
    for req in spec.mandatory_requirements():
        metric=str(req.get('metric'))
        if req.get('implementation_status')!='executable':
            out.append(CriterionEvidence(spec.case_id,req['id'],metric,req.get('analysis',''),req.get('implementation_status','metadata_only'),CriterionStatus.NOT_IMPLEMENTED.value,None,req.get('unit',''),req.get('operator',''),req.get('threshold'),req.get('minimum'),req.get('maximum'),req.get('criterion_source',''),req.get('equivalence',''), 'Deterministic runtime does not implement this mandatory criterion.'))
            continue
        if str(execution_status).upper()!=ExecutionStatus.SUCCESS.value:
            out.append(CriterionEvidence(spec.case_id,req['id'],metric,req.get('analysis',''),'executable',CriterionStatus.NOT_EVALUATED.value,None,req.get('unit',''),req.get('operator',''),req.get('threshold'),req.get('minimum'),req.get('maximum'),req.get('criterion_source',''),req.get('equivalence',''),'Simulation was not successful; no compliance value is promoted from partial evidence.'))
            continue
        executable=str(req.get('executable_metric') or metric)
        value=ex.extract(results,executable)
        if value is None or not math.isfinite(float(value)):
            out.append(CriterionEvidence(spec.case_id,req['id'],metric,req.get('analysis',''),'executable',CriterionStatus.NOT_EVALUATED.value,None,req.get('unit',''),req.get('operator',''),req.get('threshold'),req.get('minimum'),req.get('maximum'),req.get('criterion_source',''),req.get('equivalence',''),f'Metric {executable} has no usable runtime evidence.'))
            continue
        passed=evaluate_operator(float(value),req); status=CriterionStatus.PASS.value if passed else CriterionStatus.FAIL.value
        out.append(CriterionEvidence(spec.case_id,req['id'],metric,req.get('analysis',''),'executable',status,float(value),req.get('unit',''),req.get('operator',''),req.get('threshold'),req.get('minimum'),req.get('maximum'),req.get('criterion_source',''),req.get('equivalence',''),f'{executable}={float(value):.12g} {req.get("unit","")} -> {status}'))
    return out


def circuit_compliance(rows: Iterable[CriterionEvidence]) -> str:
    rows=list(rows)
    statuses={r.criterion_status for r in rows}
    if CriterionStatus.FAIL.value in statuses: return 'NONCOMPLIANT'
    if rows and all(r.criterion_status==CriterionStatus.PASS.value for r in rows): return 'COMPLIANT'
    return 'NOT_EVALUATED'


def _merge_results(dst: Dict[str,Any], src: Dict[str,Any]) -> None:
    for key in ('dc','ac','tran','transient','fourier','pvt'):
        if src.get(key): dst[key]=src[key]
    for key in ('metrics','native_metrics','currents'):
        if isinstance(src.get(key),dict): dst.setdefault(key,{}).update(src[key])
    if src.get('op_bias_probe'): dst['op_bias_probe']=src['op_bias_probe']
    dst.setdefault('logs',[]).extend(src.get('logs',[])); dst.setdefault('errors',[]).extend(src.get('errors',[]))


def simulate_spec(spec: Specification, netlist: Path, output_dir: Path, simulator: PySpiceSimulator) -> Dict[str,Any]:
    generator=TestBenchGenerator(use_llm=False); full=generator.generate(spec,netlist_path=netlist)
    aggregated={'metrics':{},'native_metrics':{},'dc':{},'ac':{},'tran':{},'transient':{},'fourier':{},'currents':{},'logs':[],'errors':[],'analysis_runs':[]}
    # Run only declared analyses. Each pass has one plot, making raw extraction deterministic.
    overall_success=True
    analysis_ids=[]
    for i,(analysis_decl,analysis_cfg) in enumerate(zip(spec.analyses,full.analyses)):
        analysis_id=str(analysis_decl.get('id',f'analysis_{i}')); analysis_ids.append(analysis_id)
        # Measurements belonging to this analysis only. OP probe is automatically included when required.
        metrics={str(r.get('executable_metric')) for r in spec.mandatory_requirements() if r.get('implementation_status')=='executable' and r.get('analysis')==analysis_id and r.get('executable_metric')}
        measurements=[m for m in full.measurements if m.name in metrics]
        # Skip analyses that exist only for metadata-only requirements EXCEPT keep an execution smoke pass so simulation status remains a real property.
        pass_tb=TestBench(name=f'{full.name}_{analysis_id}',category=analysis_id,circuit_name=full.circuit_name,netlist_path=full.netlist_path,
                          stimuli=list(full.stimuli),analyses=[analysis_cfg],measurements=measurements,temperature=full.temperature,
                          metadata=dict(full.metadata))
        pass_tb.metadata['required_metrics']=[m.name for m in measurements]
        pass_tb.metadata['needs_op_bias_probe']='minimum_device_drain_current_a' in pass_tb.metadata['required_metrics']

        # External differential AC metric (post-freeze extension).
        # ACP-28 metadata-only differential criteria remain unchanged.
        if 'differential_gain_db' in metrics:
            input_nodes = spec.ports.get('input') or []
            output_nodes = spec.ports.get('output') or []

            if len(input_nodes) < 2:
                raise ValueError(
                    'differential_gain_db requires two input nodes'
                )

            if not output_nodes:
                raise ValueError(
                    'differential_gain_db requires one output node'
                )

            declared_parameters = dict(
                analysis_decl.get('parameters') or {}
            )

            reference_frequency_hz = float(
                declared_parameters.get(
                    'reference_frequency_hz',
                    1000.0,
                )
            )

            pass_tb.metadata['measurement_requests'] = [
                {
                    'metric_name': 'differential_gain_db',
                    'analysis_type': 'AC',
                    'input_positive_node': input_nodes[0],
                    'input_negative_node': input_nodes[1],
                    'output_node': output_nodes[0],
                    'expected_unit': 'dB',
                    'reference_frequency_hz': reference_frequency_hz,
                    'in_pos_real_column': 1,
                    'in_pos_imag_column': 2,
                    'in_neg_real_column': 3,
                    'in_neg_imag_column': 4,
                    'out_real_column': 5,
                    'out_imag_column': 6,
                }
            ]

        run_dir=Path(output_dir)/'simulation'/analysis_id
        result=simulator.run(netlist,pass_tb,output_dir=run_dir)
        _merge_results(aggregated,result)
        aggregated['analysis_runs'].append({'analysis_id':analysis_id,'execution_status':result.get('execution_status'),'success':result.get('success'),'error_type':result.get('error_type'),'artifact_dir':result.get('artifact_dir')})
        if not result.get('success'): overall_success=False
    aggregated['success']=overall_success
    aggregated['execution_status']=ExecutionStatus.SUCCESS.value if overall_success else ExecutionStatus.ERROR.value
    aggregated['simulation_mode']='REAL' if simulator.is_available else ('MOCK' if simulator.allow_mock else 'NONE')
    if not overall_success:
        errors=[r for r in aggregated['analysis_runs'] if not r.get('success')]
        aggregated['error_type']=errors[0].get('error_type') if errors else 'simulation_error'
    return aggregated


def summarize_runs(runs: list[dict], criteria: list[CriterionEvidence]) -> Dict[str,Any]:
    n=len(runs); status=Counter(r['compliance_status'] for r in runs); sim=Counter(r['execution_status'] for r in runs); cstatus=Counter(r.criterion_status for r in criteria)
    conclusive=status['COMPLIANT']+status['NONCOMPLIANT']; usable=sum(cstatus[x] for x in ('PASS','FAIL')); total=len(criteria)
    useful_cases={r.case_id for r in criteria if r.criterion_status in {'PASS','FAIL'}}
    all_analyses={r.analysis for r in criteria if r.analysis}; usable_analyses={r.analysis for r in criteria if r.analysis and r.criterion_status in {'PASS','FAIL'}}
    return {
        'circuits':n,'simulation_success':sim[ExecutionStatus.SUCCESS.value],
        'COMPLIANT':status['COMPLIANT'],'NONCOMPLIANT':status['NONCOMPLIANT'],'NOT_EVALUATED':status['NOT_EVALUATED'],
        'evaluation_rate':conclusive/n if n else 0.0,'compliance_evaluated':status['COMPLIANT']/conclusive if conclusive else 0.0,
        'verified_compliance_yield':status['COMPLIANT']/n if n else 0.0,
        'Cov_circuits':len(useful_cases)/n if n else 0.0,'Cov_metrics':usable/total if total else 0.0,
        'Cov_analyses':len(usable_analyses)/len(all_analyses) if all_analyses else 0.0,
        'criterion_counts':dict(cstatus),'mandatory_criteria':total,'usable_metric_evidence':usable,
        'analysis_types_total':len(all_analyses),'analysis_types_with_evidence':len(usable_analyses),
    }


def run_single_case(spec_path: Path, netlist_path: Path, output_dir: Path, *, ngspice_path: Optional[str]=None, allow_mock: bool=False, timeout_seconds: float=300) -> Dict[str,Any]:
    spec_path=Path(spec_path); netlist_path=Path(netlist_path); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    spec=Specification.from_yaml(spec_path)

    # Prefer an ngspice executable available in the active OS PATH.
    # This avoids carrying a stale Windows path into Ubuntu/WSL.
    if ngspice_path is None:
        import shutil
        ngspice_path = shutil.which('ngspice')

    simulator=PySpiceSimulator(
        ngspice_path=ngspice_path,
        allow_mock=allow_mock,
        timeout_seconds=timeout_seconds,
    )
    expected=(spec.provenance.get('dut') or {}).get('sha256'); actual=sha256_file(netlist_path); hash_ok=(expected is None or expected==actual)
    if hash_ok: result=simulate_spec(spec,netlist_path,output_dir,simulator)
    else: result={'success':False,'execution_status':ExecutionStatus.ERROR.value,'simulation_mode':'NONE','error_type':'dut_hash_mismatch','metrics':{}}
    criteria=evaluate_contract(spec,result,result.get('execution_status',ExecutionStatus.ERROR.value)); compliance=circuit_compliance(criteria)
    report={'case_id':spec.case_id,'circuit_name':spec.name,'execution_status':result.get('execution_status'),
            'simulation_mode':result.get('simulation_mode'),'simulation_success':bool(result.get('success')),
            'compliance_status':compliance,'error_type':result.get('error_type'),'error_message':result.get('error_message'),
            'netlist_sha256':actual,'dut_hash_ok':hash_ok,'criteria':[asdict(x) for x in criteria],
            'metrics':result.get('metrics',{}),'native_metrics':result.get('native_metrics',{}),'analysis_runs':result.get('analysis_runs',[])}
    (output_dir/'verification_report.json').write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    return report


def run_acp_benchmark(manifest_path: Path, output_dir: Path, *, ngspice_path: Optional[str]=None, allow_mock: bool=False, timeout_seconds: float=300) -> Dict[str,Any]:
    manifest_path=Path(manifest_path); root=Path.cwd(); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    manifest=yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    simulator=PySpiceSimulator(ngspice_path=ngspice_path,allow_mock=allow_mock,timeout_seconds=timeout_seconds)
    runs=[]; all_criteria=[]
    for case in manifest.get('cases',[]):
        started=time.time(); spec_path=root/case['spec_path']; netlist=root/case['netlist_path']; spec=Specification.from_yaml(spec_path)
        actual_hash=sha256_file(netlist); hash_ok=actual_hash==case.get('netlist_sha256')
        case_dir=output_dir/'cases'/spec.case_id; case_dir.mkdir(parents=True,exist_ok=True)
        if not hash_ok:
            result={'success':False,'execution_status':ExecutionStatus.ERROR.value,'simulation_mode':'NONE','error_type':'dut_hash_mismatch','metrics':{}}
        else:
            result=simulate_spec(spec,netlist,case_dir,simulator)
        criteria=evaluate_contract(spec,result,result.get('execution_status',ExecutionStatus.ERROR.value)); all_criteria.extend(criteria)
        compliance=circuit_compliance(criteria)
        passed=sum(r.criterion_status=='PASS' for r in criteria); failed=sum(r.criterion_status=='FAIL' for r in criteria); missing=sum(r.criterion_status in {'NOT_EVALUATED','NOT_IMPLEMENTED'} for r in criteria)
        run={'case_id':spec.case_id,'task_id':case.get('task_id'),'type':case.get('type'),'level':case.get('level'),'spec_path':case['spec_path'],'netlist_path':case['netlist_path'],
             'netlist_sha256':actual_hash,'dut_hash_ok':hash_ok,'mandatory_requirements':len(criteria),
             'implemented_mandatory_requirements':sum(r.implementation_status=='executable' for r in criteria),
             'declared_contract_implementation_coverage':sum(r.implementation_status=='executable' for r in criteria)/len(criteria) if criteria else 1.0,
             'execution_status':result.get('execution_status'),'simulation_success':bool(result.get('success')),
             'simulation_mode':result.get('simulation_mode'),'compliance_status':compliance,
             'passed_mandatory_requirements':passed,'failed_mandatory_requirements':failed,'missing_mandatory_requirements':missing,
             'metric_count':sum(r.criterion_status in {'PASS','FAIL'} for r in criteria),'runtime_seconds':time.time()-started,
             'error_type':result.get('error_type'),'error':result.get('error_message') or '; '.join(result.get('errors',[])[:5])}
        runs.append(run)
        (case_dir/'result_summary.json').write_text(json.dumps({'run':run,'criteria':[asdict(x) for x in criteria],'analysis_runs':result.get('analysis_runs',[])},indent=2),encoding='utf-8')
    summary=summarize_runs(runs,all_criteria)
    def write_csv(path,rows):
        rows=list(rows)
        if not rows: return
        with Path(path).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    write_csv(output_dir/'runs.csv',runs); write_csv(output_dir/'criteria.csv',[asdict(x) for x in all_criteria])
    (output_dir/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True),encoding='utf-8')
    return {'summary':summary,'runs':runs,'criteria':[asdict(x) for x in all_criteria]}
