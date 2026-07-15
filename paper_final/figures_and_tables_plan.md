# Figures and Tables Plan

## Planning Principles

This plan is derived from the revised manuscript sections and the canonical evidence ledger. Every figure and every table must have a single scientific message, must be evidence-bearing rather than decorative, and must remain readable in a two-column `IEEEtran` layout. Relative LaTeX paths should be used throughout, for example `figures/figure_name.pdf` and `tables/table_name.tex`.

Two additional rules apply to the full set. First, figures and tables must not silently merge incompatible datasets such as the frozen pilot V3 and the later expanded controlled-violation campaign. Second, any item tied to an unexecuted ablation, robustness study, or expert-validation study must remain explicitly marked `TBD`, `Results Pending`, or `Not Executed`.

## Figures

### Figure 1 - Complete Spec2Testbench Architecture

- Scientific message:
  The framework is a traceable specification-to-evidence pipeline in which execution, extraction, checking, classification, and reporting are separated, preventing simulator success from being mistaken for compliance.
- Required content:
  `YAML -> Normalizer -> Planner -> Deterministic/LLM Generator -> ngspice -> Result Backend -> Metric Extractor -> Checker -> Status Classifier -> Reports`
- Evidence anchor:
  [method_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\method_revised.tex), [framework_architecture_spec.md](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\figures\framework_architecture_spec.md)
- Format recommendation:
  `figure*` across two columns, because the 10-stage pipeline and the anti-false-PASS callouts will be cramped in single-column mode.
- Relative LaTeX path:
  `figures/spec2testbench_architecture.pdf`
- Readability requirement:
  Block labels must remain legible at final two-column width; avoid paragraph text inside blocks.

### Figure 2 - Complementarity with AnalogCoder-Pro

- Scientific message:
  Spec2Testbench is positioned as an independent compliance-evidence layer complementary to AnalogCoder-Pro rather than as a replacement for circuit generation and optimization.
- Required content:
  `Natural-Language Design Goals -> AnalogCoder-Pro -> Generated and Optimized Circuit -> Spec2Testbench -> Independent Compliance Evidence`
- Evidence anchor:
  [manuscript_rewrite_constraints.md](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\manuscript_rewrite_constraints.md), [method_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\method_revised.tex)
- Scope note:
  The figure must not imply that AnalogCoder-Pro performs no verification. It should say or visually suggest that AnalogCoder-Pro yields a circuit candidate and that Spec2Testbench provides independent, traceable compliance evidence.
- Format recommendation:
  Single-column `figure` if the chain is rendered compactly; otherwise a narrow `figure*` with large typography.
- Relative LaTeX path:
  `figures/analogcoder_spec2testbench_complementarity.pdf`

### Figure 3 - Status Space

- Scientific message:
  The status taxonomy separates execution failure, scientific ineligibility, simulability without compliance, compliant nominal behavior, and robustness-related states, so one status cannot be substituted for another.
- Required content:
  Distinguish visually:
  `simulation failure`, `mock/ineligible`, `simulable noncompliant`, `compliant nominal`, `robust`
- Evidence anchor:
  [method_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\method_revised.tex), [docs/verdict_semantics.md](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\docs\verdict_semantics.md), [canonical_results_summary.md](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\canonical_results_summary.md)
- Scope note:
  The `robust` region must be visually marked as a taxonomy state or framework category boundary, not as a completed paper result, because canonical robustness evidence is `NOT_EXECUTED`.
- Format recommendation:
  Single-column `figure` with a compact state map or layered status diagram.
- Relative LaTeX path:
  `figures/status_space.pdf`

### Figure 4 - p04 Case Study

- Scientific message:
  `p04_amplifier` is the direct canonical counterexample showing that successful real simulation and successful metric extraction do not imply compliance.
- Required content:
  analysis performed, gain measurement, threshold, verdict
- Canonical values:
  execution `SUCCESS`, mode `REAL`, metric `dc_gain_db`, value `-160.0000000868589 dB`, threshold `>= 0.0 dB`, verdict `SIMULABLE_NONCOMPLIANT`
- Evidence anchor:
  [results_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\results_revised.tex), `results/paper_metric_results.csv`, `artifacts/paper_campaign/20260711_094959/p04_amplifier/report.json`
- Format recommendation:
  Single-column `figure` with one compact signal-to-verdict flow or a callout card; it should be visually tied to the equation `SIMULABLE != COMPLIANT`.
- Relative LaTeX path:
  `figures/p04_case_study.pdf`

### Figure 5 - Controlled-Violation Matrix

- Scientific message:
  The controlled-violation story depends on dataset choice; the frozen pilot V3 supports a clean confusion matrix, while the later expanded campaign must be shown as a separate sensitivity result.
- Required content:
  `TRUE_ACCEPT`, `TRUE_DETECTION`, `FALSE_ACCEPT`, `FALSE_REJECT`
- Canonical handling:
  Show the frozen pilot V3 confusion matrix as the main matrix. Add an explicit side note or inset stating that the expanded campaign (`20260712_195226`) produced one false accept among two effective violations and must not be merged silently with the V3 matrix.
- Evidence anchor:
  [results_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\results_revised.tex), `results/frozen_pilot_metrics_v3.json`, `results/final_controlled_summary.json`
- Format recommendation:
  Single-column `figure` if rendered as a compact 2x2 matrix plus side note; otherwise `figure*`.
- Relative LaTeX path:
  `figures/controlled_violation_matrix.pdf`

### Figure 6 - Specification-to-Evidence Example

- Scientific message:
  A single requirement can be traced from YAML specification through testbench generation and waveform evidence to a metric, assertion, and final verdict.
- Required content:
  YAML, testbench, waveform, metric, assertion, verdict
- Circuit choice recommendation:
  Use one circuit with clean nominal evidence and a legible waveform-backed metric. An oscillator WRDATA case is attractive because it can show YAML, vectors/waveform, metric extraction, and verdict in one path, but a simpler nominal case may be better for readability.
- Evidence anchor:
  [method_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\method_revised.tex), `results/wrdata_independent_comparisons.csv`, per-case artifacts in `artifacts/paper_campaign/20260711_094959/` or WRDATA extension artifacts
- Format recommendation:
  `figure*` if a six-stage horizontal storyboard is used; otherwise a vertical single-column composite with clearly segmented panels.
- Relative LaTeX path:
  `figures/specification_to_evidence_example.pdf`

## Tables

### Table 1 - Neutral Related-Work Positioning

- Scientific message:
  Related approaches should be positioned by role and evidence scope rather than ranked rhetorically.
- Required columns:
  `Work`, `Primary role`, `Circuit source`, `Verification evidence type`, `Independent compliance layer`, `Executed robustness evidence`, `Notes`
- Constraint:
  Use neutral wording. Do not imply unsupported superiority over AnalogCoder-Pro or other tools. If bibliography support is still incomplete, cells should be marked `TBD -- TO BE FILLED FROM CANONICAL EVIDENCE`.
- Format recommendation:
  `table*`
- Relative LaTeX path:
  `tables/related_work_positioning.tex`

### Table 2 - ACP-28 Characterization

- Scientific message:
  The nominal benchmark-aligned corpus has a defined family composition, analysis coverage, metric intent, and local netlist complexity profile.
- Required content:
  28 circuits, 14 families, local netlist complexity summary, analysis families, metric families, technology/model wording
- Evidence anchor:
  [experimental_methodology.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\experimental_methodology.tex), `benchmark/README.md`, `testbenches/benchmark/manifest.csv`, `results/paper_campaign_summary.csv`
- Format recommendation:
  `table*`
- Relative LaTeX path:
  `tables/acp28_characterization.tex`

### Table 3 - Nominal Status Summary

- Scientific message:
  The canonical nominal campaign achieved full real execution but not universal compliance.
- Required content:
  28 circuits, 28 REAL, 0 mock, 28 success, 28 eligible, 27 `SIMULABLE_COMPLIANT`, 1 `SIMULABLE_NONCOMPLIANT`
- Existing starting point:
  [results_tables.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\tables\results_tables.tex), Table `tab:rq1_nominal_summary` and `tab:rq2_nominal_compact`
- Format recommendation:
  single-column summary if compressed, otherwise `table*`
- Relative LaTeX path:
  `tables/nominal_status_summary.tex`

### Table 4 - Controlled-Violation Results

- Scientific message:
  Controlled-violation evidence must be split by retained dataset, with the frozen pilot V3 as the canonical main matrix and the expanded campaign as a sensitivity result.
- Required content:
  V3 counts for `TRUE_ACCEPT`, `TRUE_DETECTION`, `FALSE_ACCEPT`, `FALSE_REJECT`, `UNEVALUATED`; expanded campaign fields for generated variants, effective violations, one false accept, and zero unevaluated effective cases
- Existing starting point:
  [results_tables.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\tables\results_tables.tex), Tables `tab:rq3_controlled_conflicts` and `tab:rq3_effective_summary`
- Format recommendation:
  `table*`
- Relative LaTeX path:
  `tables/controlled_violation_results.tex`

### Table 5 - Backends and Provenance

- Scientific message:
  Native evidence extraction is supported by both `NGSPICE_MEASURE` and `NGSPICE_WRDATA`, and each verdict is tied to provenance rather than to an opaque simulator outcome.
- Required columns:
  `Backend`, `Evidence dataset`, `Cases`, `Agreement / status`, `PySpice dependency`, `Provenance fields retained`
- Canonical values:
  `NGSPICE_MEASURE` validated in frozen pilot V3 and native integration artifacts; `NGSPICE_WRDATA` validated on 2/2 independent comparisons
- Evidence anchor:
  [method_revised.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\sections\method_revised.tex), `results/wrdata_independent_comparisons.csv`, `results/full_ngspice_native_test_results.json`, per-case provenance artifacts
- Format recommendation:
  single-column if compact, otherwise `table*`
- Relative LaTeX path:
  `tables/backends_and_provenance.tex`

### Table 6 - LLM Versus Baseline

- Scientific message:
  There is currently no canonical quantitative LLM-versus-baseline result block.
- Required handling:
  If no executed ablation results become available, keep the title `Planned LLM Ablation -- Results Pending` and leave data cells as `TBD -- TO BE FILLED FROM CANONICAL EVIDENCE`.
- Existing starting point:
  [results_tables.tex](E:\my_organisation\Memoire Maruba\code\Spec2Testbench\paper_final\tables\results_tables.tex), Table `tab:planned_llm_ablation`
- Format recommendation:
  `table*`
- Relative LaTeX path:
  `tables/llm_baseline_comparison.tex`

### Table 7 - Expert Agreement

- Scientific message:
  Human expert agreement cannot be claimed unless a completed expert-validation study is located in canonical evidence.
- Required handling:
  If no executed expert-validation artifact exists, create a placeholder table titled `Expert Agreement -- Results Pending` or omit the table from the compiled manuscript while retaining the plan entry for future work.
- Suggested columns if later executed:
  `Case set`, `Experts`, `Agreement metric`, `Scope`, `Status`
- Format recommendation:
  single-column placeholder is sufficient
- Relative LaTeX path:
  `tables/expert_agreement.tex`

## Double-Column Readability Checklist

- Use `figure*` or `table*` for architecture diagrams, six-stage storyboards, and dense multi-dataset comparisons.
- Keep all axis labels and matrix labels readable at final print size; if labels must be abbreviated, decode them in the caption.
- Avoid more than one dense message per visual. If a figure tries to show both execution coverage and backend validation and controlled-violation conflict at once, split it.
- Keep p04 case-study typography large enough that the measured value and threshold are readable without zooming.
- For wide tables, prefer fewer rows with grouped entries over exhaustive per-circuit listings in the main text; move full circuit tables to an appendix if needed.

## Recommended Build Order

1. Finalize Table 3 and Table 4 from the existing results tables.
2. Generate Figure 1 from the existing architecture spec.
3. Generate Figure 4 and Figure 5 because they carry the central scientific argument.
4. Add Table 5 to bridge methods and results.
5. Draft Figure 2 and Figure 6 only after the manuscript wording on positioning and worked example is frozen.
6. Keep Table 6 and Table 7 as explicit pending placeholders unless new canonical evidence appears.
