# Phase 12 - Test Strategy

## Observed test layout

- Top-level tests:
  - `tests/test_verification_pipeline.py`
  - `tests/test_supported_registry.py`
  - `tests/test_publication_schematic.py`
  - `tests/test_ngspice_result_backends.py`
  - `tests/test_multimodal_client.py`
  - `tests/test_ground_truth_artifacts.py`
- Integration:
  - `tests/integration/test_real_pipeline_ngspice.py`

## Categories

- Unit/business-rule tests:
  - metric extraction
  - status semantics
  - unit conversion
  - eligibility rules
  - override propagation

- Backend tests:
  - `test_ngspice_result_backends.py`

- Integration tests with real ngspice:
  - `tests/integration/test_real_pipeline_ngspice.py`

- Multimodal/LLM-adjacent tests:
  - `test_multimodal_client.py`

- Artifact/provenance/ground-truth checks:
  - `test_ground_truth_artifacts.py`

## Behavior coverage strengths

- Missing metrics do not silently pass
- invalid oscillation blocks frequency extraction
- units are exact and incompatible units fail
- mock vs real eligibility rules
- recovered simulation status
- robustness status derivation
- transient override provenance
- AC stimulus collapse behavior

## Gaps

- I did not verify the claimed “66 unique tests” by executing pytest in this pass.
- I only confirmed there are 9 Python test files.
- Some script-level campaigns and manuscript-linked counts are validated by artifacts rather than by a unified automated suite.

## Architectural reading

Fact observed:
- the test suite is strongest around scientific rule correctness and regression protection for subtle edge cases.

Interpretation:
- this is a good sign for refactoring safety, even though experiment-wide claim verification is spread across scripts and static artifacts.
