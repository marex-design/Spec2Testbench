from enum import Enum

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    NOT_RUN = "NOT_RUN"

class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    COMPLIANT = "COMPLIANT"
    NONCOMPLIANT = "NONCOMPLIANT"
    NOT_EVALUATED = "NOT_EVALUATED"

class CriterionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

class SimulationMode(str, Enum):
    REAL = "REAL"
    MOCK = "MOCK"
    NONE = "NONE"
