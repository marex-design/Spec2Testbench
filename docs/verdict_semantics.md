# Verdict Semantics

Spec2Testbench now separates simulation execution, simulation origin, nominal
compliance, robustness, and scientific classification.

## ExecutionStatus

- `SUCCESS`: the simulator produced usable results.
- `ERROR`: the simulator failed.
- `TIMEOUT`: the simulator exceeded the configured timeout.
- `SKIPPED`: simulation was not attempted.

## SimulationMode

- `REAL`: results came from ngspice/PySpice execution.
- `MOCK`: synthetic development result, never scientifically eligible.
- `RECOVERED`: a real result obtained after an explicit recovery action.

## ComplianceStatus

- `PASS`: all mandatory nominal specifications passed.
- `FAIL`: at least one mandatory nominal specification failed.
- `NOT_EVALUATED`: required metrics were unavailable.

## RobustnessStatus

- `ROBUST_PASS`: nominal and requested robustness checks passed.
- `ROBUST_FAIL`: at least one robustness check failed.
- `NOT_EVALUATED`: complete robustness testing was not performed.

## ScientificCategory

- `SIMULABLE_COMPLIANT`: `ExecutionStatus.SUCCESS` and `ComplianceStatus.PASS`.
- `SIMULABLE_NONCOMPLIANT`: `ExecutionStatus.SUCCESS` and `ComplianceStatus.FAIL`.
- `NON_SIMULABLE`: `ExecutionStatus.ERROR` or `ExecutionStatus.TIMEOUT`.
- `UNEVALUATED`: simulation skipped or compliance not evaluated.

The legacy `overall_verdict` remains available for compatibility, but paper
tables must use the separated statuses.
