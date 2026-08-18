from spec2testbench.application.services.acp_benchmark_runner import CriterionEvidence,circuit_compliance,summarize_runs,evaluate_operator

def row(case,status,analysis='dc'):
    return CriterionEvidence(case,'R','m',analysis,'executable',status,1.0,'','>',0,None,None,'official_checker','exact','')

def test_fail_dominates_missing_contract_evidence():
    assert circuit_compliance([row('c','FAIL'),row('c','NOT_IMPLEMENTED')])=='NONCOMPLIANT'

def test_missing_without_fail_is_not_evaluated():
    assert circuit_compliance([row('c','PASS'),row('c','NOT_IMPLEMENTED')])=='NOT_EVALUATED'

def test_compliant_requires_all_pass():
    assert circuit_compliance([row('c','PASS'),row('c','PASS')])=='COMPLIANT'

def test_between_operator():
    assert evaluate_operator(2,{'operator':'between','minimum':1,'maximum':3})
    assert not evaluate_operator(4,{'operator':'between','minimum':1,'maximum':3})

def test_summary_coverage_definitions():
    runs=[{'case_id':'a','execution_status':'SUCCESS','compliance_status':'COMPLIANT'}, {'case_id':'b','execution_status':'SUCCESS','compliance_status':'NONCOMPLIANT'}, {'case_id':'c','execution_status':'ERROR','compliance_status':'NOT_EVALUATED'}]
    cr=[row('a','PASS','ac'),row('b','FAIL','dc'),row('c','NOT_EVALUATED','tran')]
    s=summarize_runs(runs,cr)
    assert s['evaluation_rate']==2/3 and s['verified_compliance_yield']==1/3 and s['Cov_metrics']==2/3 and s['Cov_circuits']==2/3 and s['Cov_analyses']==2/3
