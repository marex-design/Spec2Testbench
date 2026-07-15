# Manual Review: cv_006_p01_rd_low

- Original circuit: `p01_amplifier`
- Circuit family: `amplifier`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `dc_gain_db`
- Manual review status: `manually_verified`

## Physical Justification

drain load collapse suppresses voltage gain

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "drain load collapse suppresses voltage gain",
  "expected_value": null,
  "unit": "dB"
}

## Mutation

{
  "case_id": "cv_006_p01_rd_low",
  "parent_circuit_id": "p01_amplifier",
  "mutation_type": "gain",
  "target_component": "Rload",
  "original_value": "10k",
  "mutated_value": "1",
  "target_metric": "dc_gain_db",
  "expected_effect": "reduce gain",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "drain load collapse suppresses voltage gain"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
