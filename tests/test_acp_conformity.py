from spec2testbench.application.services.acp_conformity import (
    normalize_contract_status,
    summarize_acp_records,
)


def test_missing_mandatory_evidence_never_becomes_pass():
    row = {
        "execution_status": "SUCCESS",
        "compliance_status": "COMPLIANT",
        "contract_coverage": 0.5,
        "failed_mandatory_requirements": 0,
        "missing_mandatory_requirements": 1,
    }
    assert normalize_contract_status(row) == "NOT_EVALUATED"


def test_measured_mandatory_failure_is_noncompliant_even_if_contract_incomplete():
    row = {
        "execution_status": "SUCCESS",
        "contract_coverage": 0.5,
        "failed_mandatory_requirements": 1,
        "missing_mandatory_requirements": 1,
    }
    assert normalize_contract_status(row) == "FAIL"


def test_summary_reports_evaluation_and_verified_yield_separately():
    rows = [
        {"execution_status": "SUCCESS", "contract_status": "PASS", "contract_coverage": 1.0},
        {"execution_status": "SUCCESS", "contract_status": "FAIL", "contract_coverage": 1.0},
        {"execution_status": "SUCCESS", "contract_status": "NOT_EVALUATED", "contract_coverage": 0.5},
        {"execution_status": "ERROR", "contract_status": "NOT_EVALUATED", "contract_coverage": 0.0},
    ]
    s = summarize_acp_records(rows)
    assert s.circuits_total == 4
    assert s.simulation_success == 3
    assert s.evaluated == 2
    assert s.compliant == 1
    assert s.noncompliant == 1
    assert s.not_evaluated == 2
    assert s.simulation_success_rate == 0.75
    assert s.evaluation_rate == 0.5
    assert s.compliance_rate_evaluated == 0.5
    assert s.verified_compliance_yield == 0.25
