# Hybrid LLM–SPICE experimental protocol

This directory is the executable protocol for evaluating the controlled feedback architecture. It deliberately separates **coverage**, **ground truth**, **raw LLM diagnostics**, **one-shot planning**, and **hybrid feedback** so that one source of evidence is not reused as another.

## Experimental modes

`run_hybrid_feedback_campaign.py` supports four modes:

1. `deterministic` — no LLM.
2. `llm_raw_diagnostic` — one raw LLM plan, no deterministic-plan hint, no repair, and **no execution**. This is the safe diagnostic proxy for an uncontrolled LLM baseline; it measures JSON/schema/node/role/analysis/measurement errors without allowing an unvalidated plan to reach SPICE.
3. `llm_one_shot` — one LLM plan, deterministic safety gate, no feedback repair.
4. `hybrid` — LLM plan + deterministic validation + compiler + ngspice + extraction feedback, with a bounded shared repair budget.

An electrically valid simulation that fails a user requirement is terminal. It is never sent to the LLM as a request to redesign the DUT.

## Campaign A — ACP-28 coverage

Use `acp28_manifest.yaml`. It contains exactly the 28 benchmark specification/netlist pairs and is marked `coverage_only: true`.

```bash
python scripts/run_hybrid_feedback_campaign.py \
  --manifest experiments/hybrid_feedback/acp28_manifest.yaml \
  --provider deepseek \
  --model <exact-provider-model-id> \
  --model-release <provider-published-version-or-date> \
  --trials 3 \
  --max-retries 3 \
  --output results/hybrid_feedback_acp28
```

Report `Cov_circuits`, `Cov_metrics`, and `Cov_analyses`. Do not manufacture confusion labels for ACP-28 cases that do not have an independent oracle.

## Campaign B — independent ground truth and mutations

Use `experiments/ground_truth/ground_truth_manifest.yaml`. It contains compliant, non-compliant, non-simulable, and uncertain records with pre-execution independent references. Uncertain records are excluded from principal confusion metrics.

```bash
python scripts/run_hybrid_feedback_campaign.py \
  --manifest experiments/ground_truth/ground_truth_manifest.yaml \
  --provider deepseek \
  --model <exact-provider-model-id> \
  --model-release <provider-published-version-or-date> \
  --trials 3 \
  --max-retries 3 \
  --output results/hybrid_feedback_ground_truth
```

Report TP/TN/FP/FN, accuracy, false-accept rate, false-reject rate, initial JSON-valid rate, initial plan-rejection rate, final plan-rejection rate, executable-plan rate, feedback-recovery rate, node/role/analysis/measurement error rates, token count, latency, provider transport retries, and inter-run stability.

## Independent manual oracle subset

`../manual_oracle_subset/` contains manually authored `.ckt` decks for p10/p11 and controlled violations. Their expected cutoff frequency comes from `fc = 1/(2*pi*R*C)`, not from Spec2Testbench. The subset provides an auditable non-circular oracle for representative PASS and FAIL cases.

## Controlled LLM-like fault injection

```bash
python scripts/run_llm_fault_catalog.py \
  --output scientific_evidence/hybrid_feedback_revision/controlled_fault_catalog.json
```

This campaign verifies that deterministic guards reject deliberately injected faults. It **must not** be reported as the spontaneous hallucination rate of a live model.

## Reproducibility metadata

Every LLM run writes the request payload, complete system prompt, raw response, plan validation, provider call history, prompt hash, tokens, latency and — for hybrid/one-shot execution — the complete hybrid evidence record. The campaign summary records provider, exact configured model, optional provider-published model release, temperature, token limit, timeout, LLM repair budget and provider transport retry budget.

`top_p` is currently not set by the adapter and is recorded as such rather than guessed. Monetary cost is not inferred from token counts because provider pricing is external and time-varying; token counts are the canonical cost evidence stored by this framework.

## Environment gate

Scientific execution requires both:

- a real ngspice executable (`NGSPICE_PATH` may be used), and
- a real provider credential (`DEEPSEEK_API_KEY`) for live LLM evidence.

Stub runs are integration tests only and are tagged `scientific_llm_evidence: false`.
