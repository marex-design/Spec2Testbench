# Experimental Protocol

The paper campaign is configured by `configs/paper_experiment.yaml` and run with:

```powershell
python scripts\run_paper_campaign.py
```

The campaign uses the 28 reference netlists in `benchmark/analogcoder_pro` and
the matching specifications in `examples/benchmark_specs`. Specs without a
matching reference netlist are excluded from the nominal 28-circuit campaign.

The deterministic paper profile uses:

- `llm.enabled: false`
- `simulation.allow_mock: false`
- `simulation.allow_recovery: true`
- `simulation.timeout_seconds: 60`

Each circuit writes artifacts under `artifacts/paper_campaign/<run_id>/<circuit_id>/`.
The generated paper tables are:

- `results/paper_campaign_summary.csv`
- `results/paper_metric_results.csv`
- `results/circuit_test_matrix.csv`
- `results/simulability_vs_compliance.csv`
- `results/paper_campaign_summary.json`

Mock results are excluded by default. Any simulator failure is preserved as a
failure and must not be converted into a synthetic success.
