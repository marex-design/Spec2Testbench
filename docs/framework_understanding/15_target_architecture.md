# Phase 15 - Target Architecture

## Proposed package split

```text
domain/
application/
ports/
adapters/
infrastructure/
interfaces/
experiments/
```

## Suggested core interfaces

```python
class SimulatorPort:
    def execute(self, testbench) -> "SimulationResult":
        ...

class MetricBackendPort:
    def extract(self, artifacts, requests) -> dict[str, "MeasurementResult"]:
        ...

class TestbenchGeneratorPort:
    def generate(self, specification) -> "TestbenchPlan":
        ...

class ComplianceCheckerPort:
    def evaluate(self, requirement, measurement) -> "ComplianceDecision":
        ...
```

## Target responsibilities

- `domain/`
  - `Specification`
  - `Requirement`
  - `MetricDefinition`
  - `Threshold`
  - `Measurement`
  - `SimulationResult`
  - status policy/value objects

- `application/`
  - `RunVerificationUseCase`
  - `GenerateTestbenchUseCase`
  - `AssessScientificEligibilityUseCase`

- `ports/`
  - simulator, backend, report writer, LLM planner, spec reader

- `adapters/`
  - YAML spec reader
  - ngspice adapter
  - WRDATA backend
  - MEASURE backend
  - markdown/json report writers
  - OpenAI/DeepSeek/etc clients

- `experiments/`
  - campaign runners only

## Benefits

- deterministic generator and LLM generator both implement `TestbenchGeneratorPort`
- ngspice and future Xyce both implement `SimulatorPort`
- measure and wrdata both implement `MetricBackendPort`
- provenance generation becomes a dedicated adapter/service
- experiments stop depending on hidden dict contracts

## Architectural reading

Interpretation:
- the best next step is not “rewrite everything”, but extracting registries and typed DTOs first, then inverting dependencies around the simulator/generator/checker boundary.
