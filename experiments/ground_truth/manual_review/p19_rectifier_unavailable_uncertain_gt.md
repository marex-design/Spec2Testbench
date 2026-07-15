# Manual Review: p19_rectifier_unavailable_uncertain_gt

- Original circuit: `p19_mixer`
- Circuit family: `rectifier_or_peak_detector_not_available`
- Ground-truth label: `GROUND_TRUTH_UNCERTAIN`
- Target metric: `n/a`
- Manual review status: `excluded_uncertain`

## Physical Justification

Excluded because the benchmark inventory does not provide a clear rectifier or peak detector parent circuit.

## Independent Reference

{
  "method": "manual_inventory",
  "equation": "No explicit rectifier or peak detector exists among the 28 available benchmark netlists.",
  "expected_value": null,
  "unit": ""
}

## Ambiguity Risks

The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.
