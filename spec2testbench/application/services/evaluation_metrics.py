from __future__ import annotations

from dataclasses import dataclass
from math import comb, sqrt
from typing import Any, Iterable


@dataclass(frozen=True)
class CoverageSummary:
    cov_circuits: float
    cov_metrics: float
    cov_analyses: float
    circuits_total: int
    circuits_covered: int
    metrics_total: int
    metrics_evaluated: int
    analyses_total: int
    analyses_executed: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def compute_coverage(rows: Iterable[dict[str, Any]]) -> CoverageSummary:
    rows = list(rows)
    circuit_ids = {str(row.get("case_id") or row.get("circuit_id") or "") for row in rows}
    circuit_ids.discard("")
    covered_ids = {
        str(row.get("case_id") or row.get("circuit_id") or "")
        for row in rows
        if int(row.get("evaluated_metric_count") or 0) > 0
        or float(row.get("metric_coverage") or 0.0) > 0.0
    }
    covered_ids.discard("")

    metrics_total = sum(int(row.get("requested_metric_count") or 0) for row in rows)
    metrics_evaluated = sum(int(row.get("evaluated_metric_count") or 0) for row in rows)

    analyses_total = sum(int(row.get("requested_analysis_count") or 0) for row in rows)
    analyses_executed = sum(int(row.get("executed_analysis_count") or 0) for row in rows)
    if analyses_total == 0:
        requested = [row for row in rows if row.get("analysis_type")]
        analyses_total = len(requested)
        analyses_executed = sum(
            1
            for row in requested
            if str(row.get("execution_status") or "").upper() == "SUCCESS"
        )

    return CoverageSummary(
        cov_circuits=(len(covered_ids) / len(circuit_ids)) if circuit_ids else 0.0,
        cov_metrics=(metrics_evaluated / metrics_total) if metrics_total else 0.0,
        cov_analyses=(analyses_executed / analyses_total) if analyses_total else 0.0,
        circuits_total=len(circuit_ids),
        circuits_covered=len(covered_ids),
        metrics_total=metrics_total,
        metrics_evaluated=metrics_evaluated,
        analyses_total=analyses_total,
        analyses_executed=analyses_executed,
    )


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> dict[str, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    p_hat = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denominator
    margin = (z * sqrt((p_hat * (1.0 - p_hat) / total) + z2 / (4.0 * total * total))) / denominator
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


@dataclass(frozen=True)
class ConfusionMatrix:
    tp: int
    tn: int
    fp: int
    fn: int
    excluded: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def false_accept_rate(self) -> float:
        denominator = self.tp + self.fn
        return self.fn / denominator if denominator else 0.0

    @property
    def false_reject_rate(self) -> float:
        denominator = self.tn + self.fp
        return self.fp / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, Any]:
        positive_total = self.tp + self.fn
        negative_total = self.tn + self.fp
        return {
            "TP": self.tp,
            "TN": self.tn,
            "FP": self.fp,
            "FN": self.fn,
            "eligible_total": self.total,
            "excluded": self.excluded,
            "accuracy": self.accuracy,
            "accuracy_ci95": wilson_interval(self.tp + self.tn, self.total),
            "false_accept_rate": self.false_accept_rate,
            "false_accept_rate_ci95": wilson_interval(self.fn, positive_total),
            "false_reject_rate": self.false_reject_rate,
            "false_reject_rate_ci95": wilson_interval(self.fp, negative_total),
        }


def confusion_from_rows(
    rows: Iterable[dict[str, Any]],
    *,
    truth_key: str = "ground_truth_label",
    verdict_key: str = "compliance_status",
) -> ConfusionMatrix:
    tp = tn = fp = fn = excluded = 0
    for row in rows:
        truth = str(row.get(truth_key) or "").upper()
        verdict = str(row.get(verdict_key) or "").upper()
        if verdict not in {"PASS", "FAIL"}:
            excluded += 1
            continue

        if "UNCERTAIN" in truth or "NON_SIMULABLE" in truth or not truth:
            excluded += 1
            continue
        if "NONCOMPLIANT" in truth or truth in {"FAIL", "VIOLATION", "POSITIVE"}:
            truth_noncompliant = True
        elif "COMPLIANT" in truth or truth in {"PASS", "NEGATIVE"}:
            truth_noncompliant = False
        else:
            excluded += 1
            continue

        if truth_noncompliant and verdict == "FAIL":
            tp += 1
        elif not truth_noncompliant and verdict == "PASS":
            tn += 1
        elif not truth_noncompliant and verdict == "FAIL":
            fp += 1
        elif truth_noncompliant and verdict == "PASS":
            fn += 1
    return ConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn, excluded=excluded)



def majority_vote_rows(
    rows: Iterable[dict[str, Any]],
    *,
    case_key: str = "case_id",
    truth_key: str = "ground_truth_label",
    verdict_key: str = "compliance_status",
) -> list[dict[str, Any]]:
    """Aggregate repeated runs into one case-level verdict.

    PASS/FAIL votes only are counted. Ties or cases with no executable verdict are
    retained as NOT_EVALUATED so they are explicitly excluded by confusion logic.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        case_id = str(row.get(case_key) or "")
        if case_id:
            grouped.setdefault(case_id, []).append(dict(row))
    out: list[dict[str, Any]] = []
    for case_id, items in sorted(grouped.items()):
        passes = sum(str(item.get(verdict_key) or "").upper() == "PASS" for item in items)
        fails = sum(str(item.get(verdict_key) or "").upper() == "FAIL" for item in items)
        if passes > fails:
            verdict = "PASS"
        elif fails > passes:
            verdict = "FAIL"
        else:
            verdict = "NOT_EVALUATED"
        out.append({
            case_key: case_id,
            truth_key: next((item.get(truth_key) for item in items if item.get(truth_key)), ""),
            verdict_key: verdict,
            "pass_votes": passes,
            "fail_votes": fails,
            "trial_count": len(items),
            "eligible_vote_count": passes + fails,
        })
    return out


def _truth_is_noncompliant(value: Any) -> bool | None:
    truth = str(value or "").upper()
    if not truth or "UNCERTAIN" in truth or "NON_SIMULABLE" in truth:
        return None
    if "NONCOMPLIANT" in truth or truth in {"FAIL", "VIOLATION", "POSITIVE"}:
        return True
    if "COMPLIANT" in truth or truth in {"PASS", "NEGATIVE"}:
        return False
    return None


def _is_correct(row: dict[str, Any], *, truth_key: str, verdict_key: str) -> bool | None:
    truth_noncompliant = _truth_is_noncompliant(row.get(truth_key))
    verdict = str(row.get(verdict_key) or "").upper()
    if truth_noncompliant is None or verdict not in {"PASS", "FAIL"}:
        return None
    return (truth_noncompliant and verdict == "FAIL") or ((not truth_noncompliant) and verdict == "PASS")


def mcnemar_exact(
    left_rows: Iterable[dict[str, Any]],
    right_rows: Iterable[dict[str, Any]],
    *,
    case_key: str = "case_id",
    truth_key: str = "ground_truth_label",
    verdict_key: str = "compliance_status",
) -> dict[str, Any]:
    """Exact two-sided McNemar test on paired case-level correctness."""
    left = {str(row.get(case_key) or ""): row for row in left_rows if row.get(case_key)}
    right = {str(row.get(case_key) or ""): row for row in right_rows if row.get(case_key)}
    b = c = paired = excluded = 0
    for case_id in sorted(set(left) & set(right)):
        left_correct = _is_correct(left[case_id], truth_key=truth_key, verdict_key=verdict_key)
        right_correct = _is_correct(right[case_id], truth_key=truth_key, verdict_key=verdict_key)
        if left_correct is None or right_correct is None:
            excluded += 1
            continue
        paired += 1
        if left_correct and not right_correct:
            b += 1
        elif not left_correct and right_correct:
            c += 1
    discordant = b + c
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(comb(discordant, k) for k in range(0, min(b, c) + 1)) / (2 ** discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        "paired_cases": paired,
        "excluded_pairs": excluded,
        "left_correct_right_wrong": b,
        "left_wrong_right_correct": c,
        "discordant_pairs": discordant,
        "exact_two_sided_p_value": p_value,
    }

def llm_quality_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    total = len(rows)
    if not total:
        return {
            "runs": 0,
            "json_valid_rate": 0.0,
            "plan_rejection_rate": 0.0,
            "final_plan_rejection_rate": 0.0,
            "executable_plan_rate": 0.0,
            "unknown_node_rate": 0.0,
            "role_mismatch_rate": 0.0,
            "analysis_mismatch_rate": 0.0,
            "invalid_stimulus_rate": 0.0,
            "invalid_measurement_rate": 0.0,
            "feedback_recovery_rate": 0.0,
            "mean_llm_calls": 0.0,
            "mean_tokens": 0.0,
            "mean_latency_seconds": 0.0,
            "total_tokens": 0,
            "total_latency_seconds": 0.0,
            "provider_transport_retry_count": 0,
        }

    def truthy(row: dict[str, Any], key: str) -> bool:
        value = row.get(key)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "valid", "success"}
        return bool(value)

    repaired = [row for row in rows if int(row.get("repair_count") or 0) > 0]
    recovered = [
        row
        for row in repaired
        if truthy(row, "final_plan_valid")
        and str(row.get("execution_status") or "").upper() == "SUCCESS"
    ]

    issue_texts = [
        str(
            row.get("initial_issues")
            or row.get("issues")
            or row.get("validation_issues")
            or ""
        ).upper()
        for row in rows
    ]

    def rate_with_any(*markers: str) -> float:
        # Report a fraction of runs, not a count of issue occurrences.  A single
        # rejected plan can legitimately contain several errors of one class.
        return sum(any(marker in text for marker in markers) for text in issue_texts) / total

    return {
        "runs": total,
        "json_valid_rate": sum(
            truthy(row, "initial_json_valid")
            if "initial_json_valid" in row
            else (truthy(row, "json_valid") or truthy(row, "final_json_valid"))
            for row in rows
        ) / total,
        "plan_rejection_rate": sum(
            not (truthy(row, "initial_plan_valid") if "initial_plan_valid" in row else truthy(row, "final_plan_valid"))
            for row in rows
        ) / total,
        "final_plan_rejection_rate": sum(not truthy(row, "final_plan_valid") for row in rows) / total,
        "executable_plan_rate": sum(str(row.get("execution_status") or "").upper() == "SUCCESS" for row in rows) / total,
        "unknown_node_rate": rate_with_any("UNKNOWN_NODE"),
        "role_mismatch_rate": rate_with_any("ROLE_MISMATCH"),
        "analysis_mismatch_rate": rate_with_any("ANALYSIS_MISMATCH"),
        "invalid_stimulus_rate": rate_with_any("INVALID_STIMULUS"),
        "invalid_measurement_rate": rate_with_any(
            "UNSUPPORTED_BACKEND",
            "UNIT_MISMATCH",
            "MISSING_REQUIRED_METRIC",
            "MEASUREMENT",
        ),
        "feedback_recovery_rate": (len(recovered) / len(repaired)) if repaired else 0.0,
        "mean_llm_calls": sum(int(row.get("llm_call_count") or 0) for row in rows) / total,
        "mean_tokens": sum(int(row.get("total_tokens") or 0) for row in rows) / total,
        "mean_latency_seconds": sum(float(row.get("total_llm_latency_seconds") or row.get("generation_latency_s") or 0.0) for row in rows) / total,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
        "total_latency_seconds": sum(float(row.get("total_llm_latency_seconds") or row.get("generation_latency_s") or 0.0) for row in rows),
        "provider_transport_retry_count": sum(int(row.get("provider_transport_retry_count") or 0) for row in rows),
    }
