# From Specs to SPICE Testbenches: A Beginner-Friendly Framework for LLM-Assisted Analog Verification

## Abstract
Analog verification remains difficult for beginners because specification parsing, testbench authoring, simulation control, metric extraction, and result interpretation are usually spread across several tools and expert workflows. This paper presents Spec2TestBench, a beginner-friendly framework that maps user-facing specifications to SPICE-oriented verification artifacts through a layered architecture combining structured specifications, deterministic testbench templates, optional large language model assistance, simulation backends, waveform analysis, and report generation. The current implementation supports 35 analog circuit families and exposes a normalized registry of 28 verification tests grouped into 6 categories: DC, AC, transient, spectral, differential, and PVT. On the audited `dev-moanra` branch dated June 10, 2026, the framework passes 11/11 automated tests after stabilization work on headless plotting, pipeline verdict propagation, transient metric plumbing, and test isolation. These results position Spec2TestBench as a practical educational and research scaffold for analog verification workflows, while also highlighting the gap between a complete 28-test specification catalog and the subset currently implemented as deterministic executable generators.

## 1. Introduction
Analog verification is often introduced through fragmented scripts, hand-written SPICE decks, and tool-specific knowledge that are hard for beginners to reproduce. Recent progress in LLM-assisted engineering suggests that natural-language specifications can be transformed into verification artifacts with less manual effort, but educationally useful frameworks still need determinism, traceability, and clear reporting.

Spec2TestBench targets this need by combining:

- YAML-based circuit specifications
- Testbench generation with deterministic templates and optional LLM support
- SPICE simulation integration
- Metric extraction and PASS/FAIL checking
- Waveform plotting and multimodal diagnosis
- Schematic rendering from SPICE netlists

The goal is not only automation, but also accessibility: each stage leaves inspectable artifacts that can be reused in teaching, experimentation, and debugging.

## 2. Framework Overview
The framework follows a clean architecture decomposition with presentation, application, domain, and infrastructure layers. Users can interact through a command-line interface to generate testbenches, run verification, analyze waveform failures, and draw netlist-based schematics.

The verification flow is:

1. Read a YAML specification into a domain `Specification`.
2. Select verification categories from the circuit type or explicit user request.
3. Generate a `TestBench` using deterministic templates or an LLM.
4. Run simulation through a backend or use a fallback mock path.
5. Extract performance metrics and compare them against requirements.
6. Produce reports and waveform-oriented diagnostics.

## 3. Supported Verification Scope
The repository currently exposes:

- 35 supported circuit families in the circuit registry
- 28 standardized verification tests in the test registry
- 6 top-level test groups

The 28 tests are distributed as follows:

- DC: 4
- AC: 6
- Transient: 7
- Spectral: 4
- Differential: 4
- PVT: 3

This registry is important for research framing because it defines the intended verification vocabulary independently of the current execution backend.

## 4. Current Implementation Status
The audit of branch `dev-moanra` shows that the framework already provides strong building blocks, but not all 28 test names are implemented as dedicated executable flows yet.

Implemented and usable today:

- Category-based deterministic testbench generation for `dc`, `ac`, `transient`, `spectral`, `differential`, and `pvt`
- Specification checking with unit handling and verdict generation
- Waveform plotting for transient, AC, FFT, eye-diagram, and comparison views
- CLI commands for `verify`, `generate`, `diagnose`, `draw`, `config`, and `providers`
- Schematic rendering modules from SPICE-like netlists

Important limitation:

- The framework currently implements 6 executable category templates rather than 28 fully specialized per-test generators. Therefore, the 28-test registry should be described as the normalized target verification catalog, while the present codebase delivers partial operational coverage through grouped testbench generation.

## 5. Stabilization Results on `dev-moanra`
During this audit, the following reliability issues were corrected:

- Pytest collection was restricted to the real `tests/` suite instead of collecting exploratory scripts.
- Matplotlib plotting was switched to a headless backend for reproducible test execution.
- Verification reports now propagate `ERROR` verdicts correctly instead of potentially reporting false success.
- Success-rate computation now treats `WARNING` as a soft success, consistent with the framework verdict semantics.
- Transient results are now stored and read under a consistent key, fixing metric extraction paths.
- Simulator availability checks are now lazy, avoiding unnecessary delays during non-simulation workflows.

Additional regression tests were added for these fixes.

## 6. Experimental Snapshot
As of June 10, 2026, the local audited state produced the following measurable outcomes:

- Automated tests passed: 11/11
- Supported test groups: 6
- Registered standardized tests: 28
- Supported circuit families: 35
- CLI smoke checks passed: help command and mock verification flow
- Example verification: `examples/amplifier_spec.yaml` completed successfully in mock mode with an overall `PASS` verdict and a 100% success rate on 2 extracted metrics

These numbers support a reproducibility argument, although they do not yet constitute a full analog benchmark campaign across all supported circuit families.

## 7. Discussion
Spec2TestBench is already useful as a pedagogical platform because it externalizes verification intent as structured specifications and keeps outputs inspectable. This makes it easier for beginners to understand how requirements map to analyses and metrics. The framework also creates a natural interface for LLM assistance without making the verification flow entirely opaque.

However, a research paper should present the current system honestly:

- The test catalog is broader than the current deterministic execution coverage.
- Simulation-backed evaluation still depends on the availability and quality of local SPICE infrastructure.
- Some benchmark and schematic-generation scripts remain exploratory and would benefit from stronger packaging and integration.

## 8. Future Work
The next steps with the highest research value are:

- Implement dedicated executable logic for all 28 verification tests
- Run a benchmark campaign across the 35 circuit families
- Measure generation correctness, metric extraction accuracy, and diagnosis usefulness
- Compare deterministic generation against LLM-generated testbenches
- Quantify beginner usability through classroom or lab studies

## 9. Conclusion
Spec2TestBench demonstrates that a beginner-friendly LLM-assisted analog verification framework can be organized around clean software abstractions, structured specifications, standardized verification intents, and reproducible reporting. The current repository already provides a credible foundation with 35 supported circuit classes, a 28-test verification vocabulary, and a stabilized automated test suite. The strongest claim supported by the present implementation is that the framework is a practical and extensible scaffold for analog verification research and education, with clear pathways toward full per-test execution coverage.
