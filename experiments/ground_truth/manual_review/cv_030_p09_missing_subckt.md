# Manual Review: cv_030_p09_missing_subckt

- Original circuit: `p09_comparator`
- Circuit family: `comparator`
- Ground-truth label: `GROUND_TRUTH_NON_SIMULABLE`
- Target metric: `propagation_delay`
- Manual review status: `manually_verified`

## Physical Justification

undefined subcircuit is intentionally non-simulable

## Independent Reference

{
  "method": "physical_mutation_reasoning",
  "equation": "undefined subcircuit is intentionally non-simulable",
  "expected_value": null,
  "unit": "s"
}

## Mutation

{
  "case_id": "cv_030_p09_missing_subckt",
  "parent_circuit_id": "p09_comparator",
  "mutation_type": "non_simulable",
  "target_component": "Xcmp",
  "original_value": "Opamp",
  "mutated_value": "MissingOpamp",
  "target_metric": "propagation_delay",
  "expected_effect": "ngspice subckt error",
  "ground_truth_label": "GROUND_TRUTH_NON_SIMULABLE",
  "justification": "undefined subcircuit is intentionally non-simulable"
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
