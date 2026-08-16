"""ACP benchmark aggregation and strict conformity accounting."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional


PASS_VALUES = {"PASS", "COMPLIANT", "ROBUST_PASS"}
FAIL_VALUES = {"FAIL", "NONCOMPLIANT"}
SUCCESS_VALUES = {"SUCCESS"}


@dataclass(frozen=True)
class ACPConformitySummary:
    circuits_total: int
    simulation_success: int
    evaluated: int
    compliant: int
    noncompliant: int
    not_evaluated: int
    contract_complete: int
    contract_incomplete: int
    simulation_success_rate: float
    evaluation_rate: float
    compliance_rate_evaluated: float
    noncompliance_rate_evaluated: float
    verified_compliance_yield: float
    failure_to_evaluate_rate: float
    contract_completion_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _ratio(num: int, den: int) -> float:
    return float(num) / float(den) if den else 0.0


def normalize_contract_status(record: Dict[str, Any], *, strict_contract: bool = True) -> str:
    """Return PASS/FAIL/NOT_EVALUATED without converting missing evidence to PASS.

    In strict mode, a circuit can only be called compliant when every mandatory
    ACP contract requirement has an executable/evaluated mapping.
    """
    explicit = str(record.get("contract_status", "")).upper()
    if explicit in {"PASS", "FAIL", "NOT_EVALUATED"}:
        return explicit

    coverage = float(record.get("contract_coverage", 0.0) or 0.0)
    execution_status = str(record.get("execution_status", "")).upper()
    raw_status = str(record.get("compliance_status", "")).upper()
    missing_required = int(record.get("missing_mandatory_requirements", 0) or 0)
    failed_required = int(record.get("failed_mandatory_requirements", 0) or 0)

    if execution_status not in SUCCESS_VALUES:
        return "NOT_EVALUATED"
    # A demonstrated violation is sufficient to establish non-compliance even
    # when another mandatory criterion could not be measured. PASS is stricter:
    # every mandatory criterion must be evaluated and pass.
    if failed_required > 0:
        return "FAIL"
    if strict_contract and (coverage < 1.0 - 1e-12 or missing_required > 0):
        return "NOT_EVALUATED"
    if raw_status in PASS_VALUES:
        return "PASS"
    if raw_status in FAIL_VALUES:
        return "FAIL"
    return "NOT_EVALUATED"


def summarize_acp_records(records: Iterable[Dict[str, Any]], *, strict_contract: bool = True) -> ACPConformitySummary:
    rows: List[Dict[str, Any]] = [dict(row) for row in records]
    total = len(rows)
    simulation_success = sum(str(r.get("execution_status", "")).upper() in SUCCESS_VALUES for r in rows)
    contract_complete = sum(float(r.get("contract_coverage", 0.0) or 0.0) >= 1.0 - 1e-12 for r in rows)
    statuses = [normalize_contract_status(r, strict_contract=strict_contract) for r in rows]
    compliant = statuses.count("PASS")
    noncompliant = statuses.count("FAIL")
    evaluated = compliant + noncompliant
    not_evaluated = total - evaluated
    return ACPConformitySummary(
        circuits_total=total,
        simulation_success=simulation_success,
        evaluated=evaluated,
        compliant=compliant,
        noncompliant=noncompliant,
        not_evaluated=not_evaluated,
        contract_complete=contract_complete,
        contract_incomplete=total - contract_complete,
        simulation_success_rate=_ratio(simulation_success, total),
        evaluation_rate=_ratio(evaluated, total),
        compliance_rate_evaluated=_ratio(compliant, evaluated),
        noncompliance_rate_evaluated=_ratio(noncompliant, evaluated),
        verified_compliance_yield=_ratio(compliant, total),
        failure_to_evaluate_rate=_ratio(not_evaluated, total),
        contract_completion_rate=_ratio(contract_complete, total),
    )
