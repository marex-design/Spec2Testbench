# LLM Experiment Protocol

Stage order:

1. Audit the existing LLM architecture.
2. Run unit and integration tests.
3. Run the provider smoke test.
4. Run the explicit seven-use-case smoke campaign.
5. Run the explicit frozen pilot campaign.
6. Generate aggregate CSVs, use-case reports, and reviewer-facing analyses.

Recommended live sequence:

```bash
RUN_NGSPICE_INTEGRATION=1 pytest -q
SPEC2TESTBENCH_DISABLE_PYSPICE=1 RUN_NGSPICE_INTEGRATION=1 pytest -q
RUN_LLM_LIVE=1 SPEC2TESTBENCH_DISABLE_PYSPICE=1 pytest -m llm_live -vv --tb=long
python scripts/list_deepseek_models.py
python scripts/smoke_test_deepseek_provider.py --provider deepseek --model "$env:DEEPSEEK_MODEL"
python scripts/run_deepseek_testbench_campaign.py --manifest experiments/llm_deepseek/use_case_smoke_manifest.yaml --provider deepseek --model "$env:DEEPSEEK_MODEL" --temperature 0.1 --max-tokens 4096 --timeout 90 --trials 1 --modes deterministic,deepseek_refinement --disable-pyspice --no-mock --output-run-id live_use_case_smoke_20260721
python scripts/run_deepseek_testbench_campaign.py --manifest experiments/llm_deepseek/frozen_manifest.yaml --provider deepseek --model "$env:DEEPSEEK_MODEL" --temperature 0.1 --max-tokens 4096 --timeout 90 --trials 3 --modes deterministic,deepseek_refinement --disable-pyspice --no-mock --output-run-id live_frozen_20260721
```

The frozen pilot manifest now expands to 16 explicit cases: 14 from frozen_pilot_v2 plus 2 WRDATA extension mirrors from frozen_pilot_v3.
