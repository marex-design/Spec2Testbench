# Compilation report

The complete `pdflatex -> bibtex -> pdflatex -> pdflatex` sequence produced a 10-page PDF. The publication copy is `paper_final/Spec2Testbench_manuscript.pdf`; transient auxiliary files remain under the ignored `paper_final/build/` directory.

The official `IEEEtran.cls` is not installed in this local MiKTeX environment. `main.tex` therefore selected the explicitly named `IEEEtran_compat.cls` fallback. A final publisher build must be repeated with the official IEEEtran class.

The final log contains no unresolved citations, unresolved references, or overfull boxes. Underfull-box typography warnings remain in narrow columns, especially around long evidence identifiers. MiKTeX returns a non-zero process code after PDF generation because it cannot write its user-level `pdflatex.log` and `bibtex.log`; this environment error does not prevent output generation.
