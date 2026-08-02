# Preexisting Changes Report

Date: 2026-07-25

## Snapshot basis

- Source snapshot: `scientific_evidence/heavy_revision_20260725/audit/worktree_forensics/initial_status_short.txt`
- Snapshot timing: captured before writing the forensic archive into the loaded worktree.
- Total entries in snapshot: 
848
- Suspected preexisting entries: 
847
- Entries known not to be preexisting: 
1
- Non-preexisting path identified: `
EXECUTION_PLAN.md
`

## Counts requested by the stabilization brief

- Deletions under `paper_final/`: 
296
- Changes flagged as generated outputs or derived artifacts: 
614
- Changes touching likely source code: 
34
- Changes touching tests: 
9
- Changes touching benchmarks or benchmark specs: 
356
- Total preexisting deletions: 
784
- Total preexisting modifications: 
58
- Total preexisting untracked paths: 
5

## Directory distribution

- autres: 3
- benchmark: 242
- examples: 115
- paper_final: 296
- results: 150
- scripts: 20
- spec2testbench: 12
- tests: 9

## Interpretation

- The loaded worktree was already forensically unstable before this stabilization phase: most preexisting changes are tracked deletions, not cleanly reviewable edits.
- `paper_final/` deletions are numerous and must not be treated as intentional. They are evidence of a broken scientific worktree, not a basis for experimentation.
- Generated/derived deletions are concentrated in `benchmarks_normalized/` and `paper_final/evidence_freeze_20260724/`; these are not trustworthy as reusable evidence until provenance is re-established.
- The only class of changes that looks plausibly reusable after validation is modified source/test/script content outside the paper and outside generated outputs.

## Changes that seem necessary for the current framework

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

These paths are only candidates for selective reapplication. None should be copied blindly, and none override the default recommendation to rebuild from the frozen commit.

## Changes that remain impossible to interpret automatically

- `README.md`
- `benchmark/README.md`
- `benchmark/analogcoder_pro/p01_amplifier.cir`
- `benchmark/analogcoder_pro/p02_amplifier.cir`
- `benchmark/analogcoder_pro/p03_amplifier.cir`
- `benchmark/analogcoder_pro/p04_amplifier.cir`
- `benchmark/analogcoder_pro/p05_amplifier.cir`
- `benchmark/analogcoder_pro/p06_inverter.cir`
- `benchmark/analogcoder_pro/p07_inverter.cir`
- `benchmark/analogcoder_pro/p08_currentmirror.cir`
- `benchmark/analogcoder_pro/p09_comparator.cir`
- `benchmark/analogcoder_pro/p10_lowpass.cir`
- `benchmark/analogcoder_pro/p11_highpass.cir`
- `benchmark/analogcoder_pro/p12_bandpass.cir`
- `benchmark/analogcoder_pro/p13_bandstop.cir`
- `benchmark/analogcoder_pro/p14_amplifier.cir`
- `benchmark/analogcoder_pro/p15_amplifier.cir`
- `benchmark/analogcoder_pro/p16_opamp.cir`
- `benchmark/analogcoder_pro/p17_currentmirror.cir`
- `benchmark/analogcoder_pro/p18_opamp.cir`

- Any tracked deletion without an accompanying rationale is ambiguous by definition.
- Benchmark netlist/spec changes require human provenance review because they can change the scientific meaning of later campaigns.
- All `paper_final/` paths remain frozen and excluded from framework repair work.

