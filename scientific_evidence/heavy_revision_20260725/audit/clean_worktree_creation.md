# Clean Worktree Creation

Date: 2026-07-25

## Command

`git worktree add -b codex/scientific-evidence-clean-20260725 ..\\Spec2Testbench-scientific-clean 2678818e33972ae8612aa395f329501e85a3f98d`

## Result

- Worktree path: `E:\my_organisation\Memoire Maruba\code\Spec2Testbench-scientific-clean`
- Branch: `codex/scientific-evidence-clean-20260725`
- Commit: `
2678818e33972ae8612aa395f329501e85a3f98d
`
- Initial `git status --short`: clean (empty output)
- `paper_final/` matches `HEAD`: 
true

## Validation notes

- Expected files present:
- `spec2testbench/presentation/cli/main.py`: true
- `spec2testbench/application/usecases/run_verification.py`: true
- `paper_final/main.tex`: true
- `paper_final/references_revised.bib`: true

- Git ownership validation in this environment required a per-process safe-directory override for follow-up Git inspection commands.
- No global Git configuration was modified for this workaround.
- No file under `paper_final/` was modified during creation or validation of the clean worktree.

## Next stance

- No legacy outputs, reports, caches, or manuscript files will be copied into the clean worktree.
- Baseline tests will run in the clean worktree before any correction is applied.
