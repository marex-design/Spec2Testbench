# Manual Review: cv_022_p28_vin_low

- Original circuit: `p28_schmitt`
- Circuit family: `schmitt_trigger`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `propagation_delay`
- Manual review status: `manually_verified`

## Physical Justification

input amplitude never reaches switching threshold

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "input amplitude never reaches switching threshold",
  "expected_value": null,
  "unit": "s"
}

## Mutation

{
  "case_id": "cv_022_p28_vin_low",
  "parent_circuit_id": "p28_schmitt",
  "mutation_type": "switching_threshold",
  "target_component": "Vin",
  "original_value": "2.7",
  "mutated_value": "0.1",
  "target_metric": "propagation_delay",
  "expected_effect": "prevent switching",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "input amplitude never reaches switching threshold"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
