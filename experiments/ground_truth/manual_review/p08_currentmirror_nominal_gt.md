# Manual Review: p08_currentmirror_nominal_gt

- Original circuit: `p08_currentmirror`
- Circuit family: `current_mirror`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `quiescent_current`
- Manual review status: `manually_verified`

## Physical Justification

p08_currentmirror is a nominal benchmark circuit. The label is assigned from independent_ngspice evidence (Operating-point current measured by direct ngspice raw export), before executing Spec2Testbench.

## Independent Reference

{
  "method": "independent_ngspice",
  "equation": "Operating-point current measured by direct ngspice raw export",
  "expected_value": 0.00025,
  "unit": "A",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
