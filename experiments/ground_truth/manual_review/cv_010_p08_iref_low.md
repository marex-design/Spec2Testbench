# Manual Review: cv_010_p08_iref_low

- Original circuit: `p08_currentmirror`
- Circuit family: `current_mirror`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `quiescent_current`
- Manual review status: `manually_verified`

## Physical Justification

load resistance controls output current drawn from the mirror

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "load resistance controls output current drawn from the mirror",
  "expected_value": null,
  "unit": "A"
}

## Mutation

{
  "case_id": "cv_010_p08_iref_low",
  "parent_circuit_id": "p08_currentmirror",
  "mutation_type": "dc_voltage_current",
  "target_component": "Rload",
  "original_value": "10000",
  "mutated_value": "1",
  "target_metric": "quiescent_current",
  "expected_effect": "increase load current",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "load resistance controls output current drawn from the mirror"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
