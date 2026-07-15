# Manual Review: cv_015_p24_c_large

- Original circuit: `p24_integrator`
- Circuit family: `opamp_integrator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `settling_time`
- Manual review status: `manually_verified`

## Physical Justification

larger integration capacitor increases settling time

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "larger integration capacitor increases settling time",
  "expected_value": null,
  "unit": "s"
}

## Mutation

{
  "case_id": "cv_015_p24_c_large",
  "parent_circuit_id": "p24_integrator",
  "mutation_type": "timing",
  "target_component": "Cf",
  "original_value": "100n",
  "mutated_value": "1",
  "target_metric": "settling_time",
  "expected_effect": "increase time constant",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "larger integration capacitor increases settling time"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
