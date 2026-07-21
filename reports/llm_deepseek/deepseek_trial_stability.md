# Stub Trial Determinism

Date: 2026-07-21

The L2 provider used here is deterministic stub logic, so high agreement is expected and desirable as a pipeline sanity check. These numbers describe stub determinism, not live-LLM stability.

- Stable verdict rows: 16 of 16

| Case | Trials | Verdict Stable | Backend Agreement | Latency Median (s) |
| --- | --- | --- | --- | --- |
| ref_fp2_p01_amplifier | 3 | True | True | 0.0 |
| ref_fp2_p05_amplifier | 3 | True | True | 0.0 |
| ref_fp2_p17_currentmirror | 3 | True | True | 0.0 |
| ref_fp2_p16_opamp | 3 | True | True | 0.0 |
| ref_fp2_p20_opamp | 3 | True | True | 0.0 |
| ref_fp2_p22_oscillator | 3 | True | True | 0.0 |
| ref_fp2_p07_inverter | 3 | True | True | 0.0 |
| fp2_cv_006_p01_gain_strong | 3 | True | True | 0.001001596450805664 |
| fp2_cv_023_p05_current_strong | 3 | True | True | 0.0 |
| fp2_cv_011_p17_current_strong | 3 | True | True | 0.0 |
| fp2_cv_012_p16_bias_strong | 3 | True | True | 0.0 |
| fp2_cv_013_p20_bias_strong | 3 | True | True | 0.0 |
| fp2_cv_019_p22_amplitude_strong | 3 | True | True | 0.0 |
| fp2_cv_026_p07_output_strong | 3 | True | True | 0.0 |
| wrdata_nominal | 3 | True | True | 0.0 |
| wrdata_controlled_violation | 3 | True | True | 0.0 |

Live caveat:

- These stability numbers should not be extrapolated to live DeepSeek until `RUN_LLM_LIVE=1` campaigns are executed with the configured production model.
