# Manual Review: p19_mixer_nominal_gt

- Original circuit: `p19_mixer`
- Circuit family: `mixer`
- Ground-truth label: `GROUND_TRUTH_COMPLIANT`
- Target metric: `thd`
- Manual review status: `manually_verified`

## Physical Justification

p19_mixer is a nominal benchmark circuit. The label is assigned from manual_spectral_estimate evidence (Mixer spectral content expected to remain finite and simulable), before executing Spec2Testbench.

## Independent Reference

{
  "method": "manual_spectral_estimate",
  "equation": "Mixer spectral content expected to remain finite and simulable",
  "expected_value": 1.0,
  "unit": "%",
  "tolerance_percent": 20
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
