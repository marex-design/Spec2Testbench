# Publication cleanup log

Date: 2026-07-15

## Preserved

The framework source, tests, ACP-28 benchmark, experiment definitions, canonical nominal campaign, evidence ledger, result summaries, and final manuscript were preserved. Raw result and campaign files were not edited.

## Removed from the publication surface

- Root `.tmp_sky130*` files were deleted because they were temporary model-discovery snapshots and were not referenced by tracked source code.
- Python caches, pytest caches, manuscript auxiliary build files, and generated waveform-test directories were removed locally and remain ignored.
- Large non-canonical campaign workspaces remain available locally but are ignored to prevent accidental publication of raw waveforms or provisional evidence.
- Regenerable controlled-violation case expansions under `experiments/controlled_violations/generated_cases/` remain local; the generation scripts and campaign manifests are versioned instead.

## Archived

- `docs/spec2testbench_ieee_conference.tex` and `docs/paper_draft.md` were moved under `archive/obsolete_manuscript/` because they contain superseded claims.
- The intermediate `paper/` directory was moved to the same archive because `paper_final/` is the canonical manuscript surface.
- Superseded `paper_final/` scaffolds were archived, including the empty bibliography, old two-case statistics generator, and pre-reference audit notes. Their replacements are the canonical ledger, final claim matrix, revised bibliography, and updated missing-reference report.

## Metadata and naming

- All active source, documentation, and generated benchmark testbench files now use the official name `Spec2Testbench`.
- Package metadata no longer contains placeholder author information.
- `LICENSE`, `CITATION.cff`, `pyproject.toml`, and `MANIFEST.in` were added for source publication.

## Evidence policy

Only compact files explicitly referenced by the canonical evidence ledger should be force-added from ignored `results/` or `reports/` directories. New campaign runs must use new timestamps and must not overwrite canonical evidence.
