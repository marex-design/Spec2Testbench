# Final implementation audit — Spec2Testbench v0.5.0

This document separates **implemented code**, **locally tested behavior**, and **external experimental evidence still requiring ngspice/DeepSeek**. No missing live experiment is relabelled as completed.

## A. Blocking weaknesses

| # | Weakness | v0.5.0 status | What is actually present | Remaining evidence/work |
|---|---|---|---|---|
| 1 | No real LLM → SPICE → feedback → LLM loop | **IMPLEMENTED / UNIT-TESTED** | `HybridFeedbackLoop`; validation, compilation, simulation and extraction failures can produce bounded LLM repair feedback | Real provider + real ngspice campaign still required |
| 2 | LLM mostly optional | **EXPERIMENT DRIVER READY, LIVE EVIDENCE PENDING** | `hybrid-verify`; hybrid campaign with LIVE provider flag | Run at least one complete DeepSeek campaign locally |
| 3 | Final proofs deterministic only | **LIVE EVIDENCE PENDING** | Evidence capture for every LLM call/plan/retry exists | Produce and freeze real DeepSeek evidence |
| 4 | No quantified LLM benefit | **IMPLEMENTED, RESULT PENDING** | Deterministic, raw diagnostic LLM, one-shot validated LLM and hybrid modes; deltas, case-level confusion, McNemar | Run identical cases with live model |
| 5 | No formal retry | **IMPLEMENTED / TESTED** | shared repair budget, default `MAX_RETRIES=3`; retryable categories explicitly enumerated; provider retries separated | None in code |
| 6 | No hallucination/error demonstration | **CONTROLLED GUARDS TESTED; LIVE RATE PENDING** | 10 injected LLM-like faults, 10/10 detected locally | Spontaneous live-model rates require live trials |
| 7 | ACP-28 claimed but not fully demonstrated | **PARTIAL** | 28 DUTs, 28 strict specs, ACP runner, strict NOT_EVALUATED semantics | Real 28-DUT run required; only 36/64 mandatory ACP criteria are currently executable |
| 8 | Coverage indicators not reported | **IMPLEMENTED** | `Cov_circuits`, `Cov_metrics`, `Cov_analyses` in hybrid and ACP aggregation | Populate values from real run |
| 9 | Weak baselines | **IMPLEMENTED, RESULT PENDING** | deterministic, LLM raw diagnostic, LLM one-shot + deterministic gate, hybrid feedback | Freeze comparable live results |
| 10 | No independent oracle | **IMPLEMENTED** | manual p10/p11 `.ckt` oracle + analytical `fc=1/(2πRC)` verdicts | Expand oracle if thesis requires stronger external validity |
| 11 | No false accept/reject measurement | **IMPLEMENTED, LIVE VALUES PENDING** | primary compliant/non-compliant oracle, materialized mutations, TP/TN/FP/FN, FAR/FRR, 95% Wilson CIs, case-level majority | Run ngspice on oracle/campaign |
| 12 | “Hybrid” asserted more than demonstrated | **ARCHITECTURE IMPLEMENTED; DEMONSTRATION PENDING** | LLM is visible in planning, validation rejection, repair, cost and stability evidence | The thesis must include real LLM ON results |

## D. Scientific invariants

| Invariant | Status | Enforcement |
|---|---|---|
| LLM never decides PASS/FAIL | **Implemented/tested** | plan schema + verdict-leakage guard; `SpecChecker` remains deterministic |
| LLM never creates a measured value | **Implemented** | plan carries measurement recipes, not measured values; final metrics come from ngspice extraction |
| LLM cannot change user thresholds | **Implemented/tested** | strict schema + threshold SHA-256 before/after |
| DUT immutable | **Implemented/tested** | SHA-256 before/after; mutation causes terminal invariant failure |
| No invented node | **Implemented/tested** | NetlistInspector/capability nodes + deterministic validator |
| Analysis whitelist | **Implemented** | LLM executable plan whitelist is OP/DC/AC/TRAN. FFT is deterministic post-processing of transient vectors rather than an independently LLM-selected simulator analysis. |
| Retry count bounded | **Implemented/tested** | default 3; >10 blocked by safety policy |
| Electrical FAIL is terminal | **Implemented/tested** | FAIL is not sent to the LLM as a design-repair request |

## H. LLM evaluation telemetry

| Item | Status |
|---|---|
| LLM call count | implemented |
| exact provider/model | implemented |
| provider-published model release/date | optional recorded field; never guessed |
| temperature | implemented |
| top_p | **implemented in v0.5.0** |
| system prompt | saved |
| user payload/context | saved |
| expected JSON schema | saved in payload/schema |
| protocol repair count | implemented |
| provider transport retry count | implemented separately |
| initial JSON-valid rate | implemented |
| initial/final plan rejection rate | implemented |
| executable-plan rate | implemented |
| invented-node rate | implemented |
| role-mismatch rate | implemented |
| analysis-mismatch rate | implemented |
| invalid-stimulus rate | implemented |
| invalid-measurement rate | implemented |
| recovery-after-feedback rate | implemented |
| prompt/completion/total tokens | implemented |
| latency | implemented |
| inter-run stability | implemented |
| model-to-model comparison | `scripts/compare_llm_models.py` |
| deterministic planner comparison | implemented in campaign |
| less-controlled LLM comparison | `llm_raw_diagnostic`; never executed without safety gate |
| run-level confusion | implemented |
| case-level majority confusion | **implemented in v0.5.0** |
| confidence intervals | **Wilson 95% implemented in v0.5.0** |
| paired significance | **exact McNemar implemented in v0.5.0** |

## ACP-28 contract completeness

- DUTs retained: **28/28**.
- Uniform v2 YAMLs: **28/28**.
- Mandatory ACP criteria encoded: **64/64**.
- Mandatory criteria executable by the current core: **36/64**.
- Mandatory criteria explicitly retained as `metadata_only`: **28/64**.
- Circuits with a completely executable mandatory contract: **12/28**.

The strict runner never converts a missing mandatory criterion into PASS. Therefore a real ACP run may legitimately contain `NOT_EVALUATED` until specialized procedures for MOS drain-current inspection, multi-condition op-amp gain, mixer IF products, adder/subtractor grids, and related criteria are implemented and validated.


## Canonical specification source

All retained ACP workflows now consume the same strict YAML v2 files under `benchmark/analogcoder_pro/specs/`. The legacy duplicate `examples/benchmark_specs/` corpus has been removed. CLI verification, hybrid planning, ACP aggregation, the primary oracle and materialized mutations therefore no longer select different specification dialects for the same DUT.

## Final local validation

- Full pytest suite in the audit environment: **273 passed, 23 skipped, 0 failed**.
- Non-external subset: **273 passed, 1 skipped, 22 deselected**.
- ACP YAML lint: **28/28 valid**, mean mandatory-contract implementation coverage **59.5%**.
- Controlled LLM-like fault catalog: **10/10 detected**.
- Materialized active-DUT controlled violations: **26**.
- CLI entry point: `spec2testbench version` reports **v0.5.0**.
- Environment limitation: ngspice and a live DeepSeek API key were unavailable; those tests are skipped rather than misreported as framework failures.

## Primary oracle vs extended mutations

The primary confusion-matrix manifest contains the independent p10/p11 analytical oracle. The broader controlled set contains 26 active-line mutations for stress testing. Four legacy mutations that only targeted provenance comments after DUT canonicalization were removed in v0.5.0. Every retained mutation has distinct original/mutated SHA-256 evidence and an active-line effectiveness check.

## Final package cleanliness

The final package is deliberately restricted to the Spec2Testbench core and the AnalogCoder-Pro research assets required to reproduce the thesis experiments. `benchmark/` contains only `analogcoder_pro/`; generated `output/`, `reports/`, `results/`, Python caches, editable-install metadata, old frozen/live campaigns and the former secondary benchmark are excluded. A package-contract test enforces the 28 DUTs, 28 canonical v2 specs, absence of the legacy spec dialect, resolvable ground-truth paths and version `0.5.0`.

The v0.5.0 package was derived from the user-supplied v0.4.0 archive whose SHA-256 is `b0e8dbf44991fc1ece04c0de7fe1538638732f4cac8e62edf7e34ed7a2be9631`.

## Definition of “done” for the thesis

The software architecture is ready for the requested experiments, but the scientific evaluation is **not done** until a machine with ngspice and the exact live DeepSeek model produces and freezes:

1. the complete deterministic ACP-28 run;
2. the ground-truth/oracle confusion run;
3. at least three live trials for one-shot and hybrid modes on the same eligible cases;
4. prompt/model/sampling/token/latency evidence;
5. the resulting coverage, confusion, recovery, stability and baseline tables.
