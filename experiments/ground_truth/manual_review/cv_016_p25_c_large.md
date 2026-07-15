# Manual Review: cv_016_p25_c_large

- Original circuit: `p25_differentiator`
- Circuit family: `opamp_differentiator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `slew_rate`
- Manual review status: `manually_verified`

## Physical Justification

large capacitor attenuates fast transient response

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "large capacitor attenuates fast transient response",
  "expected_value": null,
  "unit": "V/s"
}

## Mutation

{
  "case_id": "cv_016_p25_c_large",
  "parent_circuit_id": "p25_differentiator",
  "mutation_type": "timing",
  "target_component": "C1",
  "original_value": "10n",
  "mutated_value": "1",
  "target_metric": "slew_rate",
  "expected_effect": "reduce dynamic slope",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "large capacitor attenuates fast transient response"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
