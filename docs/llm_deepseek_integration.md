# LLM DeepSeek Integration

Date: 2026-07-21

This integration adds a provider-agnostic LLM planning path that turns a structured specification and netlist-derived capability payload into a validated `TestbenchPlan`, then compiles that plan deterministically into ngspice-ready SPICE.

Core commands:

```bash
python scripts/list_deepseek_models.py
python scripts/smoke_test_deepseek_provider.py --provider stub --model deepseek-stub-v1
python scripts/run_deepseek_testbench_campaign.py \
  --manifest experiments/llm_deepseek/use_case_smoke_manifest.yaml \
  --provider stub \
  --model deepseek-stub-v1 \
  --temperature 0.1 \
  --max-tokens 512 \
  --timeout 60 \
  --trials 1 \
  --modes deterministic,deepseek_refinement \
  --disable-pyspice \
  --no-mock \
  --output-run-id stub_use_case_smoke_20260721
```

Environment variables:

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
DEEPSEEK_TEMPERATURE
DEEPSEEK_MAX_TOKENS
DEEPSEEK_TIMEOUT_SECONDS
DEEPSEEK_MAX_RETRIES
```

Current local state on 2026-07-21: `DEEPSEEK_API_KEY` is absent. The repository therefore contains stub-backed campaign evidence and the exact live commands that still need to be run once credentials are available.
