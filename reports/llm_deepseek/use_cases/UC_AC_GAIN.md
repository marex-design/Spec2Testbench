# UC_AC_GAIN

Date: 2026-07-21

- Rows: 10
- L2 rows: 7
- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- Mean L2 metric coverage: 1.00

| Case | Mode | Compliance | Coverage | Validity |
| --- | --- | --- | --- | --- |
| smoke_p01_gain | deterministic | PASS | 1.0 | VALID |
| smoke_p01_gain | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p01_amplifier | deterministic | PASS | 1.0 | VALID |
| ref_fp2_p01_amplifier | deepseek_refinement | FAIL | 1.0 | VALID |
| ref_fp2_p01_amplifier | deepseek_refinement | FAIL | 1.0 | VALID |
| ref_fp2_p01_amplifier | deepseek_refinement | FAIL | 1.0 | VALID |
| fp2_cv_006_p01_gain_strong | deterministic | FAIL | 1.0 | VALID |
| fp2_cv_006_p01_gain_strong | deepseek_refinement | FAIL | 1.0 | VALID |

Notes:

- Use-case reports combine smoke evidence and frozen-pilot evidence when both exist.
- Missing frozen rows for a use case mean that the use case is currently covered only by the smoke campaign.
