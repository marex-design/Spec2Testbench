# Spec2TestBench

Spec2TestBench is a Python framework for analog verification from YAML specifications to SPICE testbenches, ngspice simulation, metric extraction, and report generation.

The project supports two execution modes:

- `--no-llm`: deterministic template-based generation for reproducible baseline campaigns
- optional LLM-assisted generation: alternative testbench synthesis through supported providers

## What The Framework Does

Given:

- a SPICE netlist
- a YAML specification with expected metrics and limits

the framework can:

- generate a compatible testbench
- run ngspice analyses
- extract DC, AC, transient, oscillator, and spectral metrics
- compare results against the specification
- emit a verification verdict and a report
- draw a schematic from the netlist

## Current Scope

The active benchmark in this repository is centered on the `AnalogCoder-Pro` 28-circuit set stored under [benchmark](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/benchmark).

Current repository organization:

- `benchmark/analogcoder_pro`: reference benchmark netlists
- `benchmark/industrial`: industrial-style benchmark scaffold for future extension
- `examples/benchmark_specs`: YAML specifications aligned with the active benchmark
- `spec2testbench`: framework source code
- `scripts`: benchmark generation, campaign, reporting, and utility scripts
- `docs`: paper sources and supporting writing material
- `results`: generated campaign outputs
- `testbenches/benchmark`: generated reference testbenches when campaigns are run

## Installation

```bash
pip install -e .
```

Optional dependencies commonly used in this project:

```bash
pip install openai schemdraw
```

You also need a working `ngspice` installation available from the execution environment.

## LLM Configuration

Supported providers in the current codebase:

- `openai`
- `deepseek`
- `groq`
- `gemini`
- `anthropic`

Typical PowerShell setup:

```powershell
$env:LLM_PROVIDER="deepseek"
$env:DEEPSEEK_API_KEY="your_key"
```

## CLI Commands

```bash
spec2testbench verify --specs examples/benchmark_specs/p01.yaml --netlist benchmark/analogcoder_pro/p01.cir --no-llm
spec2testbench generate --specs examples/benchmark_specs/p01.yaml
spec2testbench diagnose --waveform path/to/waveform.png
spec2testbench draw --netlist benchmark/analogcoder_pro/p01.cir --output results/p01.png
spec2testbench config
spec2testbench providers
```

## Benchmark Campaign Scripts

Baseline framework campaign on the 28 reference circuits:

```bash
python scripts/run_reference_28_framework_campaign.py
```

LLM vs baseline comparison:

```bash
python scripts/run_llm_mode_comparison.py
```

Paper-ready benchmark table generation:

```bash
python scripts/generate_reference_28_paper_table.py
```

## Outputs

Typical generated artifacts:

- CSV summaries
- JSON result dumps
- Markdown verification reports
- schematic images

Most outputs are written under `results/`.

## Notes For The Paper

At this stage, the framework is strongest on:

- reproducible non-LLM verification
- benchmark-aligned YAML-to-testbench generation
- automatic metric extraction and verdicting
- paper-ready result aggregation

The optional LLM path is integrated, but should be presented carefully in the paper unless a stable multi-model evaluation is included.

## License

MIT License

## Authors

- Exauce Kambale Maruba - `exauce.kambale@unikin.ac.cd`
- Christian Moanda Ndeko - `christianmoanda@yahoo.fr`
