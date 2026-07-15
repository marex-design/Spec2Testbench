# Manual Review: cv_018_p23_c_large

- Original circuit: `p23_oscillator`
- Circuit family: `oscillator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `oscillator_frequency`
- Manual review status: `manually_verified`

## Physical Justification

RC oscillator frequency scales inversely with C

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "RC oscillator frequency scales inversely with C",
  "expected_value": null,
  "unit": "Hz"
}

## Mutation

{
  "case_id": "cv_018_p23_c_large",
  "parent_circuit_id": "p23_oscillator",
  "mutation_type": "amplitude_oscillation",
  "target_component": "C1",
  "original_value": "10n",
  "mutated_value": "1",
  "target_metric": "oscillator_frequency",
  "expected_effect": "decrease frequency",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "RC oscillator frequency scales inversely with C"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
