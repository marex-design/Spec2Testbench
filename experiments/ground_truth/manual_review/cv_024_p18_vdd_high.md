# Manual Review: cv_024_p18_vdd_high

- Original circuit: `p18_opamp`
- Circuit family: `opamp`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `power`
- Manual review status: `manually_verified`

## Physical Justification

DC power scales with supply for biased opamp

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "DC power scales with supply for biased opamp",
  "expected_value": null,
  "unit": "W"
}

## Mutation

{
  "case_id": "cv_024_p18_vdd_high",
  "parent_circuit_id": "p18_opamp",
  "mutation_type": "power_consumption",
  "target_component": "Vdd",
  "original_value": "5",
  "mutated_value": "50",
  "target_metric": "power",
  "expected_effect": "increase power",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "DC power scales with supply for biased opamp"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
