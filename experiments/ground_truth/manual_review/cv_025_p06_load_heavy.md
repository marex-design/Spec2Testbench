# Manual Review: cv_025_p06_load_heavy

- Original circuit: `p06_inverter`
- Circuit family: `amplifier`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `operating_point`
- Manual review status: `manually_verified`

## Physical Justification

heavy load forces output DC point away from nominal

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "heavy load forces output DC point away from nominal",
  "expected_value": null,
  "unit": "V"
}

## Mutation

{
  "case_id": "cv_025_p06_load_heavy",
  "parent_circuit_id": "p06_inverter",
  "mutation_type": "dc_voltage_current",
  "target_component": "Rload",
  "original_value": "100k",
  "mutated_value": "1",
  "target_metric": "operating_point",
  "expected_effect": "pull output high/low incorrectly",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "heavy load forces output DC point away from nominal"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
