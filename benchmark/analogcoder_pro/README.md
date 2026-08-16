# AnalogCoder-Pro ACP-28 benchmark adapter

This directory preserves the 28 `p01`-`p28` AnalogCoder-Pro DUT netlists used by this project and couples each DUT to one strict Spec2Testbench YAML v2 contract.

## What is preserved

- `p01_*.cir` ... `p28_*.cir`: canonical DUT netlists. The generated topology and component/device values are preserved; embedded analysis/output commands are externalized so the verifier owns the protocol.
- `upstream/problem_set.tsv`: pinned upstream task metadata snapshot, SHA-256 recorded in `acp28_manifest.yaml`.
- `specs/*.yaml`: strict v2 verification contracts generated from the task metadata and summarized official checker semantics.
- `acp28_manifest.yaml`: one-to-one mapping task → spec → DUT → SHA-256 → official checker name.

The upstream checker source is deliberately not copied into this repository. Each YAML records its checker path and a concise criterion summary for provenance.

## Why netlists are retained

The netlist is the DUT. Keeping only circuit names would make an independent conformity experiment impossible. Spec2Testbench verifies the preserved ACP-produced DUT; it does not regenerate the circuit.

## Strict conformity policy

ACP-28 uses a conservative three-state contract:

- `COMPLIANT`: all mandatory requirements have evidence and pass.
- `NONCOMPLIANT`: at least one mandatory requirement has evidence and fails.
- `NOT_EVALUATED`: evidence is incomplete and no mandatory failure has been demonstrated.

A criterion marked `metadata_only` remains visible in the contract but cannot contribute a PASS. This is intentional. Some upstream checkers mutate component values or use multi-run semantics not yet represented by the core immutable-DUT verification path. Such gaps are reported as contract implementation coverage rather than hidden.

## Validate the corpus

```powershell
spec2testbench spec-lint --specs benchmark/analogcoder_pro/specs
```

## Run deterministic ACP conformity

```powershell
$env:NGSPICE_PATH = (Get-Command ngspice_con).Source
spec2testbench acp-benchmark `
  --manifest benchmark/analogcoder_pro/acp28_manifest.yaml `
  --output results/acp28_compliance
```

Primary outputs:

- `runs.csv`: one row per ACP DUT.
- `criteria.csv`: one row per mandatory functional criterion.
- `summary.json`: aggregate rates and definitions.
- `summary.md`: human-readable report.
- `<case_id>/verification_report.json`: detailed evidence when artifacts are retained.

## Reported rates

Let `N` be all ACP DUTs, `E` the circuits with a complete PASS/FAIL decision, `P` compliant circuits, `F` noncompliant circuits, and `S` simulations that completed successfully.

- Simulation success rate = `S / N`
- Evaluation rate = `E / N`
- Compliance rate among evaluated = `P / E`
- Non-compliance rate among evaluated = `F / E`
- Verified Compliance Yield = `P / N`
- Failure-to-evaluate rate = `NOT_EVALUATED / N`

Always report evaluation rate next to compliance rate. A high conditional compliance rate with low evaluation coverage is not strong evidence.

## Rebuild the specifications

```powershell
python scripts/build_acp28_specs.py
```

This is a maintainer/reproducibility command. Normal users should use the `spec2testbench` CLI.
