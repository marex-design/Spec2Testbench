# Manual Review: cv_005_p13_c_shift

- Original circuit: `p13_bandstop`
- Circuit family: `notch_filter`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `center_frequency`
- Manual review status: `manually_verified`

## Physical Justification

large C shifts notch frequency far below expected band

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "large C shifts notch frequency far below expected band",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_005_p13_c_shift",
  "parent_circuit_id": "p13_bandstop",
  "mutation_type": "frequency_bandwidth",
  "target_component": "C1",
  "original_value": "10n",
  "mutated_value": "1",
  "target_metric": "center_frequency",
  "expected_effect": "move outside range",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "large C shifts notch frequency far below expected band"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
