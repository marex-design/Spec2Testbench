# Manual Review: cv_004_p12_r_shift

- Original circuit: `p12_bandpass`
- Circuit family: `band_pass_filter`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `center_frequency`
- Manual review status: `manually_verified`

## Physical Justification

large R shifts the RC pole/zero network by four decades

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "large R shifts the RC pole/zero network by four decades",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_004_p12_r_shift",
  "parent_circuit_id": "p12_bandpass",
  "mutation_type": "frequency_bandwidth",
  "target_component": "R1",
  "original_value": "10k",
  "mutated_value": "100Meg",
  "target_metric": "center_frequency",
  "expected_effect": "move outside range",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "large R shifts the RC pole/zero network by four decades"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
