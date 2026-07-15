# Manual Review: p22_oscillator_nominal_gt

- Original circuit: `p22_oscillator`
- Circuit family: `oscillator`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `oscillator_frequency`
- Manual review status: `manually_verified`

## Physical Justification

p22_oscillator is a nominal benchmark circuit. The label is assigned from manual_transient_estimate evidence (Period estimated from transient zero crossings), before executing Spec2Testbench.

## Independent Reference

{
  "method": "manual_transient_estimate",
  "equation": "Period estimated from transient zero crossings",
  "expected_value": 20000.0,
  "unit": "Hz",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
