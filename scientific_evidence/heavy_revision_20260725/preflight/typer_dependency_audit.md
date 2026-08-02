# Typer Dependency Audit

Date: 2026-07-25
Clean scientific worktree: `E:\my_organisation\Memoire Maruba\code\Spec2Testbench-scientific-clean`
Branch: `codex/scientific-evidence-clean-20260725`
Base commit: `2678818e33972ae8612aa395f329501e85a3f98d`

## Files inspected

- `pyproject.toml`: build backend only; no runtime dependency declarations.
- `setup.py`: authoritative runtime dependency declaration and console entry point.
- `setup.cfg`: absent.
- `requirements*.txt`: absent.
- `spec2testbench/presentation/cli/main.py`: direct `import typer` at module import time.
- `tests/test_cli_plan_and_categories.py`: CLI test module gated by `pytest.importorskip("typer.testing")`.
- `tests/test_scientific_workflow_guards.py`: two CLI tests gated by `pytest.importorskip("typer")`.

## Findings

- `typer` is a mandatory runtime dependency for the public CLI, not an optional extra.
- `rich` is also a mandatory runtime dependency for the CLI because `main.py` imports `rich.console`, `rich.progress`, and `rich.table` at module import time.
- The public console script is declared in `setup.py` as:
  - `spec2testbench=spec2testbench.presentation.cli.main:app`
- Before installation, the environment had no importable `typer`, no importable `rich`, and no `spec2testbench` command on `PATH`.
- The authoritative dependency metadata already declared `typer>=0.9` and `rich>=13.0` in `install_requires`, so the issue was not a missing dependency declaration in the repository.
- Root cause: the local Python environment was not installed from the authoritative package metadata.

## Decision

- Dependency classification: `typer` is a mandatory runtime dependency.
- Authoritative file: `setup.py`.
- Dependency-file modification required: no.
- Environment installation required: yes.
- Installation method used: `python -m pip install -e .`
- Resulting validated `typer` version: `0.27.0`.
- Resulting validated state: `typer`, `rich`, and the public `spec2testbench` console script are available.

## Validation after installation

- `import typer`: PASS
- `import rich`: PASS
- `import spec2testbench.presentation.cli.main`: PASS
- `Get-Command spec2testbench`: PASS
- CLI-focused pytest rerun: see `cli_tests_after_typer.txt`

## Packaging policy conclusion

No dependency policy change was made during this audit. The repository already declared the required CLI dependencies in its authoritative runtime metadata. The corrective action was to install the package environment from that metadata, then rerun the CLI coverage.
