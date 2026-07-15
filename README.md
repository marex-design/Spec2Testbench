# Spec2Testbench

Spec2Testbench is a Python framework that translates structured analog-circuit specifications into SPICE testbenches, executes ngspice, extracts traceable metrics, checks specification thresholds, and reports execution, compliance, robustness scope, and scientific eligibility as distinct outcomes.

The framework supports a deterministic generation path for reproducible campaigns and an optional LLM-assisted path. The final compliance decision remains deterministic: an LLM may propose an analysis, stimulus, testbench formulation, or measurement, but it does not modify benchmark circuits, specifications, thresholds, parsers, result backends, checkers, or final verdicts during evaluation.

## Repository map

- `spec2testbench/`: framework source code.
- `tests/`: unit, integration, ngspice, and evidence-integrity tests.
- `benchmark/analogcoder_pro/`: 28 pedagogical benchmark-aligned netlists.
- `examples/benchmark_specs/`: YAML specifications used by the ACP-28 campaign.
- `experiments/`: controlled-violation manifests and frozen experiment definitions.
- `artifacts/paper_campaign/20260711_094959/`: canonical nominal campaign evidence.
- `paper_final/`: evidence ledger, revised manuscript, tables, and reference audit.
- `scripts/`: reproducibility, campaign, validation, and reporting utilities.

The ACP-28 netlists are educational benchmark-aligned circuits using simplified device models. They are not industrial, post-layout, or full process-voltage-temperature validation circuits.

## Requirements

- Python 3.10 or newer.
- A working ngspice executable for real simulations.
- PySpice only for workflows that explicitly use its optional parsing interface.
- Provider-specific Python packages and API credentials only for optional LLM-assisted workflows.

## Installation

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e .
```

Install optional development and simulator integrations when required:

```bash
python -m pip install -e ".[dev,pyspice,llm]"
```

## Deterministic verification

```bash
spec2testbench verify \
  --specs examples/benchmark_specs/p01_amplifier.yaml \
  --netlist benchmark/analogcoder_pro/p01_amplifier.cir \
  --no-llm
```

Run the automated suite:

```bash
python -m pytest
```

Tests marked `ngspice` require a local ngspice installation. LLM-provider availability must not be interpreted as circuit success or failure.

## Reproducing the paper campaign

The canonical evidence used by the manuscript is identified in `paper_final/canonical_evidence_ledger.csv`. A new campaign can be launched with:

```bash
python scripts/run_paper_campaign.py
```

This creates a new timestamped directory and must not overwrite the canonical run. See `REPRO.md` for the evidence-preserving workflow and backend validation commands.

## Scientific scope

Spec2Testbench is positioned as a complementary verification layer downstream of circuit generation and optimization. AnalogCoder-Pro performs structural, operating-point, DC-sweep, functional, and multimodal checks during its own generation and optimization workflow; Spec2Testbench adds independent, specification-centered evidence and provenance.

Mock execution is useful for software development but is not scientifically eligible. Missing measurements are reported as not evaluated rather than replaced by synthetic values. Simplified voltage and temperature checks are not presented as full industrial PVT validation.

## Citation and license

Citation metadata is available in `CITATION.cff`. Spec2Testbench is distributed under the MIT License; see `LICENSE`.

Authors:

- Exauce Kambale Maruba (`exauce.kambale@unikin.ac.cd`)
- Christian-Marie Moanda Ndeko Mosengo (`christianmoanda@yahoo.fr`)
