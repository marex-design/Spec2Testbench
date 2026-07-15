# Evidence Conflicts

| Claim | Source A | Value A | Source B | Value B | Selected source | Reason |
|---|---|---:|---|---:|---|---|
| Frozen pilot population | `paper_final/main.tex` | 7 references + 7 violations | `results/frozen_pilot_metrics_v3.json` | 8 TRUE_ACCEPT + 8 TRUE_DETECTION | V3 JSON | machine-readable final result is newer and tied to the V3 manifest |
| Outstanding nominal replay | `paper_final/main.tex` | future work | `results/final_nominal_summary.json` | 29 specifications replayed | final JSON | execution artifact is direct evidence; manuscript wording is stale |
| Controlled campaign size | `paper_final/main.tex` | not claimed | `results/final_controlled_summary.json` | 30 candidates, 2 effective | final JSON | expanded campaign exists but must remain separate from V3 |
| Baseline evidence | `paper_final/main.tex` | not claimed | `results/final_baseline_vs_spec2testbench.csv` | 1.0 versus 0.5 FAR | final CSV | direct computed comparison exists, but denominator is only 2 |
| Robustness | `paper_final/main.tex` | future/limited study not claimed | `results/final_robustness_metrics.json` | NOT_EXECUTED | final JSON | no robustness result may be inferred |

Unresolved conflicts requiring manual confirmation: author identity and the absent codirector source document.
