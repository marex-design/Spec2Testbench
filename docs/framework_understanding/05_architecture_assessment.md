# Phase 5 - Architecture Assessment

## Short answer

1. Business core: `Specification`, `TestBench`, `MetricExtractor`, `SpecChecker`, and the status logic in `VerificationReport`.
2. Infrastructure adapters: simulator layer, LLM client, waveform checker, schematic rendering, filesystem/report writers.
3. Orchestration: `VerificationPipeline`.
4. Domain dependence on files/libraries: yes, partially.
5. Backends interchangeable: partially.
6. Checker independent of simulator: mostly yes at API level, but metric structure assumptions leak in.
7. Reporting decoupled from compliance: partially.
8. Statuses centralized: partially.
9. Claimed Clean Architecture compliance: partial.
10. Boundary violations exist: yes.

## Principle-by-principle assessment

- Clean Architecture: `Partiellement conforme`
  - Strength: explicit `domain`, `application`, `infrastructure`, `presentation` folders.
  - Weakness: application layer directly instantiates concrete infrastructure classes.

- Onion Architecture: `Partiellement conforme`
  - Core types exist, but outer concerns still leak inward through dict schemas and concrete dependencies.

- Domain / application / infrastructure separation: `Partiellement conforme`
  - Separation exists physically in folders.
  - Real dependency inversion is incomplete.

- Dependency inversion: `Non conforme`
  - `VerificationPipeline` imports and constructs `TestBenchGenerator`, `SpecChecker`, `WaveformChecker`, `PySpiceSimulator` directly.

- Single responsibility: `Partiellement conforme`
  - `Specification` and `TestBench` are focused.
  - `VerificationPipeline` is very large and mixes orchestration, status derivation, provenance, mock generation, and recovery policy.

- Interfaces and adapters: `Partiellement conforme`
  - Interfaces exist in `domain/interfaces/`.
  - Main orchestration still bypasses constructor-injected ports.

- Ports and adapters: `Partiellement conforme`
  - Present in intention.
  - Not fully realized in runtime composition.

- Testability: `Conforme`
  - Strong pure-Python test surface.
  - Pipeline can consume synthetic `simulation_results`.

- Coupling: `Partiellement conforme`
  - Checker depends on generic dicts rather than raw simulator API calls.
  - But dict shapes are implicit contracts shared across layers.

- Cohesion: `Partiellement conforme`
  - `SpecChecker` and `MetricExtractor` are cohesive.
  - `run_verification.py` is less cohesive.

- Circular dependencies: `Conforme`
  - No obvious circular import problem was observed in the inspected path.

- Side effects control: `Partiellement conforme`
  - Report/artifact creation is mostly isolated to scripts/formatters.
  - Output directory creation happens in config initialization, which is an eager side effect.

- File handling: `Partiellement conforme`
  - Provenance is careful about hashes and file references.
  - File lifecycle and artifact persistence are spread across scripts and simulator code.

- External process management: `Partiellement conforme`
  - ngspice integration has explicit status modeling.
  - Exact command persistence is weaker than ideal in paper artifacts.

## Architectural violations observed

- `VerificationPipeline` constructs infrastructure implementations directly.
- `Specification` mixes domain data with YAML parsing and serialization.
- `TestBench` mixes domain plan with concrete SPICE/PySpice rendering.
- Status derivation exists both in `VerificationReport.__post_init__` and `_finalize_report_statuses()`.
- Simulation result contracts are plain dicts rather than typed application DTOs.

## Real business core

Observed core rules:

- a metric must be extractable and unit-compatible before it can be judged
- a missing metric becomes `ERROR`/`NOT_EVALUATED`, not silent zero
- scientific category depends on execution plus compliance, not simulation alone
- mock results are not paper-eligible
- nominal and PVT results are treated separately

## Architectural reading

Fact observed:
- the repository structure advertises Clean Architecture more strongly than the dependency graph actually enforces it.

Interpretation:
- this is a usable architecture for research software, but not yet a strict ports-and-adapters implementation.
