# Execution Plan

Date: 2026-07-25

## Scope and guardrails

- This audit is limited to the framework, tests, benchmarks, scripts, outputs, and provenance paths.
- No file under `paper_final/` will be edited, restored, regenerated, or treated as valid evidence without separate provenance verification.
- No previous result will be reused unless its provenance can be tied back to the current raw inputs, code state, and recorded hashes.

## Baseline state captured before further work

- Starting branch observed before branch creation: `reviewer-evidence-revision`
- Local audit branch created: `codex/execution-plan-20260725`
- Current `HEAD`: `c90c3dc63d495e496a8395a9e022aa4163d3b287`
- Worktree snapshot at audit start: `58 modified`, `784 deleted`, `5 untracked`
- The `paper_final/` tree is already absent from the working tree in many paths. Those deletions predate this plan and are not being altered here.

## LaTeX and manuscript inventory

No `.tex`, `.bib`, `.cls`, or `.sty` file currently exists on disk in the working tree, so no on-disk SHA256 could be recorded at this stage.

Tracked manuscript-related paths missing from the working tree were recorded for traceability using their `HEAD` blob ids:

| Path | Worktree status | `HEAD` blob id |
| --- | --- | --- |
| `paper_final/IEEEtran_compat.cls` | missing | `2d855d54eb1ecf7d022618b345b2ad094f8ca12b` |
| `paper_final/main.tex` | missing | `1cbc756bdc157d4a8ede0cb264687b284fd1dd0c` |
| `paper_final/references_revised.bib` | missing | `8a4803a3ef6832181b738409acbbdec4603eda82` |
| `paper_final/sections/experimental_methodology.tex` | missing | `eb415fcf57f0633273f1ca4c60faee5540433463` |
| `paper_final/sections/method_revised.tex` | missing | `458cc8b32b7cd01d90142e31f845924272aafc15` |
| `paper_final/sections/results_revised.tex` | missing | `51bc5b6aa24c25f0c8f5afc080387543fae70680` |
| `paper_final/tables/results_tables.tex` | missing | `594dacc9aee8c4ac060f812236a624d01f82ef69` |

Operational rule from this point onward:

- If any manuscript file is restored later, record its filesystem SHA256 immediately before any other action and keep it out of normal framework edits.

## Audit of `verify`

Code audited: `spec2testbench/presentation/cli/main.py`

Functional behavior confirmed:

- `verify` validates the spec path and warns when the netlist path is missing or absent (`main.py:66-85`).
- When `--output` is provided, it redirects `output_dir`, `waveform_dir`, and `report_dir` under the chosen root (`main.py:87-90`).
- It configures provider selection, optional LLM usage, optional planner LLM, invokes `VerificationPipeline.verify_from_yaml`, then formats the report as markdown, JSON, or console output (`main.py:92-142`).
- It returns a non-zero exit code when the overall verdict is `FAIL` or `RUN` (`main.py:144-145`).

Audit findings:

- `verify` does not remap `settings.output.results_dir` when `--output` is supplied. Persisted result summaries created by the pipeline can therefore land under the default `./results` tree while reports and waveforms go elsewhere. This weakens the intended clean output contract.
- The CLI message says a missing netlist "will use mock results", but the pipeline only does that when `allow_mock` is enabled in settings. The message is therefore stronger than the actual guarantee.
- Artifact persistence is not surfaced as a CLI switch here; runtime behavior depends on configuration and environment, not on an explicit audit/freeze mode in the command.

## Audit of `run_verification.py`

Code audited: `spec2testbench/application/usecases/run_verification.py`

Functional behavior confirmed:

- `VerificationPipeline.verify` follows a clear four-step flow: testbench generation, simulation, spec checking, then waveform analysis for failed metrics (`run_verification.py:366-503`).
- The pipeline enriches the generated testbench with required metric metadata and measurement requests before simulation (`run_verification.py:386-450`).
- Native backend metrics are treated as authoritative when present, which reduces silent drift between extraction paths (`run_verification.py:453-458`).
- Provenance capture is strong at the per-run level: it records spec and netlist hashes, binding status, backend selection, executed deck hashes, generated testbench hashes, runtime metadata, and failure context (`run_verification.py:981-1039`).
- Persisted run bundles are timestamped and separated into simulation, figures, report, and result-summary locations (`run_verification.py:1056-1128`).
- `verify_from_yaml` is intentionally thin and delegates to `verify` after parsing the YAML specification (`run_verification.py:1462-1464`).

Audit findings:

- The pipeline supports caller-supplied `testbench` and `simulation_results`. That is useful for tests, but any campaign script using those hooks must record origin and freshness explicitly or it can accidentally replay stale artifacts.
- Artifact directories are created as soon as a persisted run starts. Failed runs still leave bundles behind, so downstream scripts must not treat mere artifact presence as proof of validity.
- The provenance model is good for newly produced runs, but there is no built-in gate that validates the provenance of an old artifact bundle before another script consumes it.
- Artifact persistence writes reports into `report_dir` and summaries into `results_dir`; combined with the CLI gap above, a single logical run can still be split across multiple roots unless the caller aligns all output settings.

## Execution sequence from here

1. Treat the current worktree as non-clean and non-authoritative for prior evidence. Nothing already present under deleted or untracked result areas will be trusted by default.
2. Keep all manuscript paths out of scope. If any paper file reappears in the worktree, hash it immediately and leave it untouched.
3. Before running any campaign, audit every script that calls `VerificationPipeline.verify(...)` or `verify_from_yaml(...)` to identify whether it can inject precomputed `testbench` or `simulation_results`.
4. Add a provenance gate for reused artifacts. Minimum rule: accept reuse only if the artifact manifest, spec hash, netlist hash, generated deck hash, backend metadata, and source commit all match the current intended inputs.
5. Align output roots before large runs. In particular, ensure reports, waveforms, and result summaries land under one explicit campaign root instead of splitting across `output/`, `reports/`, and `results/`.
6. Only after steps 3 to 5 are complete, run fresh verification campaigns from raw spec and netlist inputs.
7. Archive each fresh run with its manifest, report JSON, report markdown, figure paths, simulator command, and hash metadata so later tables can be traced without touching the manuscript.

## Immediate next checks recommended

- Inspect direct callers of `VerificationPipeline` in `scripts/` and `tests/` for any path that bypasses fresh execution.
- Decide whether `verify --output ...` must also redirect `results_dir` before campaign execution.
- Inventory existing untracked result files such as `experiments/frozen_pilot_v3/reference_results.csv` and verify their provenance before any reuse.

## Files changed by this audit step

- Added `EXECUTION_PLAN.md`
- No file under `paper_final/` was modified by this step
