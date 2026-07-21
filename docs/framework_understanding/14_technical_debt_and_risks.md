# Phase 14 - Technical Debt and Risks

## Critical

- `run_verification.py`: orchestration, status policy, provenance, and mock logic are co-located
  - Scientific risk: subtle policy changes can alter paper eligibility and compliance semantics together.
  - Software risk: hard to refactor safely.
  - Recommended refactor: split orchestration, status policy, provenance assembly, and simulation gateway.

## High

- Metric semantics duplicated across generator, extractor, and backend registries
  - Risk: adding a metric incompletely produces silent partial support.
  - Refactor: central metric registry with required analysis, unit, aliases, backend support, and comparator rule.

- Status derivation duplicated in `VerificationReport` and pipeline finalization
  - Risk: inconsistent behavior depending on construction path.
  - Refactor: single status policy object.

- Domain objects own serialization/parsing/rendering concerns
  - Risk: domain layer depends on YAML/SPICE rendering details.
  - Refactor: move YAML and deck rendering to adapters/assemblers.

## Medium

- simulation result DTO is an untyped dict contract
  - Risk: backend and checker assumptions drift.
  - Refactor: typed result objects.

- artifact command capture is simplified in campaign output
  - Risk: weaker exact reproducibility audit.
  - Refactor: persist exact executed command and temp/raw paths.

- output directory creation in settings constructor
  - Risk: import-time side effects.

## Low

- legacy or secondary simulator adapters coexist with primary path
  - Risk: reader confusion.

- large experiment/archive footprint obscures the core framework
  - Risk: onboarding cost.

## Architectural reading

Fact observed:
- the main debt is not lack of features; it is concentration of policy and duplication of metric/status knowledge.
