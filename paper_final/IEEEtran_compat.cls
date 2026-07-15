\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{IEEEtran_compat}[2026/07/15 Explicit local compilation fallback]
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax
\LoadClass[10pt,twocolumn]{article}
\RequirePackage[margin=0.72in]{geometry}
\setlength{\columnsep}{0.22in}
