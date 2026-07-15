# Manual Review: cv_021_p09_ref_high

- Original circuit: `p09_comparator`
- Circuit family: `comparator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `propagation_delay`
- Manual review status: `manually_verified`

## Physical Justification

reference outside input range prevents valid transition

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "reference outside input range prevents valid transition",
  "expected_value": null,
  "unit": "s"
}

## Mutation

{
  "case_id": "cv_021_p09_ref_high",
  "parent_circuit_id": "p09_comparator",
  "mutation_type": "switching_threshold",
  "target_component": "Vref",
  "original_value": "2.5",
  "mutated_value": "100",
  "target_metric": "propagation_delay",
  "expected_effect": "prevent switching",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "reference outside input range prevents valid transition"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
