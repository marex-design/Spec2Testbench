# DeepSeek Failure Analysis

Date: 2026-07-21

This report focuses on L2 stub trials that did not align cleanly with frozen ground truth.

- False accepts: 9
- False rejects: 3
- Unevaluated trials: 0

| Case | Use Case | Compliance | Outcome | Notes |
| --- | --- | --- | --- | --- |
| fp2_cv_011_p17_current_strong | UC_DC_CURRENT_POWER | PASS | FALSE_ACCEPT | agreement gap |
| fp2_cv_011_p17_current_strong | UC_DC_CURRENT_POWER | PASS | FALSE_ACCEPT | agreement gap |
| fp2_cv_011_p17_current_strong | UC_DC_CURRENT_POWER | PASS | FALSE_ACCEPT | agreement gap |
| fp2_cv_019_p22_amplitude_strong | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |
| fp2_cv_019_p22_amplitude_strong | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |
| fp2_cv_019_p22_amplitude_strong | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |
| wrdata_controlled_violation | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |
| wrdata_controlled_violation | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |
| wrdata_controlled_violation | UC_OSCILLATION_FREQUENCY | PASS | FALSE_ACCEPT | agreement gap |

Observed pattern:

- `wrdata_controlled_violation` and `fp2_cv_019_p22_amplitude_strong` stay compliant under the current stub strategy because startup-amplitude planning alone does not encode the intended noncompliance semantics.
- `ref_fp2_p07_inverter` and `fp2_cv_026_p07_output_strong` remain executable but unevaluated, which points to measurement coverage limits rather than provider or compiler failure.
