# Manual Review: p09_comparator_nominal_gt

- Original circuit: `p09_comparator`
- Circuit family: `comparator`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `propagation_delay`
- Manual review status: `manually_verified`

## Physical Justification

p09_comparator is a nominal benchmark circuit. The label is assigned from manual_transient_estimate evidence (Input and output transition timing inspected independently), before executing Spec2Testbench.

## Independent Reference

{
  "method": "manual_transient_estimate",
  "equation": "Input and output transition timing inspected independently",
  "expected_value": 1e-05,
  "unit": "s",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
