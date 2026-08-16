# Controlled hybrid LLM–SPICE feedback architecture

## Scientific boundary

The verification core is a controlled loop:

`Specification + immutable DUT -> Inspector -> LLM planner -> deterministic validator -> compiler -> ngspice -> extractor -> deterministic SpecChecker`.

Only protocol/testbench failures may be returned to the LLM for repair. A successful SPICE execution that produces a deterministic specification `FAIL` is terminal. The core must not mutate component values or close the design automatically.

## Retry semantics

`MAX_RETRIES = 3` is the default shared repair budget. It counts LLM repair calls after the initial plan call. Provider transport retries (rate limit, timeout, transient HTTP errors) are separate and are recorded by the provider adapter.

Retryable classes:

- invalid JSON/schema/plan;
- unknown node or incompatible analysis;
- compilation failure;
- ngspice protocol/testbench failure when the simulator itself is available;
- missing/failed metric extraction.

Terminal classes:

- electrical non-conformity after successful simulation;
- DUT hash mutation;
- specification/threshold mutation;
- missing ngspice installation / permission failure;
- exhausted repair budget.

## Invariants

1. **No LLM verdict.** PASS/FAIL is emitted only by `SpecChecker` from measured values and immutable requirements.
2. **No synthetic measurement.** The plan may describe how to measure, but the accepted metric source is an ngspice measurement/vector backend.
3. **Immutable user thresholds.** A hash of `performance_targets` is checked throughout the loop.
4. **Immutable DUT.** SHA-256 is computed before planning and after every repair/execution boundary.
5. **No invented nodes.** Every observed/measurement/stimulus node must be present in the deterministic netlist inventory or explicit specification port set.
6. **Analysis whitelist.** The current executable LLM-plan schema accepts `OP`, `DC`, `AC`, and `TRAN`. Unsupported analysis requests are rejected rather than guessed. Frequency-domain post-processing such as FFT is not claimed as supported by this planner until a dedicated compiler/backend is implemented.
7. **Finite retry budget.** No uncontrolled agent loop is permitted.

## Evidence emitted per run

A hybrid evidence record contains provider/model, prompt hash, sampling parameters in the request configuration, provider call history, token usage, latency, validation failures, feedback categories, repair count, execution status, measurement status, DUT/spec/threshold hashes and final deterministic compliance status.

## Evaluation modes

Use at least these modes in the experimental section:

- **Deterministic**: no LLM.
- **LLM one-shot**: one LLM plan, deterministic safety gate, no repair.
- **Hybrid validated + feedback**: LLM plan, deterministic validation and bounded SPICE/extraction feedback repair.

For mutations with an independent ground-truth label, report TP/TN/FP/FN, false-accept rate and false-reject rate. For the corpus, report `Cov_circuits`, `Cov_metrics`, and `Cov_analyses`. Stub-provider results are software-integration evidence only, never scientific evidence of an LLM.

## Role validation

Node existence alone is insufficient. The validator also checks declared signal roles: a measurement input must use a declared input-role node when that metric requires an input, a measurement output must use a declared output-role node when required, and signal stimuli may not silently target an output node. Violations are reported as `ROLE_MISMATCH` and may be returned to the LLM within the shared repair budget.

## Raw-LLM safety baseline

The campaign includes `llm_raw_diagnostic`: one raw plan with no deterministic-plan hint and no repair. The response is validated and its error profile is measured, but it is never allowed to execute before the deterministic gate. This makes a non-controlled LLM comparison measurable without allowing unsafe arbitrary SPICE execution.
