# PRE-EXPERIMENT GO/NO-GO

- Date: `2026-07-25`
- Decision: `GO`
- Scientific commit: `6520d80100bd4ac5806bddbe26e3a4036368d7d8`
- Authoritative CLI command: `spec2testbench verify --specs examples/benchmark_specs/p10_lowpass.yaml --netlist benchmark/analogcoder_pro/p10_lowpass.cir --output "E:\my_organisation\Memoire Maruba\code\Spec2Testbench\scientific_evidence\heavy_revision_20260725\preflight\smoke_real_cli\run_output" --format json --no-llm`
- Planned campaign root: `E:\my_organisation\Memoire Maruba\code\Spec2Testbench\scientific_evidence\heavy_revision_20260725\campaigns\acp28_nominal_real_6520d801`

## Gates
- G1 `PASS`: Corrections committed (6520d80100bd4ac5806bddbe26e3a4036368d7d8)
- G2 `PASS`: Worktree code clean (git status --short --branch)
- G3 `PASS`: Typer available or CLI validated (setup.py dependency audit + CLI help/version smoke)
- G4 `PASS`: CLI tests executed (cli_tests_after_typer.txt)
- G5 `PASS`: Full pytest suite without critical failure (pytest_full_summary.json)
- G6 `PASS`: Smoke run via public CLI succeeded (spec2testbench verify --specs examples/benchmark_specs/p10_lowpass.yaml --netlist benchmark/analogcoder_pro/p10_lowpass.cir --output "E:\my_organisation\Memoire Maruba\code\Spec2Testbench\scientific_evidence\heavy_revision_20260725\preflight\smoke_real_cli\run_output" --format json --no-llm)
- G7 `PASS`: REAL mode confirmed (smoke_run_validation.md)
- G8 `PASS`: Real netlist confirmed (smoke_run_validation.md)
- G9 `PASS`: All outputs isolated (smoke_run_validation.md)
- G10 `PASS`: No old result reused (artifact_validation=CURRENT_RUN)
- G11 `PASS`: Anti-stale tests passed (stale_artifact_scenarios.csv)
- G12 `PASS`: Provenance and hashes present (smoke_run_manifest.json + smoke_run_sha256sums.txt)
- G13 `PASS`: No paper file modified (paper_final_integrity_report.md)

## GO

- All mandatory gates G1-G13 are `PASS`.
- ACP-28, mutations, baselines, and ablations remain intentionally not started in this phase.
