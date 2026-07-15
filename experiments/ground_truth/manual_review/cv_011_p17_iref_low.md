# Manual Review: cv_011_p17_iref_low

- Original circuit: `p17_currentmirror`
- Circuit family: `current_mirror`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `quiescent_current`
- Manual review status: `manually_verified`

## Physical Justification

reference current controls mirrored current directly

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "reference current controls mirrored current directly",
  "expected_value": null,
  "unit": "A"
}

## Mutation

{
  "case_id": "cv_011_p17_iref_low",
  "parent_circuit_id": "p17_currentmirror",
  "mutation_type": "dc_voltage_current",
  "target_component": "Iref",
  "original_value": "100u",
  "mutated_value": "1n",
  "target_metric": "quiescent_current",
  "expected_effect": "decrease current",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "reference current controls mirrored current directly"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
