# Reproducing Spec2Testbench evidence

This guide separates software validation from scientific campaign reproduction. Running unit tests demonstrates software behavior; it does not by itself establish analog-circuit compliance.

## 1. Environment

Use Python 3.10 or newer and install ngspice separately so that `ngspice`, `ngspice.exe`, or `ngspice_con.exe` is available to the framework.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

PySpice is optional for native ngspice measurement workflows:

```bash
python -m pip install -e ".[pyspice]"
```

## 2. Software validation

```bash
python -m pytest
```

To isolate tests that require ngspice:

```bash
python -m pytest -m ngspice
```

The canonical software-test count used by the manuscript must be read from `results/final_test_results.json`, not inferred from a new local run.

## 3. Nominal ACP-28 campaign

```bash
python scripts/run_paper_campaign.py
```

The script reads `examples/benchmark_specs/` and `benchmark/analogcoder_pro/`, writes summary files under `results/`, and creates a timestamped evidence tree under `artifacts/paper_campaign/`. A newly generated run is a new campaign; it does not silently replace the canonical run `20260711_094959`.

Canonical manuscript values and exact evidence locations are listed in:

- `paper_final/canonical_evidence_ledger.csv`
- `paper_final/canonical_results_summary.md`
- `paper_final/final_claim_evidence_matrix.csv`

## 4. Native result backends

The backend validation suite is:

```bash
python -m pytest tests/test_ngspice_result_backends.py
python scripts/validate_ngspice_native_extraction.py
python scripts/validate_wrdata_metrics_independently.py
```

These checks validate the `NGSPICE_MEASURE` and `NGSPICE_WRDATA` extraction paths. Their outputs are software/backend evidence and must not be presented as direct proof that every analog circuit is compliant.

## 5. Controlled violations

Controlled cases and their expected mutations are frozen under `experiments/`. Campaign results must distinguish generated mutations from mutations that actually changed the measured behavior. The canonical and conflicting campaign records are documented in `paper_final/canonical_results_summary.md`; do not combine their confusion matrices.

## 6. Evidence preservation

Do not edit files under `results/` or `artifacts/` to make them agree with a manuscript claim. Generate a new timestamped campaign instead. Raw ngspice waveforms are intentionally ignored by Git because of their size; compact canonical CSV, JSON, Markdown, logs, provenance, and campaign decks are the publication evidence.
