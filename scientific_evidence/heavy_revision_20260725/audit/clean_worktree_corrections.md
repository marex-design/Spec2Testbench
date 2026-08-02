# Clean Worktree Corrections

Date: 2026-07-25
Worktree: `E:\my_organisation\Memoire Maruba\code\Spec2Testbench-scientific-clean`
Branch: `codex/scientific-evidence-clean-20260725`
Base commit: `2678818e33972ae8612aa395f329501e85a3f98d`

## Scope

These corrections were implemented directly in the clean scientific worktree after the forensic audit. No file under `paper_final/` was modified.

## Functional corrections now present

- `spec2testbench/config/settings.py`
  - Added coherent output-root remapping so `output/`, `waveforms/`, `reports/`, and `results/` can stay under one campaign root.
- `spec2testbench/presentation/cli/main.py`
  - `verify` now requires a real existing netlist for scientific runs.
  - `--output` now remaps `results_dir` as well, keeping the output architecture clean.
  - Scientific CLI runs force real execution and persisted artifacts.
- `spec2testbench/application/usecases/run_verification.py`
  - Added artifact persistence and run-bundle generation.
  - Added provenance validation for caller-supplied artifacts before replay.
  - Rejects stale or mismatched artifact reuse by run id, timestamp, commit, file presence, and SHA256.
  - Allows only explicit replay/import modes for historical artifact reuse.
  - Treats missing optional `raw_result_file` as non-blocking when it was not actually produced.
- `tests/integration/test_real_pipeline_ngspice.py`
  - Canonical replay now uses the pipeline helper that stamps artifact provenance.
  - Controlled-violation case is skipped when its fixture is absent from the frozen checkout.
- `tests/integration/test_llm_stub_pipeline.py`
  - Replay artifacts are persisted in stable per-case directories and marked as explicit replay.
- `tests/test_scientific_workflow_guards.py`
  - Added guard coverage for output isolation, stale artifact rejection, provenance enforcement, explicit replay acceptance, and optional missing raw artifact handling.

## Post-fix verification status

Archived outputs are under `scientific_evidence/heavy_revision_20260725/audit/tests_after_fix/`.

- `tests/test_scientific_workflow_guards.py`: `13 passed, 2 skipped`
- `tests/integration/test_real_pipeline_ngspice.py`: `10 passed, 1 skipped`
- `tests/integration/test_llm_stub_pipeline.py`: `6 passed, 5 skipped`
- `tests/test_verification_pipeline.py tests/test_canonical_harness.py`: `58 passed`

## Remaining known environment limitation

- `typer` is absent in the current environment, so CLI-import tests skip rather than fail. This is an environment gap, not a framework regression.
