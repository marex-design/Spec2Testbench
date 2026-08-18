<#
Run this script from the repository root in PowerShell to create a virtualenv,
install Python dependencies and run the benchmark pipeline (ngspice must be installed).

Usage:
  Open PowerShell as normal (or admin if you want automatic ngspice install)
  .\scripts\run_all.ps1        # normal run
  .\scripts\run_all.ps1 -SkipNgspiceInstall  # skip attempting to install ngspice

Note: Automatic installation of ngspice via Chocolatey requires administrator rights.
#>

param(
    [switch]$SkipNgspiceInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "== Spec2Testbench reproducible run =="

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment .venv..."
    python -m venv .venv
} else {
    Write-Host "Virtualenv .venv already exists."
}

Write-Host "Activating virtualenv..."
. .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip and installing package..."
python -m pip install --upgrade pip
python -m pip install -e .

Write-Host "Ensuring PySpice is installed (used for more advanced parsing)..."
python -m pip install PySpice || Write-Host "PySpice install may have failed; continue anyway."

Write-Host "Checking ngspice in PATH..."
try {
    $ng = Get-Command ngspice -ErrorAction Stop
    Write-Host "ngspice found:" $ng.Path
    & ngspice --version
} catch {
    Write-Host "ngspice not found in PATH."
    if (-not $SkipNgspiceInstall) {
        if (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Host "Chocolatey detected. Installing ngspice (requires admin)..."
            choco install ngspice -y
            Write-Host "After installation, re-open PowerShell or ensure ngspice is in PATH."
        } else {
            Write-Host "To install ngspice on Windows:"
            Write-Host "  1) Install Chocolatey: https://chocolatey.org/install"
            Write-Host "  2) choco install ngspice -y"
            Write-Host "Or download from: https://ngspice.sourceforge.io/"
        }
    } else {
        Write-Host "Skipped ngspice installation (SkipNgspiceInstall set)."
    }
}

Write-Host "Running netlist checks (ngspice batch)"
python scripts/check_35_netlists_ngspice.py

Write-Host "Aggregating metrics (generates results/metrics.csv)"
python scripts/aggregate_metrics.py

Write-Host "Analyzing metrics and generating figures"
python scripts/analyze_metrics.py

Write-Host "Generating benchmark summary (results/benchmark_summary.md)"
python scripts/generate_benchmark_report.py

Write-Host "Generating coverage matrix (results/coverage_matrix.csv)"
python scripts/generate_coverage_matrix.py

Write-Host "Done. Results are in the results/ directory."
Write-Host " - Logs: results/ngspice_logs/"
Write-Host " - Raw files: results/raw/"
Write-Host " - Metrics: results/metrics.csv"
Write-Host " - Figures: results/figures/"
Write-Host " - Summary: results/benchmark_summary.md"
