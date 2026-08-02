# Authoritative State Decision

Date: 2026-07-25

## Option A: frozen commit `2678818e33972ae8612aa395f329501e85a3f98d`

Advantages:
- Starts from a clean, reviewable, reproducible baseline.
- Avoids inheriting the 784 tracked deletions and the ambiguous benchmark/output state of the loaded worktree.
- Avoids automatically inheriting paper-manuscript edits from the current `HEAD` commit.

Risks:
- Loses all uncommitted work unless selectively re-applied after validation.
- Requires fresh implementation or selective carry-over of any genuinely needed framework/test fixes.

Files concerned by the committed delta between the frozen commit and current `HEAD`:
- `M	paper_final/main.tex`
- `M	paper_final/sections/experimental_methodology.tex`
- `M	paper_final/sections/method_revised.tex`
- `M	paper_final/sections/results_revised.tex`
- `M	paper_final/tables/results_tables.tex`
- `M	reproduce_paper.py`
- `M	scripts/freeze_paper_public_evidence.py`
- `M	spec2testbench/application/usecases/run_verification.py`
- `M	spec2testbench/infrastructure/simulator/pyspice_simulator.py`
- `A	tools/generate_reviewer_phase0_audit.py`

## Option B: current modified code after local checkpoint

Advantages:
- Preserves every local modification immediately available in the loaded worktree.
- Minimizes short-term reimplementation effort if every local change were already validated.

Risks:
- The local state is not clean: it contains 784 tracked deletions, many generated-artifact deletions, and benchmark/paper paths in an ambiguous state.
- The current `HEAD` is one commit ahead of the frozen baseline and already includes paper-related changes, which is incompatible with the requested scientific stabilization posture.
- Carrying this state forward would blur the boundary between framework repair, evidence generation, and manuscript work.

## Changes that would be lost with Option A

- The committed delta listed above.
- All preexisting dirty-worktree changes recorded in `preexisting_change_classification.csv`, except any later selective reapplication.

## Changes that should be re-applied if and only if validated

- `scripts/build_final_implementation_registry_artifacts.py`
- `scripts/build_frozen_pilot_v3.py`
- `scripts/create_reference_28_netlists.py`
- `scripts/deepseek_live_lib.py`
- `scripts/generate_reference_28_specs.py`
- `scripts/knowledge_stub_lib.py`
- `scripts/normalize_analogcoder_benchmark.py`
- `scripts/run_acp28_light_campaign.py`
- `scripts/run_deepseek_testbench_campaign.py`
- `scripts/run_reference_28_campaign.py`
- `spec2testbench/application/services/benchmark_deck_normalizer.py`
- `spec2testbench/application/services/canonical_harness.py`
- `spec2testbench/application/services/llm_metric_registry.py`
- `spec2testbench/application/services/testbench_plan_compiler.py`
- `spec2testbench/application/usecases/run_verification.py`
- `spec2testbench/config/settings.py`
- `spec2testbench/domain/entities/metric_coverage.py`
- `spec2testbench/infrastructure/simulator/pyspice_simulator.py`
- `spec2testbench/infrastructure/spec_checker/metric_extractor.py`
- `spec2testbench/infrastructure/spec_checker/spec_checker.py`
- `spec2testbench/infrastructure/testbench/testbench_generator.py`
- `spec2testbench/infrastructure/waveform_checker/waveform_plotter.py`
- `tests/integration/test_real_pipeline_ngspice.py`
- `tests/test_benchmark_deck_normalizer.py`
- `tests/test_ground_truth_artifacts.py`
- `tests/test_llm_planning_components.py`
- `tests/test_multimodal_client.py`
- `tests/test_pyspice_native_backend_selection.py`
- `tests/test_reference_28_coverage.py`
- `tests/test_verification_pipeline.py`
- `tests/test_waveform_plotter.py`

Benchmark assets, generated outputs, paper files, and unexplained deletions should not be re-applied automatically.

## Final recommendation

Create a clean worktree from the frozen commit, then re-apply only explicitly validated code and test changes.

This matches the default recommendation from the stabilization brief and is the only defensible base for subsequent correction/testing work.
