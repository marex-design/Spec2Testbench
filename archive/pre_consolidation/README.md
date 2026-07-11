# Pre-Consolidation Artifacts

This directory contains result and report artifacts generated before the
scientific-status consolidation phase.

They must not be used as paper evidence because they may mix legacy verdict
semantics, mock fallback behavior, outdated pytest snapshots, exploratory LLM
runs, and campaign outputs that were not produced under the
`configs/paper_experiment.yaml` policy.

New paper-eligible campaign outputs are generated separately under:

- `artifacts/paper_campaign/<run_id>/`
- `results/paper_campaign_summary.csv`
- `results/paper_metric_results.csv`
- `results/circuit_test_matrix.csv`
- `results/simulability_vs_compliance.csv`
- `results/paper_campaign_summary.json`
