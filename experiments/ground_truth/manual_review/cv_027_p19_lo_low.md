# Manual Review: cv_027_p19_lo_low

- Original circuit: `p19_mixer`
- Circuit family: `mixer`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `thd`
- Manual review status: `manually_verified`

## Physical Justification

LO amplitude reduction suppresses mixer spectral output

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "LO amplitude reduction suppresses mixer spectral output",
  "expected_value": null,
  "unit": ""
}

## Mutation

{
  "case_id": "cv_027_p19_lo_low",
  "parent_circuit_id": "p19_mixer",
  "mutation_type": "amplitude_oscillation",
  "target_component": "Vlop",
  "original_value": "3",
  "mutated_value": "0.001",
  "target_metric": "thd",
  "expected_effect": "reduce mixing product",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "LO amplitude reduction suppresses mixer spectral output"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
