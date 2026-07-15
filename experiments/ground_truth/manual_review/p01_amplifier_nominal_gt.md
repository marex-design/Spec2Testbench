# Manual Review: p01_amplifier_nominal_gt

- Original circuit: `p01_amplifier`
- Circuit family: `amplifier`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `dc_gain_db`
- Manual review status: `manually_verified`

## Physical Justification

p01_amplifier is a nominal benchmark circuit. The label is assigned from independent_ngspice evidence (AC gain measured by direct ngspice raw export, not by SpecChecker), before executing Spec2Testbench.

## Independent Reference

{
  "method": "independent_ngspice",
  "equation": "AC gain measured by direct ngspice raw export, not by SpecChecker",
  "expected_value": -31.9,
  "unit": "dB",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
