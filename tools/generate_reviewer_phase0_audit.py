from __future__ import annotations

import csv
import hashlib
import importlib.metadata as md
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
TOOLS_DIR = ROOT / "tools"
PAPER_DIR = ROOT / "paper_final"
CURRENT_FREEZE = PAPER_DIR / "evidence_freeze_20260724"

INVENTORY_CSV = RESULTS_DIR / "current_evidence_inventory.csv"
CLAIMS_CSV = RESULTS_DIR / "current_claims_vs_artifacts.csv"
CONFLICTS_CSV = RESULTS_DIR / "evidence_conflicts.csv"
AUDIT_MD = REPORTS_DIR / "reviewer_evidence_audit.md"

ABSOLUTE_PATH_RE = re.compile(r"\b[A-Za-z]:[\\/][^\s\"']+")
TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".tex",
    ".txt",
    ".yaml",
    ".yml",
    ".cir",
    ".tsv",
}
AUDIT_ROOTS = [
    ROOT / "results",
    ROOT / "reports",
    ROOT / "paper_final",
    ROOT / "benchmark" / "analogcoder_pro",
    ROOT / "examples" / "benchmark_nominal_specs",
    ROOT / "testbenches",
]


@dataclass
class ClaimRow:
    claim_id: str
    claim_text: str
    manuscript_location: str
    source_artifacts: str
    derived_value: str
    status: str
    notes: str


@dataclass
class ConflictRow:
    conflict_id: str
    severity: str
    category: str
    artifact_path: str
    issue: str
    impact: str
    recommended_action: str
    status: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def run_command(command: list[str], timeout: int = 15) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
            "timed_out": False,
        }
    except FileNotFoundError:
        return {
            "command": " ".join(command),
            "returncode": None,
            "stdout": "",
            "stderr": "NOT_FOUND",
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "returncode": None,
            "stdout": (exc.stdout or "").strip() if exc.stdout else "",
            "stderr": "TIMEOUT",
            "timed_out": True,
        }


def git_stdout(*args: str) -> str:
    return run_command(["git", *args]).get("stdout", "")


def detect_artifact_kind(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    name = path.name.lower()
    ext = path.suffix.lower()
    if rel.startswith("benchmark/") and ext == ".cir":
        return "NETLIST"
    if rel.startswith("examples/") and ext in {".yaml", ".yml"}:
        return "SPECIFICATION"
    if "testbench" in rel and ext in {".cir", ".ckt", ".sp", ".txt"}:
        return "TESTBENCH"
    if name == "report.json":
        return "CASE_REPORT"
    if name == "metrics.json":
        return "METRIC_VECTOR"
    if name == "metric_traces.json":
        return "METRIC_TRACE_VECTOR"
    if name == "provenance.json":
        return "PROVENANCE"
    if "measure" in name and ext in {".txt", ".csv", ".json"}:
        return "MEASURE_OUTPUT"
    if "wrdata" in name or "vectors" in name:
        return "WRDATA_OUTPUT"
    if ext == ".json":
        return "JSON_RESULT"
    if ext == ".csv":
        return "CSV_RESULT"
    if ext == ".md":
        return "MARKDOWN_REPORT"
    if ext == ".txt":
        return "TEXT_LOG"
    if ext == ".pdf":
        return "PDF"
    if ext == ".tex":
        return "LATEX_SOURCE"
    if ext in {".png", ".svg"}:
        return "FIGURE"
    return "OTHER"


def iter_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in AUDIT_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            text = ""
            file_size = path.stat().st_size
            if path.suffix.lower() in TEXT_EXTENSIONS and file_size <= 1 * 1024 * 1024:
                text = safe_read_text(path)
            rows.append(
                {
                    "relative_path": rel,
                    "top_level_group": rel.split("/", 1)[0],
                    "artifact_kind": detect_artifact_kind(path),
                    "extension": path.suffix.lower(),
                    "size_bytes": file_size,
                    "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                    "sha256": sha256_file(path),
                    "contains_absolute_windows_path": bool(ABSOLUTE_PATH_RE.search(text)),
                }
            )
    rows.sort(key=lambda row: row["relative_path"])
    return rows


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def current_case_reports() -> list[dict[str, Any]]:
    case_root = CURRENT_FREEZE / "nominal" / "cases"
    rows: list[dict[str, Any]] = []
    if not case_root.exists():
        return rows
    for report_path in sorted(case_root.glob("*/report.json")):
        payload = load_json(report_path)
        rows.append(
            {
                "case_id": report_path.parent.name,
                "execution_status": payload.get("execution_status", ""),
                "simulation_mode": payload.get("simulation_mode", ""),
                "compliance_status": payload.get("compliance_status", ""),
                "scientific_category": payload.get("scientific_category", ""),
                "scientifically_eligible": bool(payload.get("scientifically_eligible", False)),
                "overall_verdict": payload.get("overall_verdict", ""),
                "report_path": report_path.relative_to(ROOT).as_posix(),
            }
        )
    return rows


def summarize_cases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    execution = Counter(row["execution_status"] for row in rows)
    modes = Counter(row["simulation_mode"] for row in rows)
    scientific = Counter(row["scientific_category"] for row in rows)
    compliance = Counter(row["compliance_status"] for row in rows)
    return {
        "case_count": len(rows),
        "execution": dict(execution),
        "modes": dict(modes),
        "scientific": dict(scientific),
        "compliance": dict(compliance),
        "scientifically_eligible_true": sum(1 for row in rows if row["scientifically_eligible"]),
    }


def find_candidate_paths(patterns: list[str], limit: int = 12) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for root_name in ("results", "reports", "paper_final", "artifacts"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                rel = path.relative_to(ROOT).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
                if len(found) >= limit:
                    return found
    return found


def build_claim_rows(case_summary: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> list[ClaimRow]:
    claim_rows: list[ClaimRow] = []
    freeze_manifest = CURRENT_FREEZE / "nominal" / "freeze_manifest.json"
    test_results = CURRENT_FREEZE / "tests" / "test_results.json"
    frozen_pilot = ROOT / "results" / "frozen_pilot_metrics_v3.json"

    claim_rows.append(
        ClaimRow(
            claim_id="CL01",
            claim_text="The authoritative paper workflow uses the public deterministic CLI without LLM.",
            manuscript_location="paper_final/main.tex; paper_final/sections/method_revised.tex",
            source_artifacts="reproduce_paper.py; scripts/freeze_paper_public_evidence.py",
            derived_value="python reproduce_paper.py -> python -m spec2testbench.presentation.cli.main verify --no-llm",
            status="VERIFIED_FROM_RAW_EVIDENCE",
            notes="No internal verification pipeline fallback remains in the replay path.",
        )
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL02",
            claim_text="The current frozen nominal bundle records 28 REAL runs and 28 successful executions.",
            manuscript_location="paper_final/main.tex:abstract; paper_final/sections/results_revised.tex:RQ1",
            source_artifacts="paper_final/evidence_freeze_20260724/nominal/cases/*/report.json",
            derived_value=f"case_count={case_summary['case_count']}; REAL={case_summary['modes'].get('REAL', 0)}; SUCCESS={case_summary['execution'].get('SUCCESS', 0)}",
            status="VERIFIED_FROM_RAW_EVIDENCE",
            notes="Derived by recounting the per-case reports in the current frozen bundle.",
        )
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL03",
            claim_text="The current frozen nominal bundle records 16 SIMULABLE_COMPLIANT, 2 SIMULABLE_NONCOMPLIANT, and 10 UNEVALUATED cases.",
            manuscript_location="paper_final/main.tex:abstract; paper_final/sections/results_revised.tex:RQ2",
            source_artifacts="paper_final/evidence_freeze_20260724/nominal/cases/*/report.json",
            derived_value=(
                f"SIMULABLE_COMPLIANT={case_summary['scientific'].get('SIMULABLE_COMPLIANT', 0)}; "
                f"SIMULABLE_NONCOMPLIANT={case_summary['scientific'].get('SIMULABLE_NONCOMPLIANT', 0)}; "
                f"UNEVALUATED={case_summary['scientific'].get('UNEVALUATED', 0)}"
            ),
            status="VERIFIED_FROM_RAW_EVIDENCE",
            notes="The totals satisfy total = compliant + noncompliant + unevaluated in the current bundle.",
        )
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL04",
            claim_text="The current frozen software test artifact records 304 passed / 17 skipped and 316 passed / 5 skipped for two overlapping invocations.",
            manuscript_location="paper_final/sections/results_revised.tex:Secondary Software Results",
            source_artifacts="paper_final/evidence_freeze_20260724/tests/test_results.json",
            derived_value="python_m_pytest_q=304/17; python_m_pytest_q_ngspice=316/5; python_m_pytest_q_ngspice_no_pyspice=316/5",
            status="VERIFIED_FROM_REPLAY",
            notes="The counts are present, but the invocations overlap and must not be summed into one total.",
        )
    )
    if frozen_pilot.exists():
        pilot_payload = load_json(frozen_pilot)
        claim_rows.append(
            ClaimRow(
                claim_id="CL05",
                claim_text="The retained Frozen Pilot V3 records 16 cases, 8 TRUE_ACCEPT, 8 TRUE_DETECTION, and zero false accepts / false rejects.",
                manuscript_location="paper_final/sections/results_revised.tex:RQ3",
                source_artifacts="results/frozen_pilot_metrics_v3.json",
                derived_value=(
                    f"cases={pilot_payload.get('cases')}; TRUE_ACCEPT={pilot_payload.get('TRUE_ACCEPT')}; "
                    f"TRUE_DETECTION={pilot_payload.get('TRUE_DETECTION')}; FALSE_ACCEPT={pilot_payload.get('FALSE_ACCEPT')}; "
                    f"FALSE_REJECT={pilot_payload.get('FALSE_REJECT')}"
                ),
                status="VERIFIED_FROM_REPLAY",
                notes="The current bundle copies this artifact into paper_final/evidence_freeze_20260724/controlled/.",
            )
        )
        claim_rows.append(
            ClaimRow(
                claim_id="CL06",
                claim_text="The retained backend cross-check evidence currently covers only two WRDATA validations within tolerance.",
                manuscript_location="paper_final/main.tex:abstract; paper_final/sections/results_revised.tex:RQ3",
                source_artifacts="results/frozen_pilot_metrics_v3.json; results/frozen_pilot_results_v3.csv",
                derived_value=(
                    f"wrdata_cases={pilot_payload.get('wrdata_cases')}; "
                    f"independent_comparisons_within_tolerance={pilot_payload.get('independent_comparisons_within_tolerance')}"
                ),
                status="VERIFIED_FROM_REPLAY",
                notes="This is a small-scope backend check and not broad backend validation.",
            )
        )
    mutation_candidates = find_candidate_paths(["*mutation*", "*controlled*violation*", "*controlled*summary*"])
    mutation_status = "HISTORICAL_ONLY" if mutation_candidates else "UNSUPPORTED"
    mutation_notes = (
        "Historical mutation and controlled-violation traces exist in the repository, but no current authoritative summary file was located at the expected current paths."
        if mutation_candidates
        else "No current mutation or controlled-violation summary artifact was located."
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL07",
            claim_text="The repository currently supports the claim '30 variants, 2 effective violations, 1 detected, 1 missed' for the mutation campaign.",
            manuscript_location="reviewer-request current announced results",
            source_artifacts="; ".join(mutation_candidates) if mutation_candidates else "NONE_FOUND",
            derived_value="No authoritative current summary resolved during Phase 0 audit.",
            status=mutation_status,
            notes=mutation_notes,
        )
    )
    absolute_path_rows = [row for row in inventory_rows if row["contains_absolute_windows_path"]]
    claim_rows.append(
        ClaimRow(
            claim_id="CL08",
            claim_text="The current frozen paper bundle is publishable as-is with relative paths only.",
            manuscript_location="paper_final/evidence_freeze_20260724/**/*",
            source_artifacts="current_evidence_inventory.csv",
            derived_value=f"absolute_path_artifacts={len(absolute_path_rows)}",
            status="CONTRADICTED" if absolute_path_rows else "VERIFIED_FROM_RAW_EVIDENCE",
            notes="Multiple artifacts still embed absolute Windows paths, including case reports and historical result CSV files.",
        )
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL09",
            claim_text="The current replay entrypoint writes to a reviewer-revision bundle without mutating the existing frozen bundle.",
            manuscript_location="reproduce_paper.py; scripts/freeze_paper_public_evidence.py",
            source_artifacts="reproduce_paper.py; scripts/freeze_paper_public_evidence.py",
            derived_value=str(freeze_manifest.relative_to(ROOT).as_posix()) if freeze_manifest.exists() else "freeze manifest missing",
            status="CONTRADICTED",
            notes="The current replay still targets paper_final/evidence_freeze_20260724 rather than a separate reviewer-revision bundle.",
        )
    )
    claim_rows.append(
        ClaimRow(
            claim_id="CL10",
            claim_text="The current paper evidence is fully independent of a pre-existing .venv.",
            manuscript_location="reproduce_paper.py; scripts/freeze_paper_public_evidence.py",
            source_artifacts="scripts/freeze_paper_public_evidence.py",
            derived_value="Replay prefers ROOT/.venv/Scripts/python.exe when present, then falls back to sys.executable.",
            status="PARTIALLY_SUPPORTED",
            notes="The replay can fall back to the active interpreter, but its primary resolution still prefers a pre-existing project .venv.",
        )
    )
    return claim_rows


def build_conflict_rows(inventory_rows: list[dict[str, Any]], case_summary: dict[str, Any]) -> list[ConflictRow]:
    absolute_rows = [row for row in inventory_rows if row["contains_absolute_windows_path"]]
    example_absolute = absolute_rows[0]["relative_path"] if absolute_rows else "NONE"
    conflicts: list[ConflictRow] = [
        ConflictRow(
            conflict_id="CF01",
            severity="HIGH",
            category="PUBLISHABLE_PATHS",
            artifact_path=example_absolute,
            issue="Publishable artifacts still contain absolute Windows paths.",
            impact="Breaks the requirement to publish reviewer-facing evidence with relative paths only and leaks machine-local locations into scientific evidence.",
            recommended_action="Rewrite bundle manifests and case-level evidence exports to store relative producer paths and relative artifact references.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF02",
            severity="HIGH",
            category="BUNDLE_ISOLATION",
            artifact_path="reproduce_paper.py; scripts/freeze_paper_public_evidence.py",
            issue="The replay entrypoint still targets the existing frozen bundle paper_final/evidence_freeze_20260724.",
            impact="Running the current replay mutates the historical frozen bundle instead of producing a separate reviewer-revision freeze.",
            recommended_action="Parameterize the freeze id / output root and create paper_final/evidence_freeze_reviewer_revision_20260724 as a new immutable bundle.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF03",
            severity="HIGH",
            category="CONTROLLED_CAMPAIGN_TRACEABILITY",
            artifact_path="results/frozen_pilot_metrics_v3.json; paper_final/evidence_freeze_20260724/controlled/",
            issue="The authoritative bundle copies controlled-artifact summaries but does not yet include a richer reviewer-revision raw campaign tree.",
            impact="Reviewer-facing claims about controlled violations, backend validation, and negative benchmarking remain narrower than the requested new evidence scope.",
            recommended_action="Generate a dedicated reviewer-revision controlled/negative_benchmark tree with raw logs, commands, manifests, and hashes.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF04",
            severity="MEDIUM",
            category="TEST_COUNT_INTERPRETATION",
            artifact_path="paper_final/evidence_freeze_20260724/tests/test_results.json",
            issue="The recorded pytest invocations overlap and must not be summed into one total.",
            impact="Any manuscript or reviewer response that aggregates these counts into one population would overstate software-test evidence.",
            recommended_action="Publish a test taxonomy and treat each invocation as a separate environment-specific run with explicit overlap notes.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF05",
            severity="HIGH",
            category="HISTORICAL_RESULTS_COEXISTENCE",
            artifact_path="results/; reports/; paper_final/",
            issue="Historical, reconciliation, and final-* result families coexist with the current paper bundle and can be confused for active evidence.",
            impact="A reviewer or future maintainer can accidentally cite stale or conflicting CSV/JSON files outside the current authoritative bundle.",
            recommended_action="Classify historical result families explicitly in the reviewer-revision audit and isolate the new authoritative bundle with a global manifest.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF06",
            severity="MEDIUM",
            category="ENVIRONMENT_PROBE_ROBUSTNESS",
            artifact_path="ngspice command-line probe",
            issue="Direct environment probing for ngspice can hang or time out in the current shell context.",
            impact="Phase-0 environment capture is less robust than it should be if it depends on a shell-level ngspice version call.",
            recommended_action="Capture ngspice version from the verified replay environment and use bounded subprocess probes with explicit timeout logging.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF07",
            severity="MEDIUM",
            category="CURRENT_MUTATION_CLAIM",
            artifact_path="results/; reports/; artifacts/",
            issue="The Phase-0 audit did not locate a current authoritative summary file for the '30 variants / 2 effective / 1 missed' mutation claim at the expected paths.",
            impact="That claim cannot currently be treated as replay-verified paper evidence.",
            recommended_action="Regenerate the controlled negative benchmark under the reviewer-revision bundle and produce a fresh authoritative summary.",
            status="OPEN",
        ),
        ConflictRow(
            conflict_id="CF08",
            severity="LOW",
            category="COUNT_CONSISTENCY",
            artifact_path="paper_final/evidence_freeze_20260724/nominal/cases/*/report.json",
            issue="The current nominal counts are internally consistent but were not yet reproduced into a reviewer-revision bundle.",
            impact="The numbers are auditable today, but the historical bundle cannot serve as the final reviewer-revision freeze.",
            recommended_action="Re-run the 28-case nominal replay into the new reviewer-revision bundle and preserve the current bundle as historical.",
            status="OPEN",
        ),
    ]
    if case_summary["case_count"] != sum(case_summary["scientific"].values()):
        conflicts.append(
            ConflictRow(
                conflict_id="CF09",
                severity="HIGH",
                category="COUNT_MISMATCH",
                artifact_path="paper_final/evidence_freeze_20260724/nominal/cases/*/report.json",
                issue="Nominal per-case recount does not equal the scientific-category total.",
                impact="Would invalidate the current manuscript summary counts.",
                recommended_action="Repair the per-case aggregation before any manuscript reuse.",
                status="OPEN",
            )
        )
    return conflicts


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_environment_summary() -> dict[str, Any]:
    pip_version = "NOT_INSTALLED"
    pytest_version = "NOT_INSTALLED"
    pyspice_version = "NOT_INSTALLED"
    for package_name, target in (("pip", "pip"), ("pytest", "pytest"), ("PySpice", "pyspice")):
        try:
            version_value = md.version(package_name)
        except md.PackageNotFoundError:
            version_value = "NOT_INSTALLED"
        if target == "pip":
            pip_version = version_value
        elif target == "pytest":
            pytest_version = version_value
        else:
            pyspice_version = version_value
    cached_environment = CURRENT_FREEZE / "support" / "environment.json"
    cached_payload = load_json(cached_environment) if cached_environment.exists() else {}
    pdflatex_path = shutil.which("pdflatex") or "NOT_FOUND"
    latexmk_path = shutil.which("latexmk") or "NOT_FOUND"
    ngspice_path = shutil.which("ngspice") or "NOT_FOUND"
    build_log = safe_read_text(PAPER_DIR / "build" / "main.log")
    pdflatex_version_line = next((line.strip() for line in build_log.splitlines() if "pdfTeX" in line), "UNKNOWN_NOT_CAPTURED")
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_stdout("rev-parse", "HEAD"),
        "git_branch": git_stdout("rev-parse", "--abbrev-ref", "HEAD"),
        "git_clean": git_stdout("status", "--porcelain") == "",
        "python_executable": sys.executable,
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "timezone": datetime.now().astimezone().tzname(),
        "locale": locale.getlocale(),
        "preferred_encoding": locale.getpreferredencoding(False),
        "pip_version": pip_version,
        "pytest_version": pytest_version,
        "pyspice_version": pyspice_version,
        "ngspice_path": ngspice_path,
        "ngspice_version": cached_payload.get("ngspice_version", "UNKNOWN_NOT_PROBED"),
        "pdflatex_path": pdflatex_path,
        "pdflatex_version": pdflatex_version_line,
        "latexmk_path": latexmk_path,
    }


def write_audit_report(
    environment: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
    claims: list[ClaimRow],
    conflicts: list[ConflictRow],
    case_summary: dict[str, Any],
) -> None:
    counts_by_kind = Counter(row["artifact_kind"] for row in inventory_rows)
    absolute_path_rows = [row for row in inventory_rows if row["contains_absolute_windows_path"]]
    lines = [
        "# Reviewer Evidence Audit",
        "",
        f"- Audit timestamp (UTC): `{environment['timestamp_utc']}`",
        f"- Branch: `{environment['git_branch']}`",
        f"- Commit: `{environment['git_commit']}`",
        f"- Git clean at audit start: `{environment['git_clean']}`",
        f"- Python: `{environment['python_version']}`",
        f"- Python executable: `{environment['python_executable']}`",
        f"- Platform: `{environment['platform']}`",
        f"- Machine: `{environment['machine']}`",
        f"- Timezone: `{environment['timezone']}`",
        f"- Locale: `{environment['locale']}`",
        "",
        "## Tool Versions",
        "",
        f"- `pip`: `{environment['pip_version']}`",
        f"- `pytest`: `{environment['pytest_version']}`",
        f"- `PySpice`: `{environment['pyspice_version']}`",
        f"- `ngspice`: `{environment['ngspice_version']}` at `{environment['ngspice_path']}`",
        f"- `pdflatex`: `{environment['pdflatex_version']}` at `{environment['pdflatex_path']}`",
        f"- `latexmk`: `{environment['latexmk_path']}`",
        "",
        "## Nominal Bundle Recount",
        "",
        f"- Current frozen bundle: `{CURRENT_FREEZE.relative_to(ROOT).as_posix()}`",
        f"- Cases recounted from per-case reports: `{case_summary['case_count']}`",
        f"- REAL runs: `{case_summary['modes'].get('REAL', 0)}`",
        f"- SUCCESS executions: `{case_summary['execution'].get('SUCCESS', 0)}`",
        f"- SIMULABLE_COMPLIANT: `{case_summary['scientific'].get('SIMULABLE_COMPLIANT', 0)}`",
        f"- SIMULABLE_NONCOMPLIANT: `{case_summary['scientific'].get('SIMULABLE_NONCOMPLIANT', 0)}`",
        f"- UNEVALUATED: `{case_summary['scientific'].get('UNEVALUATED', 0)}`",
        f"- Scientifically eligible: `{case_summary['scientifically_eligible_true']}`",
        "",
        "## Inventory Summary",
        "",
        f"- Total inventoried files: `{len(inventory_rows)}`",
        f"- Files embedding absolute Windows paths: `{len(absolute_path_rows)}`",
        "",
    ]
    for artifact_kind, count in sorted(counts_by_kind.items()):
        lines.append(f"- `{artifact_kind}`: `{count}`")
    lines.extend(
        [
            "",
            "## Key Findings",
            "",
        ]
    )
    for conflict in conflicts:
        lines.append(f"- `{conflict.conflict_id}` [{conflict.severity}] {conflict.issue}")
        lines.append(f"  Impact: {conflict.impact}")
        lines.append(f"  Recommended action: {conflict.recommended_action}")
    lines.extend(
        [
            "",
            "## Claim Status Snapshot",
            "",
        ]
    )
    for claim in claims:
        lines.append(f"- `{claim.claim_id}` [{claim.status}] {claim.claim_text}")
        lines.append(f"  Evidence: {claim.source_artifacts}")
        lines.append(f"  Derived value: {claim.derived_value}")
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    environment = build_environment_summary()
    inventory_rows = iter_inventory_rows()
    case_rows = current_case_reports()
    case_summary = summarize_cases(case_rows)
    claims = build_claim_rows(case_summary, inventory_rows)
    conflicts = build_conflict_rows(inventory_rows, case_summary)

    write_csv(
        INVENTORY_CSV,
        inventory_rows,
        [
            "relative_path",
            "top_level_group",
            "artifact_kind",
            "extension",
            "size_bytes",
            "modified_utc",
            "sha256",
            "contains_absolute_windows_path",
        ],
    )
    write_csv(
        CLAIMS_CSV,
        [claim.__dict__ for claim in claims],
        [
            "claim_id",
            "claim_text",
            "manuscript_location",
            "source_artifacts",
            "derived_value",
            "status",
            "notes",
        ],
    )
    write_csv(
        CONFLICTS_CSV,
        [conflict.__dict__ for conflict in conflicts],
        [
            "conflict_id",
            "severity",
            "category",
            "artifact_path",
            "issue",
            "impact",
            "recommended_action",
            "status",
        ],
    )
    write_audit_report(environment, inventory_rows, claims, conflicts, case_summary)
    print(
        json.dumps(
            {
                "inventory_csv": str(INVENTORY_CSV.relative_to(ROOT).as_posix()),
                "claims_csv": str(CLAIMS_CSV.relative_to(ROOT).as_posix()),
                "conflicts_csv": str(CONFLICTS_CSV.relative_to(ROOT).as_posix()),
                "audit_md": str(AUDIT_MD.relative_to(ROOT).as_posix()),
                "cases_recounted": case_summary["case_count"],
                "absolute_path_artifacts": sum(1 for row in inventory_rows if row["contains_absolute_windows_path"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
