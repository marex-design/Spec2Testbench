# Final manuscript and evidence

`main.tex` is the canonical manuscript entry point. It uses the official `IEEEtran` class when available and falls back to the explicitly named `IEEEtran_compat.cls` only for local compilation environments where IEEEtran is absent.

Scientific values must be checked against `canonical_evidence_ledger.csv` and `canonical_results_summary.md`. Files marked obsolete or conflicted in the ledger are not authorized as current manuscript evidence.

Compile from this directory with:

```bash
pdflatex -interaction=nonstopmode -output-directory=build main.tex
bibtex build/main
pdflatex -interaction=nonstopmode -output-directory=build main.tex
pdflatex -interaction=nonstopmode -output-directory=build main.tex
```

For final submission, install the publisher-provided IEEEtran class and inspect the resulting PDF for table width, figure placement, citations, and font embedding.
