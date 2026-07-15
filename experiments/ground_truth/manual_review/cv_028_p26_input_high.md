# Manual Review: cv_028_p26_input_high

- Original circuit: `p26_adder`
- Circuit family: `composite`
- Ground-truth label: `GROUND_TRUTH_NONCOMPLIANT`
- Target metric: `operating_point`
- Manual review status: `manually_verified`

## Physical Justification

oversized input drives summing circuit outside nominal range

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "oversized input drives summing circuit outside nominal range",
  "expected_value": null,
  "unit": "V"
}

## Mutation

{
  "case_id": "cv_028_p26_input_high",
  "parent_circuit_id": "p26_adder",
  "mutation_type": "dc_voltage_current",
  "target_component": "Vin1",
  "original_value": "3",
  "mutated_value": "100",
  "target_metric": "operating_point",
  "expected_effect": "saturate output",
  "ground_truth_label": "GROUND_TRUTH_NONCOMPLIANT",
  "justification": "oversized input drives summing circuit outside nominal range"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
