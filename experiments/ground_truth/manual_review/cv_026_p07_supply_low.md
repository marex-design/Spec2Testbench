# Manual Review: cv_026_p07_supply_low

- Original circuit: `p07_inverter`
- Circuit family: `amplifier`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `operating_point`
- Manual review status: `manually_verified`

## Physical Justification

low supply prevents nominal output swing

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "low supply prevents nominal output swing",
  "expected_value": null,
  "unit": "V"
}

## Mutation

{
  "case_id": "cv_026_p07_supply_low",
  "parent_circuit_id": "p07_inverter",
  "mutation_type": "dc_voltage_current",
  "target_component": "Vdd",
  "original_value": "5",
  "mutated_value": "0.1",
  "target_metric": "operating_point",
  "expected_effect": "collapse output swing",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "low supply prevents nominal output swing"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
