# DeepSeek Campaign Report

Date: 2026-07-21
Provider: stub
Run id: stub_frozen_20260721

The frozen pilot used 16 explicit cases and 48 L2 trials. The provider remained stub-backed because `DEEPSEEK_API_KEY` was absent on 2026-07-21.

- D0 cases attempted: 16
- L2 trials attempted: 48
- L2 valid-plan rate: 100.0%
- L2 real-simulation rate: 100.0%
- L2 success rate: 100.0%
- L2 full metric coverage rate: 100.0%

| Metric | D0 | L2 |
| --- | --- | --- |
| Rows | 16 | 48 |
| TRUE_ACCEPT | 8 | 21 |
| TRUE_DETECTION | 8 | 15 |
| FALSE_ACCEPT | 0 | 9 |
| FALSE_REJECT | 0 | 3 |
| UNEVALUATED | 0 | 0 |

Interpretation:

- The implementation path is stable enough to generate valid structured plans and executable ngspice decks on every stub trial.
- Scientific agreement is mixed because several frozen cases intentionally remain difficult, and the stub provider is not tuned to optimize verdict agreement.
- Live DeepSeek evidence is still pending; these results are implementation and orchestration evidence only.
