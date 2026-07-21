# Phase 1 - Repository Inventory

## Scope

This inventory is based on direct code and artifact inspection of the repository on 2026-07-17. I stayed read-only on existing source, tests, specs, netlists, results, reports, and manuscript files.

## Top-level structure

- `spec2testbench/`: primary Python package.
- `scripts/`: experiment launchers, validation utilities, reporting builders, and one-off repository tooling.
- `tests/`: software tests plus one real-ngspice integration suite.
- `examples/benchmark_specs/`: ACP-28-style YAML specifications used by campaigns and tests.
- `benchmark/analogcoder_pro/`: benchmark SPICE netlists and manifest.
- `benchmark/industrial/`: industrial Sky130 subset with specs, netlists, and model include.
- `artifacts/`, `results/`, `reports/`: generated evidence and campaign outputs.
- `testbenches/benchmark/`: pre-generated benchmark testbench examples.
- `paper_final/`: manuscript, evidence tables, and publication support files.

## Executable entrypoints

- `spec2testbench/presentation/cli/main.py`
  - Responsibility: user-facing CLI with `verify`, `generate`, `diagnose`, `draw`, `version`, `config`, `providers`.
  - Main functions: `verify()`, `generate()`, `diagnose()`, `draw()`, `run()`.
  - Inputs: YAML spec path, optional netlist, output paths, provider flags.
  - Outputs: `VerificationReport`, generated markdown/json reports, printed console status.
  - Depends on: `VerificationPipeline`, `Specification`, `LLMClient`, `ReportFormatter`, schematic infrastructure.
  - Called by: Typer CLI and `python -m`-style execution.

- `scripts/run_paper_campaign.py`
  - Responsibility: canonical ACP-28 campaign runner and artifact writer.
  - Inputs: `examples/benchmark_specs/*.yaml`, `benchmark/analogcoder_pro/*.cir`.
  - Outputs: per-circuit artifact folders, `results/paper_campaign_summary.json`, CSV summaries.
  - Depends on: `VerificationPipeline`, `ReportFormatter`.
  - Called by: manual script execution.

- Other important script entrypoints:
  - `scripts/run_reference_28_campaign.py`
  - `scripts/run_reference_28_framework_campaign.py`
  - `scripts/run_controlled_violation_campaign_v2.py`
  - `scripts/run_industrial_sky130_campaign.py`
  - `scripts/generate_full_ngspice_native_validation.py`
  - `scripts/validate_ngspice_native_extraction.py`
  - Architectural role: experiment orchestration and evidence production, not reusable domain core.

## Python packages and modules

### `spec2testbench.application`

- `application/usecases/run_verification.py`
  - Real orchestration center of the framework.
  - Main classes: `VerificationPipeline`, `VerificationReport`, `MetricTrace`.
  - Inputs: `Specification`, optional netlist path, optional precomputed simulation results.
  - Outputs: fully populated `VerificationReport` including statuses, metric traces, provenance, eligibility.
  - Depends on: domain entities/status objects, `TestBenchGenerator`, `SpecChecker`, waveform checker, `PySpiceSimulator`, config.
  - Called by: CLI, scripts, tests.

### `spec2testbench.domain`

- `domain/entities/specification.py`
  - Responsibility: YAML/text/dict representation of structured verification intent.
  - Main classes: `Specification`, `VariantOverride`, `TemperatureRange`, `ProcessCorner`.
  - Inputs: YAML or dict.
  - Outputs: normalized in-memory specification object.
  - Called by: CLI, pipeline, tests.

- `domain/entities/testbench.py`
  - Responsibility: executable verification plan abstraction.
  - Main classes: `TestBench`, `Stimulus`, `AnalysisConfig`, `Measurement`, `AnalysisType`, `SweepType`.
  - Inputs: generated planning data.
  - Outputs: SPICE deck text and PySpice code.
  - Called by: `TestBenchGenerator`, simulator, scripts, tests.

- `domain/interfaces/*.py`
  - Responsibility: abstract ports for simulator, checker, generator, waveform analyzer.
  - Architectural role: intended Clean Architecture boundary, though not every caller depends purely on interfaces.

- `domain/value_objects/scientific_status.py`
  - Responsibility: scientific/reporting statuses.
  - Main enums: `ExecutionStatus`, `SimulationMode`, `ComplianceStatus`, `NetlistBindingStatus`, `MutationEffectivenessStatus`, `RobustnessStatus`, `ScientificCategory`.

- `domain/value_objects/verdict.py`
  - Responsibility: metric-level and run-level verdict semantics.
  - Main types: `Verdict`, `ValidationStatus`, `CheckResult`.

- `domain/registry/*`
  - Responsibility: supported circuit/test registries and benchmark knowledge.
  - Architectural role: static knowledge/configuration layer consumed mainly by tests and higher-level tooling.

### `spec2testbench.infrastructure`

- `infrastructure/testbench/testbench_generator.py`
  - Responsibility: deterministic or LLM-assisted generation of `TestBench`.
  - Main class: `TestBenchGenerator`.
  - Inputs: `Specification`.
  - Outputs: merged multi-category `TestBench`.
  - Called by: pipeline and CLI.

- `infrastructure/testbench/prompts/testbench_prompts.py`
  - Responsibility: prompt construction for LLM generation/extraction.
  - Architectural role: adapter for remote LLM provider usage.

- `infrastructure/simulator/pyspice_simulator.py`
  - Responsibility: actual ngspice execution path used by the pipeline.
  - Inputs: netlist path, `TestBench`.
  - Outputs: structured simulation result dict with logs, backend info, raw artifact references, native metrics, statuses.
  - Called by: `VerificationPipeline`.

- `infrastructure/simulator/result_backends.py`
  - Responsibility: native metric backend abstraction and implementations.
  - Main classes: `SimulationResultBackend`, `NgspiceMeasureBackend`, `NgspiceWrdataBackend`, `PySpiceResultBackend`.
  - Called by: simulator layer and tests.

- `infrastructure/simulator/ngspice_simulator.py`
  - Responsibility: older/minimal direct wrapper around ngspice.
  - Architectural role: not the main runtime path for the canonical pipeline.

- `infrastructure/spec_checker/spec_checker.py`
  - Responsibility: specification checking and unit-aware verdict assignment.
  - Main class: `SpecChecker`.
  - Inputs: simulation results plus `Specification`.
  - Outputs: `CheckResult` list.

- `infrastructure/spec_checker/metric_extractor.py`
  - Responsibility: metric extraction from simulation result structures.
  - Main class: `MetricExtractor`.
  - Architectural role: bridge between raw/natively extracted simulation structures and checker input.

- `infrastructure/llm/llm_client.py`
  - Responsibility: provider abstraction for OpenAI, DeepSeek, Groq, Gemini, Anthropic.

- `infrastructure/waveform_checker/*`
  - Responsibility: optional multimodal waveform diagnosis, plotting, and LLM-assisted interpretation.
  - Architectural role: auxiliary diagnostic path, not the main compliance engine.

- `infrastructure/schematic/*`
  - Responsibility: schematic synthesis, topology detection, graph/layout/rendering, publication rendering.
  - Architectural role: separate visualization subsystem rather than the main verification pipeline.

### `spec2testbench.presentation`

- `presentation/formatters/report_formatter.py`
  - Responsibility: markdown/json/console rendering of `VerificationReport`.
- `presentation/cli/main.py`
  - Responsibility: CLI adapter.

## Configuration files

- `spec2testbench/config/settings.py`
  - Responsibility: environment-driven settings for LLM, simulator, outputs, warning margin.

- `configs/paper_experiment.yaml`
  - Responsibility: experiment-level configuration referenced by paper campaign outputs.

- `pyproject.toml`, `setup.py`, `pytest.ini`, `.env.example`
  - Responsibility: packaging, test configuration, example environment configuration.

## YAML specifications

- `examples/benchmark_specs/*.yaml`
  - Canonical ACP-28/reference specs consumed by scripts and integration tests.
- `benchmark/industrial/specs/*.yaml`
  - Sky130 subset specs.
- `experiments/controlled_violations/generated_cases/*/specification.yaml`
  - mutated/variant cases.
- `experiments/frozen_pilot_v2/**/specification.yaml`
  - frozen pilot inputs.
- `lowpass_specs.yaml`
  - small standalone example/spec artifact.

## Netlists and SPICE models

- `benchmark/analogcoder_pro/*.cir`
  - Core benchmark netlists used by canonical campaigns.
- `benchmark/industrial/netlists/*.cir`
  - industrial subset netlists.
- `benchmark/industrial/models/sky130_tt.spice`
  - technology model include.
- `netlists/*.cir`
  - smaller generic examples.

## Testbench generators

- `spec2testbench/infrastructure/testbench/testbench_generator.py`
  - Main generator.
- `spec2testbench/infrastructure/testbench/template_engine.py`
  - supporting template logic.
- `spec2testbench/infrastructure/testbench/prompts/testbench_prompts.py`
  - LLM prompt builder.
- `testbenches/benchmark/*.py` and `*.cir`
  - pre-generated benchmark testbench examples; useful evidence, not the active generator implementation.

## ngspice execution components

- `spec2testbench/application/usecases/run_verification.py`
  - chooses simulation path and interprets execution state.
- `spec2testbench/infrastructure/simulator/pyspice_simulator.py`
  - primary real execution adapter.
- `spec2testbench/infrastructure/simulator/wsl_simulator.py`
  - alternative simulator path.
- `spec2testbench/infrastructure/simulator/ngspice_simulator.py`
  - simpler legacy wrapper.
- `spec2testbench/infrastructure/simulator/result_backends.py`
  - structured backend extraction.

## Measurement backends and metric extraction

- `spec2testbench/infrastructure/simulator/result_backends.py`
  - `NGSPICE_MEASURE`, `NGSPICE_WRDATA`, `PYSPICE`.
- `spec2testbench/infrastructure/spec_checker/metric_extractor.py`
  - higher-level metric computation and fallback lookup.

## Specification checkers and status models

- `spec2testbench/infrastructure/spec_checker/spec_checker.py`
  - metric-by-metric compliance checking.
- `spec2testbench/domain/value_objects/scientific_status.py`
  - run/scientific statuses.
- `spec2testbench/domain/value_objects/verdict.py`
  - metric verdicts and summary validation status.

## Reporting components

- `spec2testbench/presentation/formatters/report_formatter.py`
- `scripts/aggregate_metrics.py`
- `scripts/generate_paper_table.py`
- `scripts/build_final_experiment_outputs.py`
- `paper_final/*.md`, `paper_final/tables/*.tex`

## LLM components

- `spec2testbench/infrastructure/llm/llm_client.py`
- `spec2testbench/infrastructure/testbench/prompts/testbench_prompts.py`
- `spec2testbench/infrastructure/waveform_checker/llm_multimodal_client.py`
- `spec2testbench/infrastructure/waveform_checker/waveform_checker.py`

## Experiment scripts

Observed script families:

- Campaign runners: `run_paper_campaign.py`, `run_reference_28_campaign.py`, `run_industrial_sky130_campaign.py`, `run_controlled_violation_campaign_v2.py`.
- Evidence builders: `build_ground_truth_and_violations.py`, `build_frozen_pilot_v3.py`, `build_final_experiment_outputs.py`.
- Validation: `generate_full_ngspice_native_validation.py`, `validate_ngspice_native_extraction.py`, `validate_wrdata_metrics_independently.py`.
- Forensics/audit: `audit_*`, `inspect_raw.py`.

## Tests

- Unit-like repository tests live mostly in `tests/test_*.py`.
- Real simulator integration lives in `tests/integration/test_real_pipeline_ngspice.py`.
- Direct count of Python test files observed: 9.

## Canonical results and artifacts

- `artifacts/paper_campaign/20260711_094959/`
  - strong candidate for canonical ACP-28 campaign artifact set.
- `results/paper_campaign_summary.json`
  - confirms 28 executed circuits, all `REAL`, all `SUCCESS`, 27 compliant and 1 noncompliant.
- `artifacts/full_ngspice_native_validation/`
  - backend/native extraction evidence.
- `experiments/ground_truth/`
  - manual review and independent measurement evidence.
- `experiments/controlled_violations/`
  - generated mutation cases and manifests.

## Architectural reading

Fact observed:
- The repository does contain a domain/application/infrastructure/presentation layout.
- The real runtime path for verification is concentrated in `VerificationPipeline`.
- Experiment scripts and evidence folders are first-class citizens of the repository, not peripheral leftovers.

Interpretation:
- Spec2Testbench is both a software framework and a scientific artifact repository.
- The framework core is relatively small; the surrounding experiment/evidence layer is much larger and materially affects maintainability.
