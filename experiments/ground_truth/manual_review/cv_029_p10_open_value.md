# Manual Review: cv_029_p10_open_value

- Original circuit: `p10_lowpass`
- Circuit family: `low_pass_filter`
- Ground-truth label: `GROUND_TRUTH_NON_SIMULABLE`
- Target metric: `cutoff_frequency_hz`
- Manual review status: `manually_verified`

## Physical Justification

invalid numeric value is intentionally non-simulable

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "invalid numeric value is intentionally non-simulable",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_029_p10_open_value",
  "parent_circuit_id": "p10_lowpass",
  "mutation_type": "non_simulable",
  "target_component": "C1",
  "original_value": "10n",
  "mutated_value": "BAD_VALUE",
  "target_metric": "cutoff_frequency_hz",
  "expected_effect": "ngspice parse error",
  "ground_truth_label": "GROUND_TRUTH_NON_SIMULABLE",
  "justification": "invalid numeric value is intentionally non-simulable"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
