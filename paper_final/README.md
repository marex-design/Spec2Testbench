# Final manuscript and evidence

`main.tex` is the canonical manuscript entry point. It uses the official `IEEEtran` class when available and falls back to the explicitly named `IEEEtran_compat.cls` only for local compilation environments where IEEEtran is absent.

Scientific values in the manuscript should now be checked first against the frozen public bundle in `paper_final/evidence_freeze_20260724/`, especially:

- `nominal/freeze_manifest.json`
- `nominal/nominal_summary.json`
- `nominal/metric_results.csv`
- `nominal/simulability_vs_compliance.csv`
- `controlled/frozen_pilot_metrics_v3.json`
- `tests/test_results.json`

Regenerate the cited paper bundle from the repo root with:

```bash
python reproduce_paper.py
```

This replay entrypoint materializes the authoritative paper workflow only: the public deterministic CLI verification path (`spec2testbench verify --no-llm` with `SPEC2TESTBENCH_DISABLE_PYSPICE=1`), plus the frozen test summary and retained controlled artifacts copied into the cited bundle.

The older audit ledgers such as `canonical_evidence_ledger.csv` and `canonical_results_summary.md` remain useful for historical traceability, but the manuscript itself should point to the frozen bundle above rather than to stale or missing `results/*.json` paths.

Compile from this directory with:

```bash
pdflatex -interaction=nonstopmode -output-directory=build main.tex
bibtex build/main
pdflatex -interaction=nonstopmode -output-directory=build main.tex
pdflatex -interaction=nonstopmode -output-directory=build main.tex
```

For final submission, install the publisher-provided IEEEtran class and inspect the resulting PDF for table width, figure placement, citations, and font embedding.
