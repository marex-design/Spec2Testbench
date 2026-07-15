# Ground Truth Protocol

Labels are assigned before Spec2Testbench execution from analytical equations, direct ngspice checks, or documented physical reasoning. Framework verdicts are recorded only after labels are fixed and are never used as label sources.

Allowed labels: `GROUND_TRUTH_COMPLIANT`, `GROUND_TRUTH_NONCOMPLIANT`, `GROUND_TRUTH_NON_SIMULABLE`, `GROUND_TRUTH_UNCERTAIN`. Uncertain cases are excluded from principal metrics.

Original benchmark netlists under `benchmark/analogcoder_pro/` are read-only references; variants are copied under `experiments/controlled_violations/generated_cases/`.
