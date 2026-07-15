# Pilot Functional Fixes

- Scope: functional fixes only for the four root causes proven by the end-to-end FALSE_ACCEPT audit.
- Excluded on purpose: permissive YAML threshold recalibration and all historical forensic artifacts.
- Historical artifacts preserved unchanged under `artifacts/pilot_false_accept_forensics/`.

## Regression Coverage Added

- `test_controlled_variant_override_applies_to_transient_analysis`
- `test_missing_measure_does_not_fall_back_to_synthetic_zero`
- `test_metric_extractor_does_not_reconstruct_missing_propagation_delay`
- `test_parse_measure_not_found_nan_and_inf`
- `test_parse_measure_empty_file_is_not_a_zero`
- `test_parse_measure_unparsable_text_is_not_a_zero`
- `test_small_threshold_minimum_does_not_snap_to_pass`
- `test_small_threshold_explicit_tolerance_can_pass`
- `test_invalid_oscillation_blocks_frequency_metric`
- `test_real_pipeline_detects_non_oscillating_variant_as_not_evaluated`

## Case Outcomes

### cv_014_p09_input_slow

- Before status: `PASS`
- After status: `APPLIED`
- Before value: `-4.83103e-11`
- After value: `step_time=100U; end_time=2`
- Expected status: `VARIANT_OVERRIDE_APPLIED`
- Root cause: `GROUND_TRUTH_ERROR`
- Regression test: `test_controlled_variant_override_applies_to_transient_analysis`
- Outcome: Controlled variant override is now applied with explicit provenance and highest priority.

### cv_020_p28_ref_high

- Before status: `PASS`
- After status: `NOT_EVALUATED`
- Before value: `0.0`
- After value: `null`
- Expected status: `NOT_EVALUATED`
- Root cause: `MEASURE_VALUE_NOT_PROPAGATED`
- Regression test: `test_missing_measure_does_not_fall_back_to_synthetic_zero; test_metric_extractor_does_not_reconstruct_missing_propagation_delay; test_parse_measure_not_found_nan_and_inf; test_parse_measure_empty_file_is_not_a_zero; test_parse_measure_unparsable_text_is_not_a_zero`
- Outcome: Missing .measure results now stay null and propagate to NOT_EVALUATED instead of synthetic zero.

### cv_019_p22_vdd_low

- Before status: `PASS`
- After status: `FAIL`
- Before value: `1.17961e-16`
- After value: `1.17961e-16`
- Expected status: `FAIL`
- Root cause: `WRONG_THRESHOLD`
- Regression test: `test_small_threshold_minimum_does_not_snap_to_pass; test_small_threshold_explicit_tolerance_can_pass`
- Outcome: Tiny-threshold comparison now fails unless an explicit tolerance is present in the specification.

### cv_017_p22_c_large

- Before status: `PASS`
- After status: `NOT_EVALUATED`
- Before value: `19999.600063989757`
- After value: `null`
- Expected status: `NOT_EVALUATED`
- Root cause: `SEMANTIC_ALIAS_ERROR`
- Regression test: `test_invalid_oscillation_blocks_frequency_metric; test_real_pipeline_detects_non_oscillating_variant_as_not_evaluated`
- Outcome: Oscillator frequency is now gated on validated oscillation rather than FFT presence alone.

## Validation Runs

- `RUN_NGSPICE_INTEGRATION=1 pytest -q` -> `66 passed, 1 warning`
- `SPEC2TESTBENCH_DISABLE_PYSPICE=1 RUN_NGSPICE_INTEGRATION=1 pytest -q` -> `66 passed, 1 warning`

## Notes

- `cv_014_p09_input_slow` now applies the controlled transient override, but the case itself still evaluates `PASS` because its YAML threshold remains permissive and was intentionally left unchanged by this task.
- `cv_019_p22_vdd_low` now evaluates `FAIL` even with another oscillator metric missing, because the required-failure aggregation takes precedence over `NOT_EVALUATED` when a mandatory metric is already failing.
- `cv_017_p22_c_large` and the nominal `p22_oscillator` integration path now expose non-oscillation as `NOT_EVALUATED` rather than accepting a Fourier peak as proof of oscillation.
