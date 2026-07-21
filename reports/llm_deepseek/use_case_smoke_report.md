# DeepSeek Use-Case Smoke Report

Date: 2026-07-21
Provider: stub
Run id: stub_use_case_smoke_20260721

This smoke campaign exercised seven explicit use cases with D0 and one L2 stub trial per case because no live DeepSeek credential was available locally.

- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- L2 execution-success rate: 100.0%
- L2 full metric coverage rate: 100.0%
- Mean L2 metric coverage: 1.00
- GO_USE_CASE_SMOKE: PASS on stub evidence because all 7 of 7 L2 runs produced valid plans, compiled decks, and real ngspice execution.

| Use Case | Trials | Valid Plans | Real Sims | Coverage>=1.0 |
| --- | --- | --- | --- | --- |
| UC_AC_GAIN | 1 | 1 | 1 | 1 |
| UC_DC_BIAS | 1 | 1 | 1 | 1 |
| UC_DC_CURRENT_POWER | 1 | 1 | 1 | 1 |
| UC_FILTER_CUTOFF_BANDWIDTH | 1 | 1 | 1 | 1 |
| UC_OSCILLATION_FREQUENCY | 1 | 1 | 1 | 1 |
| UC_SWITCHING_THRESHOLD_HYSTERESIS | 1 | 1 | 1 | 1 |
| UC_TRANSIENT_DELAY | 1 | 1 | 1 | 1 |

Limitations:

- This is stub-backed planning evidence, not live DeepSeek evidence.
- Full metric coverage is partial on several waveform-heavy use cases even though the testbench itself remained valid and executable.
