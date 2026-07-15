# Manuscript Rewrite Constraints

This document defines the binding rewrite constraints derived from the canonical audit evidence. All rewritten sections must satisfy these rules.

## Evidence Hierarchy

Prefer machine-readable evidence in `results/*.json`, `results/*.csv`, and per-case `artifacts/` reports over prose summaries when values disagree. When two machine-readable datasets disagree, do not harmonize them implicitly; identify the dataset, its run id or file name, and restrict the claim to that dataset only.

Every quantitative statement must be traceable to a named file and, when practical, to a row, field, or case identifier. If a quantitative claim cannot be tied to an identifiable artifact, replace it with `TBD -- TO BE FILLED FROM CANONICAL EVIDENCE`.

## Naming and Terminology

Use the exact framework name `Spec2Testbench` everywhere. Do not introduce variants such as `Spec2TestBench`.

Distinguish explicitly between circuit generation, simulability, general execution success, specification compliance, robustness, and scientific eligibility. Do not collapse these concepts into a single verdict. Legacy fields such as `overall_verdict`, `success_rate`, or `compliance_score` may be mentioned only as historical compatibility artifacts, not as the main scientific taxonomy.

Do not state or imply that AnalogCoder-Pro performs no verification. If AnalogCoder-Pro is discussed, describe Spec2Testbench as a complementary, independent, traceable verification layer centered on compliance evidence.

## Claims Allowed on Current Evidence

The nominal paper campaign may be described as a 28-circuit canonical run in `REAL` mode with 27 `SIMULABLE_COMPLIANT` cases and 1 `SIMULABLE_NONCOMPLIANT` case, namely `p04_amplifier`. If `p04_amplifier` is cited, the failure must be stated precisely as `dc_gain_db = -160.0000000868589 dB` against `>= 0.0 dB`.

The frozen pilot V3 may be described only with its own counts: `16` cases, `8 TRUE_ACCEPT`, `8 TRUE_DETECTION`, `0 FALSE_ACCEPT`, `0 FALSE_REJECT`, and `0 UNEVALUATED`. The larger controlled-violation study may be described only with its own counts: `30` generated variants, `2` effective controlled violations, `28` ineffective mutations, `1` detected effective violation, and `1` missed effective violation.

The software-test claim should use `results/final_test_results.json` if a single canonical count is needed. Because another artifact reports a different count, the manuscript should avoid broad rhetoric such as "all tests ever run" and instead say that the canonical final test summary records `66` unique tests passing in both normal and PySpice-disabled modes.

## Claims Forbidden on Current Evidence

Do not say that the nominal 28-circuit replay is future work. It has already been executed in the canonical paper campaign.

Do not reuse the stale frozen-pilot wording from `paper_final/main.tex` that says seven compliant references plus seven controlled violations plus two WRDATA cases. The canonical frozen pilot V3 counts are 8 and 8.

Do not present the larger controlled-violation campaign as if all 30 mutations were effective. Do not present generated-mutation count as detected-violation population size.

Do not claim completed robustness, full PVT validation, industrial sign-off, post-layout realism, quantitative LLM comparison, or ablation completion. Do not use the word `certification` in a regulatory or industrial sense.

Do not present simplified voltage or temperature variations as full industrial PVT validation. Do not present the benchmark circuits as industrial circuits.

## Handling Conflicts and Legacy Artifacts

When the manuscript uses both the frozen pilot V3 and the expanded controlled-violation study, it must state clearly that these are distinct datasets with different purposes and different confusion counts. The frozen pilot cannot be merged numerically with the later expanded campaign.

If older files such as `results/controlled_violation_metrics.json`, `results/controlled_violation_results.csv`, or `results/reference_28_framework_campaign.json` are discussed, they must be labeled historical, obsolete, or legacy and must not be used as the current canonical basis for the paper.

If a table needs a result that is currently unstable or contradicted across artifacts, keep the table structure but replace the unstable cell with `TBD -- TO BE FILLED FROM CANONICAL EVIDENCE`.

## Style and LaTeX Constraints

Produce LaTeX compatible with `IEEEtran`. Keep the prose predominantly in coherent scientific paragraphs rather than bullet-heavy lists. Preserve necessary tables, but do not fabricate missing rows or summary statistics.

Do not remove important references or substantive scientific information without recording the decision in a change log. Do not modify result files or experimental artifacts during manuscript rewriting. Any section discussing limitations must preserve the current evidence boundaries on robustness, ablation, LLM comparison, and benchmark realism.
