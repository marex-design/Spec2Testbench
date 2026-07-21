# Missed Effective Mutation Root Cause

Date: 2026-07-21

The current replay points to `cv_019_p22_vdd_low` as the single effective threshold-crossing false accept that is still worth isolating for framework follow-up.

- Target metric: `startup_amplitude`
- Threshold in frozen manifest: `1e-12`
- Threshold in loaded specification: `1e-12`
- Operator: `>=`
- Unit: `V`
- Independent measured value: `1.17961e-16`
- Pipeline measured value: `1.17961e-16`
- Checker tolerance: `ABSOLUTE_TOLERANCE=1e-12`
- Backend: `NGSPICE_MEASURE`
- Historical verdict: `PASS`
- Corrected replay verdict: `FAIL`
- Root cause: `WRONG_THRESHOLD`
- Correctable: yes
- Historical result preserved: yes

Recommended framework fix:

Remove or scale down the absolute 1e-12 snap-to-threshold tolerance for tiny positive minima so startup_amplitude below 1e-12 V cannot be promoted to PASS.

Regression evidence:

- Existing regression tests: `test_small_threshold_minimum_does_not_snap_to_pass; test_small_threshold_explicit_tolerance_can_pass`
