from spec2testbench.application.services.evaluation_metrics import (
    confusion_from_rows,
    majority_vote_rows,
    mcnemar_exact,
    wilson_interval,
)


def test_majority_vote_and_case_level_confusion():
    rows = [
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "FAIL"},
        {"case_id": "b", "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "FAIL"},
        {"case_id": "b", "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "FAIL"},
        {"case_id": "b", "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "PASS"},
    ]
    case_rows = majority_vote_rows(rows)
    assert [r["compliance_status"] for r in case_rows] == ["PASS", "FAIL"]
    cm = confusion_from_rows(case_rows)
    assert (cm.tp, cm.tn, cm.fp, cm.fn) == (1, 1, 0, 0)
    data = cm.to_dict()
    assert 0.0 <= data["accuracy_ci95"]["low"] <= data["accuracy_ci95"]["high"] <= 1.0


def test_majority_tie_is_explicitly_excluded():
    rows = [
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "FAIL"},
    ]
    case_rows = majority_vote_rows(rows)
    assert case_rows[0]["compliance_status"] == "NOT_EVALUATED"
    cm = confusion_from_rows(case_rows)
    assert cm.total == 0
    assert cm.excluded == 1


def test_exact_mcnemar_detects_direction_of_discordance():
    left = [
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "FAIL"},
        {"case_id": "b", "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "PASS"},
        {"case_id": "c", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
    ]
    right = [
        {"case_id": "a", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
        {"case_id": "b", "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT", "compliance_status": "FAIL"},
        {"case_id": "c", "ground_truth_label": "GROUND_TRUTH_COMPLIANT", "compliance_status": "PASS"},
    ]
    out = mcnemar_exact(left, right)
    assert out["paired_cases"] == 3
    assert out["left_correct_right_wrong"] == 0
    assert out["left_wrong_right_correct"] == 2
    assert out["discordant_pairs"] == 2
    assert out["exact_two_sided_p_value"] == 0.5


def test_wilson_empty_is_defined():
    assert wilson_interval(0, 0) == {"low": 0.0, "high": 0.0}
