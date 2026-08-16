"""Separated statuses used for scientific experiment reporting."""

from enum import Enum


class ExecutionStatus(Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class SimulationMode(Enum):
    REAL = "REAL"
    MOCK = "MOCK"
    RECOVERED = "RECOVERED"


class ComplianceStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class NetlistBindingStatus(Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_VERIFIED = "NOT_VERIFIED"


class MutationEffectivenessStatus(Enum):
    EFFECTIVE_THRESHOLD_CROSSED = "EFFECTIVE_THRESHOLD_CROSSED"
    EFFECTIVE_NO_THRESHOLD_CROSSING = "EFFECTIVE_NO_THRESHOLD_CROSSING"
    NO_MEASURABLE_EFFECT = "NO_MEASURABLE_EFFECT"
    NOT_APPLIED = "NOT_APPLIED"
    NOT_EVALUATED = "NOT_EVALUATED"


class RobustnessStatus(Enum):
    ROBUST_PASS = "ROBUST_PASS"
    ROBUST_FAIL = "ROBUST_FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class ScientificCategory(Enum):
    SIMULABLE_COMPLIANT = "SIMULABLE_COMPLIANT"
    SIMULABLE_NONCOMPLIANT = "SIMULABLE_NONCOMPLIANT"
    NON_SIMULABLE = "NON_SIMULABLE"
    UNEVALUATED = "UNEVALUATED"


def classify_scientific_result(
    execution_status: ExecutionStatus,
    compliance_status: ComplianceStatus,
) -> ScientificCategory:
    if (
        execution_status == ExecutionStatus.SUCCESS
        and compliance_status == ComplianceStatus.PASS
    ):
        return ScientificCategory.SIMULABLE_COMPLIANT
    if (
        execution_status == ExecutionStatus.SUCCESS
        and compliance_status == ComplianceStatus.FAIL
    ):
        return ScientificCategory.SIMULABLE_NONCOMPLIANT
    if execution_status in (ExecutionStatus.ERROR, ExecutionStatus.TIMEOUT):
        return ScientificCategory.NON_SIMULABLE
    return ScientificCategory.UNEVALUATED
