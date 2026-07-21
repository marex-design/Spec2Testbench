# Deterministic Parity Audit

Date: 2026-07-21

- Deterministic source: `frozen_v3_reference`
- Cases audited: 16
- Exact matches: 16
- Numeric equivalents: 0
- Divergences: 0
- Legacy replay classification divergences: 2

| Case | Parity Status | Historical Outcome | New Outcome |
| --- | --- | --- | --- |
| ref_fp2_p01_amplifier | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p05_amplifier | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p17_currentmirror | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p16_opamp | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p20_opamp | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p22_oscillator | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| ref_fp2_p07_inverter | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| fp2_cv_006_p01_gain_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_023_p05_current_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_011_p17_current_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_012_p16_bias_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_013_p20_bias_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_019_p22_amplitude_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| fp2_cv_026_p07_output_strong | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |
| wrdata_nominal | EXACT_MATCH | TRUE_ACCEPT | TRUE_ACCEPT |
| wrdata_controlled_violation | EXACT_MATCH | TRUE_DETECTION | TRUE_DETECTION |

Legacy replay divergences kept for forensic traceability:

| Case | Legacy Replay Root Cause |
| --- | --- |
| ref_fp2_p01_amplifier | WRONG_TESTBENCH |
| fp2_cv_011_p17_current_strong | WRONG_OPERATOR |
