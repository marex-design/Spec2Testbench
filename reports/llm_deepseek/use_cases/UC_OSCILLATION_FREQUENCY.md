# UC_OSCILLATION_FREQUENCY

Date: 2026-07-21

- Rows: 18
- L2 rows: 13
- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- Mean L2 metric coverage: 1.00

| Case | Mode | Compliance | Coverage | Validity |
| --- | --- | --- | --- | --- |
| smoke_p22_frequency | deterministic | NOT_EVALUATED | 0.0 | VALID |
| smoke_p22_frequency | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p22_oscillator | deterministic | PASS | 1.0 | VALID |
| ref_fp2_p22_oscillator | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p22_oscillator | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p22_oscillator | deepseek_refinement | PASS | 1.0 | VALID |
| fp2_cv_019_p22_amplitude_strong | deterministic | FAIL | 1.0 | VALID |
| fp2_cv_019_p22_amplitude_strong | deepseek_refinement | PASS | 1.0 | VALID |

Notes:

- Use-case reports combine smoke evidence and frozen-pilot evidence when both exist.
- Missing frozen rows for a use case mean that the use case is currently covered only by the smoke campaign.
