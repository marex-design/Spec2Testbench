# Manual Review: cv_014_p09_input_slow

- Original circuit: `p09_comparator`
- Circuit family: `comparator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `propagation_delay`
- Manual review status: `manually_verified`

## Physical Justification

coarse/long transient stimulus makes threshold crossing much later

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "coarse/long transient stimulus makes threshold crossing much later",
  "expected_value": null,
  "unit": "s"
}

## Mutation

{
  "case_id": "cv_014_p09_input_slow",
  "parent_circuit_id": "p09_comparator",
  "mutation_type": "timing",
  "target_component": "TRAN",
  "original_value": "1U 10M",
  "mutated_value": "100U 2",
  "target_metric": "propagation_delay",
  "expected_effect": "increase delay",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "coarse/long transient stimulus makes threshold crossing much later"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
