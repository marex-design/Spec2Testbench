# Manual Review: p27_subtractor_nominal_gt

- Original circuit: `p27_subtractor`
- Circuit family: `composite`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `operating_point`
- Manual review status: `manually_verified`

## Physical Justification

p27_subtractor is a nominal benchmark circuit. The label is assigned from manual_dc_estimate evidence (Differential topology expected to remain simulable and bounded), before executing Spec2Testbench.

## Independent Reference

{
  "method": "manual_dc_estimate",
  "equation": "Differential topology expected to remain simulable and bounded",
  "expected_value": 0.1,
  "unit": "V",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
