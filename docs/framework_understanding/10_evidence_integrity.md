# Phase 10 - Evidence Integrity

## Provenance captured

Observed in `VerificationReport.provenance`:

- specification file and hash
- netlist file and hash
- generated testbench hash
- git commit
- python / PySpice / ngspice version
- OS
- ngspice command and return code
- raw result file path and existence flag
- statuses
- measurement backend/source/command/status
- variant overrides

## Safeguards requested

1. Missing metric never becomes zero
   - Implemented:
     - enforced by extractor/checker behavior
     - tested by `test_missing_measure_does_not_fall_back_to_synthetic_zero`
   - Bypass risk:
     - only if a new backend injects synthetic values improperly

2. Mock never paper-eligible
   - Implemented:
     - eligibility requires `REAL` or `RECOVERED`
   - Tested:
     - `test_mock_explicitly_allowed_is_not_paper_eligible`

3. Non-finite value rejected
   - Implemented:
     - `parse_measure_file()`
     - `parse_wrdata_file()`
   - Coverage:
     - indirectly supported by parser logic; direct explicit test not inspected in current sample

4. Incompatible unit rejected
   - Implemented:
     - `SpecChecker._to_si()`
   - Tested:
     - `test_incompatible_unit_is_not_evaluated`

5. Oscillation frequency without sustained oscillation rejected
   - Implemented:
     - `MetricExtractor` checks `oscillation_validation.status`
   - Tested:
     - `test_invalid_oscillation_blocks_frequency_metric`
     - integration test for non-oscillating variant

6. Overrides preserve provenance
   - Implemented:
     - `VariantOverride`
     - testbench metadata `variant_overrides`
     - provenance field `variant_overrides`
   - Tested:
     - `test_controlled_variant_override_applies_to_transient_analysis`

7. Old results do not silently replace canonical results
   - Partial evidence:
     - campaign scripts generate timestamped artifact directories
   - Remaining risk:
     - `results/` summary files are rewritten by scripts; canonicality still depends on process discipline.

## Architectural reading

Fact observed:
- evidence integrity rules are present in both code and tests, especially around missing metrics, mock runs, units, and oscillation validity.

Interpretation:
- scientific safeguards are a stronger part of the implementation than strict architectural purity.
