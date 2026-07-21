# Spec2Testbench for Software Designers

## Level 1 - Overview

Spec2Testbench takes a structured circuit specification, derives a testbench, runs ngspice, extracts metrics, checks them against thresholds, and classifies the result for both engineering compliance and scientific reporting. The real orchestration center is `VerificationPipeline`; the paper campaign uses the deterministic path, not the LLM path.

## Level 2 - Request walkthrough

The practical flow is:

1. parse YAML into `Specification`
2. choose categories and generate `TestBench`
3. execute simulation through `PySpiceSimulator`
4. parse backend outputs and extract metrics
5. verify metrics with `SpecChecker`
6. derive statuses and provenance
7. render reports and campaign summaries

## Level 3 - Software components

- Domain:
  - `Specification`
  - `TestBench`
  - status/value objects
- Application:
  - `VerificationPipeline`
- Infrastructure:
  - simulator adapters
  - backends
  - LLM client
  - waveform checker
- Presentation:
  - CLI
  - report formatter

## Level 4 - Scientific invariants

The most important observed invariants are:

1. a missing metric must not silently become zero
2. mock simulation is never paper-eligible
3. non-finite backend values are rejected
4. incompatible units are rejected
5. oscillation frequency is rejected when sustained oscillation is not validated

## Level 5 - Extending the framework

### Add a new metric

- Understand:
  - `testbench_generator.py`
  - `metric_extractor.py`
  - `result_backends.py`
  - `spec_checker.py`
- Add:
  - category inference
  - measurement planning
  - backend extraction or metric computation
  - checker coverage
- Tests:
  - missing metric
  - unit conversion
  - pass/fail boundaries

### Add a new analysis

- Extend `AnalysisType`
- add rendering in `AnalysisConfig.to_spice()`
- teach generator when to request it
- teach simulator/backend how to consume its outputs

### Add a new circuit family

- extend `CircuitType`
- extend default categories
- add metric aliases if needed
- add benchmark spec and netlist fixtures

### Add a new backend

- implement a new backend beside `NGSPICE_MEASURE` and `NGSPICE_WRDATA`
- define its artifact contract
- keep non-finite and missing-value safeguards

### Add a new simulator

- implement a simulator port-style adapter
- preserve provenance, statuses, and exact artifact capture

### Add an LLM generator

- implement behind the same generator interface
- ensure output still flows through the same checker and evidence policy

### Add a new experiment

- keep experiment scripts outside the business core
- write timestamped artifacts
- write machine-readable summary files

## Final synthesis

### Current architecture in 10 points

1. The true orchestration center is `VerificationPipeline`.
2. Structured specs are represented by one dataclass plus nested metric dicts.
3. Testbench generation supports deterministic and optional LLM paths.
4. Canonical campaigns currently use the deterministic path.
5. The real execution path uses `PySpiceSimulator`.
6. Native result backends are first-class and scientifically important.
7. Metric extraction logic is split across backends and `MetricExtractor`.
8. Compliance and scientific status are distinct concepts.
9. Provenance capture is deliberate and extensive.
10. Experiment scripts are a major part of the repository’s real architecture.

### Five most important invariants

1. Missing metrics do not become zero.
2. Mock runs are not scientific evidence.
3. Units must be compatible.
4. Non-finite values are rejected.
5. Execution success and compliance success are not equivalent.

### Five biggest risks

1. status logic duplication
2. metric-definition duplication
3. oversized orchestration module
4. dict-based implicit contracts
5. mixed domain/parsing/rendering responsibilities

### Five priority refactorings

1. central metric registry
2. single status policy service
3. typed simulation result DTO
4. constructor-injected ports in application layer
5. split provenance/report writing from pipeline

### Five missing experiments or audits

1. full reconstruction of controlled-violation summary counts
2. exact verification of “66 tests passed” by execution
3. formal backend parity matrix across all metrics
4. exact command-line provenance persistence audit
5. explicit LLM-vs-deterministic benchmark artifact comparison

### Real place of the LLM today

The LLM is implemented as an optional adapter for testbench generation and multimodal diagnosis, but it is not part of the canonical paper campaign path confirmed in `scripts/run_paper_campaign.py`.

### Real Clean Architecture compliance

`Partiellement conforme`.

### Recommended manual study order

1. `spec2testbench/presentation/cli/main.py`
2. `spec2testbench/application/usecases/run_verification.py`
3. `spec2testbench/domain/entities/specification.py`
4. `spec2testbench/domain/entities/testbench.py`
5. `spec2testbench/infrastructure/testbench/testbench_generator.py`
6. `spec2testbench/infrastructure/simulator/pyspice_simulator.py`
7. `spec2testbench/infrastructure/simulator/result_backends.py`
8. `spec2testbench/infrastructure/spec_checker/metric_extractor.py`
9. `spec2testbench/infrastructure/spec_checker/spec_checker.py`
10. `scripts/run_paper_campaign.py`
