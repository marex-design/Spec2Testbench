# Canonical Results Summary

## Scope and Canonical Preference

This audit treats machine-readable campaign outputs in `results/` and per-case artifacts in `artifacts/` as canonical over prose summaries when they disagree. For the nominal paper evidence, the canonical run is `results/paper_campaign_summary.json` with run id `20260711_094959`. For the frozen pilot comparison evidence, the canonical source is `results/frozen_pilot_metrics_v3.json`. For the larger controlled-violation study, the canonical source is `results/final_controlled_summary.json` and its row-level companion `results/controlled_violation_results_v2.csv`.

## Results Authorized for the Manuscript

The canonical nominal paper campaign contains 28 circuits, all executed in `REAL` mode, all with `execution_status = SUCCESS`, and all marked `paper_eligible = True` in `results/paper_campaign_summary.csv`. Among these 28 cases, 27 are `SIMULABLE_COMPLIANT` and one is `SIMULABLE_NONCOMPLIANT`. The unique noncompliant nominal case is `p04_amplifier`, which remains simulable but fails `dc_gain_db`; the measured value is `-160.0000000868589 dB` against a threshold `>= 0.0 dB`, as shown in `results/paper_metric_results.csv` and `artifacts/paper_campaign/20260711_094959/p04_amplifier/report.json`.

The native backend evidence is also supported. `NGSPICE_MEASURE` is validated by the real-measurement evidence in `results/full_ngspice_native_test_results.json` and by the row-level frozen pilot evidence in `results/frozen_pilot_results_v3.csv`. `NGSPICE_WRDATA` is validated by exactly two canonical cases, with independent agreement in both rows of `results/wrdata_independent_comparisons.csv`; the prose summary in `reports/wrdata_end_to_end_validation.md` confirms one nominal pass and one controlled-violation fail.

The frozen pilot V3 remains a valid, limited evidence block when described exactly as `16` cases with `TRUE_ACCEPT = 8`, `TRUE_DETECTION = 8`, `FALSE_ACCEPT = 0`, `FALSE_REJECT = 0`, and `UNEVALUATED = 0`, as recorded in `results/frozen_pilot_metrics_v3.json`. The canonical software-test artifact for the manuscript is `results/final_test_results.json`, which reports `66` unique tests, with `66 passed, 0 failed, 0 skipped, 1 warning` both in normal mode and with PySpice disabled. This file also records `mock_results_included = false`.

For the expanded controlled-violation study, only the cautious statements supported by `results/final_controlled_summary.json` are authorized. That dataset contains `30` generated variants, but only `2` effective controlled violations and `28` ineffective mutations. Among the `2` effective violations, one is detected and one is missed, yielding `detected_effective_violations = 1`, `false_pass = 1`, `violation_detection_recall = 0.5`, and `false_pass_rate = 0.5`. These are not population-wide claims over 30 effective violations and should be presented only as limited evidence.

## Results Forbidden Because Obsolete

The repository still contains earlier campaign outputs that must not be treated as current paper evidence. `results/controlled_violation_metrics.json` and `results/controlled_violation_results.csv` describe an earlier 30-case campaign with `28` `FALSE_PASS` and `2` `TRUE_NON_SIMULABLE`, effectively a pre-fix failure regime rather than the final calibrated interpretation. Those files are historically important for traceability, but they are obsolete as manuscript evidence if presented as the current state.

The repository also contains older framework summaries such as `results/reference_28_framework_campaign.json` and `results/reference_28_framework_campaign.md`. These use legacy fields such as `overall_verdict`, `compliance_score`, and `success_rate`, and they disagree with the canonical paper campaign on at least some cases, including `p11_highpass`, `p22_oscillator`, and `p23_oscillator`. They should not be used to support current scientific claims about the paper campaign.

Any wording implying that all generated mutations were effective controlled violations is forbidden. The canonical evidence shows that only `2` of `30` generated variants were effective in `results/final_controlled_summary.json`. Any wording that equates mutation generation with effective violation creation would overstate the evidence.

## Contradictory Results That Must Be Handled Explicitly

The current manuscript is internally stale. `paper_final/main.tex` still says that the frozen pilot combines seven compliant references, seven controlled violations, and two WRDATA cases, but `results/frozen_pilot_metrics_v3.json` shows the canonical V3 counts are `8 TRUE_ACCEPT` and `8 TRUE_DETECTION`. The manuscript also says that the nominal 28-circuit replay remains future work, but the canonical nominal paper campaign was already executed with run id `20260711_094959` in `results/paper_campaign_summary.json`.

There is also a controlled-campaign conflict across generations of artifacts. The frozen pilot V3 reports `FALSE_ACCEPT = 0` in `results/frozen_pilot_metrics_v3.json`, while the later expanded controlled-violation study reports one missed effective violation in `results/final_controlled_summary.json`. This is not a logical contradiction if the manuscript clearly separates the datasets, but it becomes misleading if the counts are merged or narrated as one homogeneous experiment.

The software-test count is currently conflicted across artifacts. `results/final_test_results.json` reports `66` unique tests in both normal and PySpice-disabled modes, while `results/full_ngspice_native_test_results.json` reports `55` tests in those modes for a different native-validation artifact. The manuscript should prefer the dedicated canonical test summary file if it cites a global test count, and it should avoid mixing counts from separate test-report generations.

## Missing or Not Yet Executed Evidence

The ablation evidence is incomplete. `results/final_ablation_summary.json` sets `status = PARTIAL`, with `A2 = NOT_EXECUTED`, `A4 = NOT_EXECUTED`, and `llm_included = false`. The robustness evidence is absent as executable scientific support because `results/final_robustness_metrics.json` sets `status = NOT_EXECUTED`. These topics may be described only as limitations or remaining work.

No canonical quantitative LLM comparison is available in the evidence inspected here. The same caution applies to any claim of industrial PVT validation, post-layout realism, or regulatory-style certification. The repository supports only academic benchmark evidence with limited controlled violations and native measurement validation.

## Manuscript Consequences

The manuscript may safely claim that Spec2Testbench distinguishes simulability from specification compliance, that the canonical paper campaign contains 28 real nominal runs with one scientifically noncompliant case, and that the native measurement path has direct evidence for both `NGSPICE_MEASURE` and `NGSPICE_WRDATA`. It must not claim completed robustness, completed ablation, a quantitative LLM comparison, universal controlled-violation effectiveness, or a single unified confusion matrix spanning the frozen pilot and the later expanded campaign.
