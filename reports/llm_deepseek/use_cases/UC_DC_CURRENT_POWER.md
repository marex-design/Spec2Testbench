# UC_DC_CURRENT_POWER

Date: 2026-07-21

- Rows: 34
- L2 rows: 25
- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- Mean L2 metric coverage: 1.00

| Case | Mode | Compliance | Coverage | Validity |
| --- | --- | --- | --- | --- |
| smoke_p05_current | deterministic | PASS | 1.0 | VALID |
| smoke_p05_current | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p05_amplifier | deterministic | PASS | 1.0 | VALID |
| ref_fp2_p05_amplifier | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p05_amplifier | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p05_amplifier | deepseek_refinement | PASS | 1.0 | VALID |
| ref_fp2_p17_currentmirror | deterministic | PASS | 1.0 | VALID |
| ref_fp2_p17_currentmirror | deepseek_refinement | PASS | 1.0 | VALID |

Notes:

- Use-case reports combine smoke evidence and frozen-pilot evidence when both exist.
- Missing frozen rows for a use case mean that the use case is currently covered only by the smoke campaign.
