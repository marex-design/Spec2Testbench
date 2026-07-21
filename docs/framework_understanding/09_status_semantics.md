# Phase 9 - Status Semantics

## Status definitions

- `ExecutionStatus`: `SUCCESS`, `ERROR`, `TIMEOUT`, `SKIPPED`
- `SimulationMode`: `REAL`, `MOCK`, `RECOVERED`
- `ComplianceStatus`: `PASS`, `FAIL`, `NOT_EVALUATED`
- `RobustnessStatus`: `ROBUST_PASS`, `ROBUST_FAIL`, `NOT_EVALUATED`
- `ScientificCategory`: `SIMULABLE_COMPLIANT`, `SIMULABLE_NONCOMPLIANT`, `NON_SIMULABLE`, `UNEVALUATED`
- run-level verdict: `ValidationStatus.FAIL`, `RUN`, `PASS`, `ROBUST PASS`

## Calculation rules observed

### Compliance

- If execution is not `SUCCESS`, compliance is `NOT_EVALUATED`
- If netlist binding is not `MATCH`, compliance is `NOT_EVALUATED`
- If no nominal results exist, compliance is `NOT_EVALUATED`
- If any nominal result is `FAIL`, compliance is `FAIL`
- If any nominal result is `ERROR`, compliance is `NOT_EVALUATED`
- Else compliance is `PASS`

### Robustness

- If no PVT results exist: `NOT_EVALUATED`
- If any PVT result is `ERROR` or `FAIL`: `ROBUST_FAIL`
- Else: `ROBUST_PASS`

### Scientific category

- `SUCCESS + PASS` -> `SIMULABLE_COMPLIANT`
- `SUCCESS + FAIL` -> `SIMULABLE_NONCOMPLIANT`
- `ERROR/TIMEOUT` -> `NON_SIMULABLE`
- otherwise -> `UNEVALUATED`

### Paper eligibility

Observed required conditions:

- `execution_status == SUCCESS`
- `simulation_mode in {REAL, RECOVERED}`
- `netlist_binding_status == MATCH`
- no unsupported/overwritten/not-applied variant override records that would disqualify provenance

## Decision table

| Execution | Mode | Metric result | Compliance | Eligibility | Final category |
| --- | --- | --- | --- | --- | --- |
| `SUCCESS` | `REAL` | all nominal pass | `PASS` | yes if binding matches | `SIMULABLE_COMPLIANT` |
| `SUCCESS` | `REAL` | any nominal fail | `FAIL` | can still be yes | `SIMULABLE_NONCOMPLIANT` |
| `SUCCESS` | `REAL` | any required nominal error | `NOT_EVALUATED` | yes only if other provenance rules hold | `UNEVALUATED` |
| `SUCCESS` | `MOCK` | pass/fail values exist | computed | no | usually not paper-eligible |
| `ERROR` | `REAL` | absent/unusable | `NOT_EVALUATED` | no | `NON_SIMULABLE` |
| `TIMEOUT` | `REAL` | absent/unusable | `NOT_EVALUATED` | no | `NON_SIMULABLE` |
| `SKIPPED` | none | none | `NOT_EVALUATED` | no | `UNEVALUATED` |

## Centralization assessment

Partially centralized:

- primary run/scientific status logic is in `VerificationReport` and `VerificationPipeline._finalize_report_statuses()`
- metric verdict logic is in `SpecChecker`
- there is duplication between `VerificationReport.__post_init__()` and `_finalize_report_statuses()`

## Architectural reading

Fact observed:
- the repository carefully separates “execution succeeded” from “specification passed”.

Interpretation:
- this separation is essential for scientific reporting and is implemented more rigorously than many research prototypes.
