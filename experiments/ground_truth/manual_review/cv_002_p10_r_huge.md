# Manual Review: cv_002_p10_r_huge

- Original circuit: `p10_lowpass`
- Circuit family: `low_pass_filter`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `cutoff_frequency_hz`
- Manual review status: `manually_verified`

## Physical Justification

fc = 1/(2*pi*1G*10n) = 0.0159 Hz

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "fc = 1/(2*pi*1G*10n) = 0.0159 Hz",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_002_p10_r_huge",
  "parent_circuit_id": "p10_lowpass",
  "mutation_type": "frequency_bandwidth",
  "target_component": "R1",
  "original_value": "10k",
  "mutated_value": "1G",
  "target_metric": "cutoff_frequency_hz",
  "expected_effect": "decrease below lower bound",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "fc = 1/(2*pi*1G*10n) = 0.0159 Hz"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
