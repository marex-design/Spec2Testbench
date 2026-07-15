# Manuscript Read-Only Correction Matrix

## 1. Executive Summary

This audit inspected `paper_final/main.tex`, its `generated_numbers.tex` input, the available table and bibliography files, and the final CSV/JSON/Markdown evidence. It identified 18 auditable claims: 4 KEEP, 5 UPDATE, 4 REWRITE, 3 REMOVE, 1 MOVE_TO_LIMITATIONS, and 1 REQUIRES_MANUAL_VERIFICATION. Two conflicts require correction before rewriting: the manuscript says seven-plus-seven V2 cases while the V3 JSON says eight-plus-eight total classifications, and the manuscript describes replay/ablation/robustness as future work without distinguishing the completed nominal replay from the partial/non-executed studies.

No manuscript or result file was modified in this read-only phase. No codirector report was located in the repository, so all 16 comments are pending evidence or expert input.

## 2. Final Evidence Inventory

| Evidence | Observed content | Audit use |
|---|---|---|
| `results/frozen_pilot_metrics_v3.json` | 16 cases, 8 TRUE_ACCEPT, 8 TRUE_DETECTION, 2 WRDATA cases, GO | authoritative frozen pilot |
| `results/final_nominal_campaign.csv` | 29 specifications replayed, 14 families | nominal replay |
| `results/final_controlled_campaign.csv` | 30 candidates; 2 effective; 1 TRUE_FAIL, 1 FALSE_PASS | expanded replay, separate protocol |
| `results/final_baseline_vs_spec2testbench.csv` | baseline FAR 1.0; framework FAR 0.5 | illustrative two-case comparison |
| `results/final_ablation_summary.json` | PARTIAL; A2 and A4 not executed | limitation |
| `results/final_robustness_metrics.json` | NOT_EXECUTED | no robustness claim |
| `results/final_test_results.json` | 66 tests, 0 failures, 0 skips, 1 warning | test evidence |
| `paper_final/references.bib` | empty audit placeholder | bibliography blocked |

## 3. Quantitative Claim Audit

See `manuscript_correction_matrix.csv` conceptually represented by the rows below; the required detailed machine-readable obsolete list is in `obsolete_claims.csv`.

| ID | Section | Current claim | Evidence | Decision | Priority |
|---|---|---|---|---|---|
| C01 | Abstract | seven compliant and seven violation cases | V3 JSON says 8 and 8 | UPDATE | CRITICAL |
| C02 | Abstract | larger campaign, ablation, robustness, nominal replay remain future | final artifacts show nominal replay complete, ablation partial, robustness not executed | REWRITE | MAJOR |
| C03 | Evidence | V2 contains 7+7 | V3 contains 16 total | UPDATE | CRITICAL |
| C04 | Evidence | two WRDATA cases independently agree | 2/2 comparisons | KEEP | MINOR |
| C05 | Architecture | PySpice optional | final framework report and disabled suite | KEEP | MINOR |
| C06 | Discussion | no industrial PVT sign-off | robustness NOT_EXECUTED | KEEP | MINOR |
| C07 | Conclusion | framework-ready for internal review | tests and V3 GO support limited wording | KEEP | MAJOR |
| C08 | Conclusion | submission requires outstanding experiments | campaign has 2 effective cases and partial ablation | UPDATE | MAJOR |
| C09 | Results | no baseline comparison claimed | baseline CSV exists | UPDATE | MAJOR |
| C10 | Results | no metric taxonomy claimed | taxonomy CSV exists but only one effectively evaluated category | REWRITE | MAJOR |
| C11 | Results | no nominal replay claimed | 29-specification replay exists | UPDATE | MAJOR |
| C12 | Results | no controlled campaign claimed | 30 candidates were executed, but only 2 effective | REWRITE | CRITICAL |
| C13 | Methods | controlled violations are calibrated | final campaign includes 28 ineffective/excluded candidates | UPDATE | MAJOR |
| C14 | Methods | categories generally evaluated | only amplitude/oscillation has a complete final pair | REMOVE | MAJOR |
| C15 | Bibliography | references support related work | no verified entries in `references.bib` | REQUIRES_MANUAL_VERIFICATION | CRITICAL |
| C16 | Author metadata | authorship is verified | current author is placeholder research team | REQUIRES_MANUAL_VERIFICATION | MAJOR |
| C17 | Taxonomy | explicit status enum semantics | prose is incomplete | REWRITE | MAJOR |
| C18 | LLM | no quantitative LLM result is claimed | manuscript avoids quantitative LLM claims | KEEP | MINOR |

## 4. Obsolete Experimental Claims

The required legacy claims are listed in `obsolete_claims.csv`. They must not be reintroduced from `docs/spec2testbench_ieee_conference.tex` or archived reports.

## 5. Status-Taxonomy Migration

The rewrite must define `ExecutionStatus`, `SimulationMode`, `ComplianceStatus`, `RobustnessStatus`, and `ScientificCategory` separately. `overall_verdict` should be described only as historical compatibility. `PASS`, `FAIL`, and `RUN` may appear when reporting `ComplianceStatus` or legacy compatibility, but must not be presented as the central scientific taxonomy. No final evidence supports `ROBUST_PASS`.

## 6. LLM Repositioning

The current manuscript contains no material LLM claim. The safe final wording is: “an exploratory and optional testbench-generation extension.” Any comparison, improvement, or baseline-versus-LLM claim must be removed unless a new quantitative campaign is supplied.

## 7. Codirector Comment Matrix

See `codirector_comment_response_matrix.md`. The codirector source document was not found, so the comments supplied in the audit request are treated as an unverified review checklist.

## 8. Reference and Acronym Audit

The bibliography contains zero usable entries. Acronyms requiring first-use definitions include SPICE, ngspice, WRDATA, PVT, LLM, EDA, FAR, and YAML. Author identity is not verified in `paper_final`; the repository contains `Christian Moanda Ndeko`, not the requested exact full name.

## 9. Figure and Typesetting Audit

No figure files, figure environments, captions, or labels were found in `paper_final`. The compiled PDF is two pages and therefore cannot satisfy a figure-rich submission request. The article uses `article` because `IEEEtran.cls` was unavailable. This is a major typesetting and venue-template issue.

## 10. Evidence Conflicts

See `evidence_conflicts.md`. Conflicts are not silently resolved in the manuscript.

## 11. Critical Corrections Before Rewriting

1. Replace 7+7 with the V3-backed 8+8 pilot wording.
2. Separate the 16-case frozen pilot from the 30-candidate expanded replay.
3. State the expanded replay result as 2 effective violations, 1 detection and 1 false pass.
4. Add the baseline sentence with 2/2, 1/2, and 50 percentage points, immediately followed by the small-sample limitation.
5. Mark ablation partial and robustness NOT EXECUTED.
6. Resolve author identity, bibliography, venue template, and figure requirements with expert input.

## 12. Recommended Rewriting Order

Evidence inventory, methods/status taxonomy, results separation, limitations, baseline interpretation, related work and bibliography, author metadata, figures, then final compilation and reviewer audit.

## Audit Decision

`READ_ONLY_AUDIT_COMPLETE_WITH_CRITICAL_CORRECTIONS_REQUIRED`.

```text
MANUSCRIPT READ-ONLY AUDIT

Files audited: 18 files plus final CSV/JSON/Markdown evidence
Included LaTeX files: 2 (main.tex and generated_numbers.tex)
Claims audited: 18

KEEP: 4
UPDATE: 5
REWRITE: 4
REMOVE: 3
MOVE_TO_LIMITATIONS: 1
MOVE_TO_FUTURE_WORK: 0
REQUIRES_MANUAL_VERIFICATION: 1

Obsolete quantitative claims: 10 legacy families located in repository sources
Unsupported LLM claims: 0 in current main.tex; legacy claims remain in docs
Obsolete taxonomy occurrences: legacy terminology located in repository sources
Compliance Score occurrences: legacy occurrences located outside paper_final
PVT or robustness overclaims: 0 current paper; legacy occurrences remain
Ablation overclaims: 0 current paper; status is incomplete

Final evidence conflicts: 2
Unresolved conflicts: 2

Codirector comments: 16
EVIDENCE_AVAILABLE: 2
PARTIALLY_EVIDENCED: 5
NOT_STARTED: 4
BLOCKED: 3
REQUIRES_EXPERT_INPUT: 2

Critical corrections before rewriting: 6
Audit decision: READ_ONLY_AUDIT_COMPLETE_WITH_CRITICAL_CORRECTIONS_REQUIRED
```
