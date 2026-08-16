# v0.5.0

- Removed the unrelated `reference_28` benchmark and legacy frozen/live campaign artifacts.
- Retained only AnalogCoder-Pro ACP-28 as the external circuit corpus.
- Replaced broken controlled-violation references with 26 materialized active-DUT mutations plus SHA-256 effectiveness evidence.
- Made the independent p10/p11 manual oracle the primary confusion-matrix ground truth.
- Added `top_p` to DeepSeek configuration, request execution, CLI and campaign summaries.
- Added case-level majority confusion matrices, Wilson 95% confidence intervals and exact paired McNemar comparisons.
- Added `Cov_circuits`, `Cov_metrics`, `Cov_analyses` to the ACP compliance summary.
- Removed obsolete scripts, generated outputs, pre-generated testbenches and old evidence bundles.
- Updated model-discovery/provider-smoke scripts to use the current DeepSeek adapter.
- Made `benchmark/analogcoder_pro/specs/` the single canonical YAML v2 source for CLI, ACP, hybrid, oracle and mutation workflows; removed the legacy duplicate benchmark-spec dialect.
- Made schema-v2 port roles authoritative so reference/bias/supply nodes are never silently reclassified as user inputs.
- Fixed verdict-leakage tokenization so circuit terms such as `low-pass` do not trigger a false `PASS` leakage alarm; added a regression test.
- Final local validation: **273 passed, 23 skipped, 0 failed**; skipped tests require ngspice and/or live LLM credentials unavailable in the audit environment.
- Version bumped to 0.5.0.
