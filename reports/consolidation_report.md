# Consolidation Report

## Scope

This consolidation stabilized the central verification pipeline only. Schematic
generation and peripheral extensions were not modified.

## Files Modified Or Added

- `spec2testbench/application/usecases/run_verification.py`
- `spec2testbench/config/settings.py`
- `spec2testbench/domain/value_objects/scientific_status.py`
- `spec2testbench/infrastructure/simulator/pyspice_simulator.py`
- `spec2testbench/infrastructure/spec_checker/spec_checker.py`
- `spec2testbench/presentation/formatters/report_formatter.py`
- `scripts/run_paper_campaign.py`
- `configs/paper_experiment.yaml`
- `pytest.ini`
- `tests/test_verification_pipeline.py`
- `tests/integration/test_real_pipeline_ngspice.py`
- `docs/verdict_semantics.md`
- `docs/experimental_protocol.md`
- `docs/reproducibility_protocol.md`
- `docs/paper_eligible_results_policy.md`
- `reports/remaining_scientific_risks.md`
- `reports/llm_current_limitations.md`

## Classes Added

- `ExecutionStatus`
- `SimulationMode`
- `ComplianceStatus`
- `RobustnessStatus`
- `ScientificCategory`
- `MetricTrace`

## Main Functions Modified

- `VerificationPipeline.verify`
- `VerificationPipeline._run_simulation_with_ngspice`
- `VerificationReport.overall_verdict`
- `PySpiceSimulator.run`
- `SpecChecker._to_si`
- `ReportFormatter.to_json`
- `ReportFormatter.to_markdown`

## Bugs Corrected

- Legacy `RUN`/`FAIL` ambiguity was replaced with separated scientific statuses.
- Silent mock fallback is now disabled by default for paper-style runs.
- Mock results are explicitly marked `simulation_mode = MOCK` and `eligible_for_paper_results = false`.
- Real simulator metadata is preserved as `simulation_mode = REAL`.
- Unit conversion now uses exact unit matching; `mV` is no longer at risk of being treated as `V`.
- Missing metrics are classified as `NOT_EVALUATED` rather than compliant.

## Tests Added Or Updated

- Unit tests for exact unit conversions.
- Unit tests for incompatible units and non-numeric metrics.
- Unit tests for successful compliant simulations.
- Unit tests for successful non-compliant simulations.
- Unit tests for missing metrics.
- Unit tests for ngspice error and timeout classifications.
- Unit tests for mock allowed and mock forbidden cases.
- Unit tests for recovered simulation classification.
- Unit tests for nominal-only, robust pass, and robust fail cases.
- Marked integration tests for five circuit families requiring ngspice.

## Pytest Result

Command:

```powershell
pytest -q
```

Result:

```text
34 passed, 5 skipped, 1 warning in 10.94s
```

The five skipped tests are marked ngspice integration tests and require
`RUN_NGSPICE_INTEGRATION=1`.

## Paper Campaign

Command:

```powershell
python scripts\run_paper_campaign.py
```

Run id:

```text
20260711_094959
```

Artifact directory:

```text
artifacts/paper_campaign/20260711_094959
```

Generated result tables:

- `results/paper_campaign_summary.csv`
- `results/paper_metric_results.csv`
- `results/circuit_test_matrix.csv`
- `results/simulability_vs_compliance.csv`
- `results/paper_campaign_summary.json`

## Campaign Summary

- Total reference circuits: 28
- Simulation mode: 28 `REAL`, 0 `MOCK`, 0 `RECOVERED`
- Execution status: 28 `SUCCESS`, 0 `ERROR`, 0 `TIMEOUT`
- Scientific category: 27 `SIMULABLE_COMPLIANT`, 1 `SIMULABLE_NONCOMPLIANT`
- Paper eligible results: 28
- Simulation success rate: 1.0
- Specification compliance rate: 0.9642857142857143
- Simulable but non-compliant rate: 0.03571428571428571
- Metric extraction success rate: 1.0
- Paper-eligible result rate: 1.0
- False successes under simulability-only validation: 1

## Circuits Simulated

All 28 reference circuits were simulated with `simulation_mode = REAL`.

## Non-Simulable Circuits

None in the consolidated paper campaign.

## Simulable But Non-Compliant Circuits

- `p04_amplifier`: `dc_gain_db = -160.0000000868589 dB`, expected `>= 0.0 dB`.

## Compliant Circuits

`p01_amplifier`, `p02_amplifier`, `p03_amplifier`, `p05_amplifier`,
`p06_inverter`, `p07_inverter`, `p08_currentmirror`, `p09_comparator`,
`p10_lowpass`, `p11_highpass`, `p12_bandpass`, `p13_bandstop`,
`p14_amplifier`, `p15_amplifier`, `p16_opamp`, `p17_currentmirror`,
`p18_opamp`, `p19_mixer`, `p20_opamp`, `p21_opamp`, `p22_oscillator`,
`p23_oscillator`, `p24_integrator`, `p25_differentiator`, `p26_adder`,
`p27_subtractor`, `p28_schmitt`.

## Mock Results Encountered

No mock result appears in the consolidated paper campaign.

## Results Excluded From The Paper

Pre-consolidation outputs and two invalid intermediate consolidation runs were
archived under `archive/pre_consolidation/`. They must not be mixed with the
paper campaign.

## Remaining Limits

- Raw ngspice files are still temporary and are not preserved in the artifact directories.
- `ngspice_version` is currently `null` in provenance to avoid blocking on this Windows environment.
- Robustness is not evaluated in the nominal 28-circuit campaign.
- LLM results remain exploratory and are documented separately in `reports/llm_current_limitations.md`.
