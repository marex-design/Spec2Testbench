# Manual Review: cv_012_p16_vdd_low

- Original circuit: `p16_opamp`
- Circuit family: `opamp`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `operating_point`
- Manual review status: `manually_verified`

## Physical Justification

insufficient supply headroom prevents nominal bias point

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "insufficient supply headroom prevents nominal bias point",
  "expected_value": null,
  "unit": "V"
}

## Mutation

{
  "case_id": "cv_012_p16_vdd_low",
  "parent_circuit_id": "p16_opamp",
  "mutation_type": "dc_voltage_current",
  "target_component": "Vdd",
  "original_value": "5",
  "mutated_value": "0.2",
  "target_metric": "operating_point",
  "expected_effect": "collapse output swing",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "insufficient supply headroom prevents nominal bias point"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
