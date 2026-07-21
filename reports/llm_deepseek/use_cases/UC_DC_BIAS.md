# UC_DC_BIAS

Date: 2026-07-21

- Rows: 10
- L2 rows: 7
- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- Mean L2 metric coverage: 1.00

| Case | Mode | Compliance | Coverage | Validity |
| --- | --- | --- | --- | --- |
| smoke_p07_bias | deterministic | PASS | 1.0 | VALID |
| smoke_p07_bias | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p07_inverter | deterministic | PASS | 1.0 | VALID |
| ref_fp2_p07_inverter | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p07_inverter | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p07_inverter | deepseek_refinement | PASS | 1.0 | VALID |
| fp2_cv_026_p07_output_strong | deterministic | FAIL | 1.0 | VALID |
| fp2_cv_026_p07_output_strong | deepseek_refinement | FAIL | 1.0 | VALID |

Notes:

- Use-case reports combine smoke evidence and frozen-pilot evidence when both exist.
- Missing frozen rows for a use case mean that the use case is currently covered only by the smoke campaign.
