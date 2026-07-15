# Manual Review: cv_019_p22_vdd_low

- Original circuit: `p22_oscillator`
- Circuit family: `oscillator`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `startup_amplitude`
- Manual review status: `manually_verified`

## Physical Justification

supply starvation prevents oscillation amplitude buildup

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "supply starvation prevents oscillation amplitude buildup",
  "expected_value": null,
  "unit": "V"
}

## Mutation

{
  "case_id": "cv_019_p22_vdd_low",
  "parent_circuit_id": "p22_oscillator",
  "mutation_type": "amplitude_oscillation",
  "target_component": "Vdd",
  "original_value": "5",
  "mutated_value": "0.1",
  "target_metric": "startup_amplitude",
  "expected_effect": "reduce amplitude",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "supply starvation prevents oscillation amplitude buildup"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
