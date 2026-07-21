# Deterministic Versus DeepSeek

Date: 2026-07-21

The comparison below uses the same cases, netlists, specifications, checker, operating system, and ngspice installation. The only intended difference is the compiled plan source.

| Case | D0 Compliance | L2 Majority Compliance | Delta |
| --- | --- | --- | --- |
| fp2_cv_006_p01_gain_strong | FAIL | FAIL | same |
| fp2_cv_011_p17_current_strong | FAIL | PASS | changed |
| fp2_cv_012_p16_bias_strong | FAIL | FAIL | same |
| fp2_cv_013_p20_bias_strong | FAIL | FAIL | same |
| fp2_cv_019_p22_amplitude_strong | FAIL | PASS | changed |
| fp2_cv_023_p05_current_strong | FAIL | FAIL | same |
| fp2_cv_026_p07_output_strong | FAIL | FAIL | same |
| ref_fp2_p01_amplifier | PASS | FAIL | changed |
| ref_fp2_p05_amplifier | PASS | PASS | same |
| ref_fp2_p07_inverter | PASS | PASS | same |
| ref_fp2_p16_opamp | PASS | PASS | same |
| ref_fp2_p17_currentmirror | PASS | PASS | same |
| ref_fp2_p20_opamp | PASS | PASS | same |
| ref_fp2_p22_oscillator | PASS | PASS | same |
| wrdata_controlled_violation | FAIL | PASS | changed |
| wrdata_nominal | PASS | PASS | same |

Headline:

- D0 is stronger on the inverter operating-point pair because it avoids the unevaluated outcome seen in the stub-backed L2 plan.
- L2 remains execution-stable across all 48 frozen trials.
