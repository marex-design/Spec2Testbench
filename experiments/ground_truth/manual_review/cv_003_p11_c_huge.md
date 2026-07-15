# Manual Review: cv_003_p11_c_huge

- Original circuit: `p11_highpass`
- Circuit family: `high_pass_filter`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `cutoff_frequency_hz`
- Manual review status: `manually_verified`

## Physical Justification

large C moves corner far below specification range

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "large C moves corner far below specification range",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_003_p11_c_huge",
  "parent_circuit_id": "p11_highpass",
  "mutation_type": "frequency_bandwidth",
  "target_component": "C1",
  "original_value": "10n",
  "mutated_value": "1",
  "target_metric": "cutoff_frequency_hz",
  "expected_effect": "decrease below lower bound",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "large C moves corner far below specification range"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
