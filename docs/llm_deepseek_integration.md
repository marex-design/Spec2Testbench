# DeepSeek integration — v0.5.0

The canonical LLM path is `HybridFeedbackLoop`: planner → deterministic validator → compiler → ngspice → extraction → deterministic SpecChecker, with bounded repair feedback for protocol/testbench failures only.

## Configuration

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
DEEPSEEK_TEMPERATURE
DEEPSEEK_TOP_P
DEEPSEEK_MAX_TOKENS
DEEPSEEK_TIMEOUT_SECONDS
DEEPSEEK_MAX_RETRIES
LLM_MODEL_RELEASE   # optional provider-published release/date; never guessed
```

## Provider preflight

```powershell
python scripts/list_deepseek_models.py
python scripts/smoke_test_deepseek_provider.py
```

## Single hybrid verification

```powershell
spec2testbench hybrid-verify `
  --specs benchmark/analogcoder_pro/specs/p10_lowpass.yaml `
  --netlist benchmark/analogcoder_pro/p10_lowpass.cir `
  --provider deepseek `
  --model $env:DEEPSEEK_MODEL `
  --temperature 0.1 `
  --top-p 1.0 `
  --max-retries 3 `
  --output results/p10_hybrid
```

## Experimental campaign

```powershell
python scripts/run_hybrid_feedback_campaign.py `
  --manifest experiments/ground_truth/ground_truth_manifest.yaml `
  --provider deepseek `
  --model $env:DEEPSEEK_MODEL `
  --temperature 0.1 `
  --top-p 1.0 `
  --trials 3 `
  --max-retries 3 `
  --output results/hybrid_ground_truth
```

The campaign saves exact model/provider configuration, prompts, payloads, JSON schema, raw responses, retries, validation history, tokens, latency, coverage, run-level and case-level confusion matrices, stability, and paired McNemar comparisons when eligible modes are present.
