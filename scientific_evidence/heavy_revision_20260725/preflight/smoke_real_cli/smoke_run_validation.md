# Smoke Run Validation

- Date: `2026-07-25`
- Commit: `6520d80100bd4ac5806bddbe26e3a4036368d7d8`
- Command: `spec2testbench verify --specs examples/benchmark_specs/p10_lowpass.yaml --netlist benchmark/analogcoder_pro/p10_lowpass.cir --output "E:\my_organisation\Memoire Maruba\code\Spec2Testbench\scientific_evidence\heavy_revision_20260725\preflight\smoke_real_cli\run_output" --format json --no-llm`
- Return code: `0`
- Overall verdict: `PASS`
- Execution status: `SUCCESS`
- Simulation mode: `REAL`

## Checks
- `simulation_mode_real`: `true`
- `ngspice_invoked`: `true`
- `real_netlist_confirmed`: `true`
- `generated_testbench_exists`: `true`
- `result_belongs_to_current_run`: `true`
- `no_historical_fallback`: `true`
- `all_outputs_under_smoke_root`: `true`
- `results_dir_redirected`: `true`
- `report_dir_redirected`: `true`
- `waveform_dir_redirected`: `true`
- `output_dir_redirected`: `true`
