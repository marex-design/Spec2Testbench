from __future__ import annotations

import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FREEZE_ID = "evidence_freeze_20260724"
FREEZE_ROOT = ROOT / "paper_final" / FREEZE_ID
NOMINAL_ROOT = FREEZE_ROOT / "nominal"
CASE_ROOT = NOMINAL_ROOT / "cases"
TEST_ROOT = FREEZE_ROOT / "tests"
CONTROLLED_ROOT = FREEZE_ROOT / "controlled"
SUPPORT_ROOT = FREEZE_ROOT / "support"
BENCH_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_nominal_specs"
MANIFEST_PATH = BENCH_DIR / "manifest.csv"
FROZEN_PILOT_FILES = [
    ROOT / "results" / "frozen_pilot_metrics_v3.json",
    ROOT / "results" / "frozen_pilot_results_v3.csv",
]


def ensure_dirs() -> None:
    for path in (FREEZE_ROOT, NOMINAL_ROOT, CASE_ROOT, TEST_ROOT, CONTROLLED_ROOT, SUPPORT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def latest_json_report(report_dir: Path) -> Path | None:
    candidates = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def resolve_python() -> Path:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    if sys.executable:
        return Path(sys.executable).resolve()
    return candidates[0]


PYTHON = resolve_python()
PYTEST_COMMAND = [str(PYTHON), "-m", "pytest", "-q"]


def resolve_cli_command() -> list[str]:
    return [str(PYTHON), "-m", "spec2testbench.presentation.cli.main", "verify"]


CLI_COMMAND = resolve_cli_command()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def git_short_head() -> str:
    return git_head()[:7]


def git_branch() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def ngspice_version() -> str:
    cached_environment = SUPPORT_ROOT / "environment.json"
    if cached_environment.exists():
        cached_payload = load_json(cached_environment)
        cached_value = str(cached_payload.get("ngspice_version", "")).strip()
        if cached_value:
            return cached_value
    try:
        completed = subprocess.run(
            ["ngspice", "-v"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "UNKNOWN_TIMEOUT"
    text = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line or "UNKNOWN"


def parse_pytest_counts(output: str) -> dict[str, int]:
    summary_line = ""
    for line in reversed(output.splitlines()):
        if any(token in line for token in ("passed", "failed", "skipped", "warning")):
            summary_line = line
            break
    counts = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0}
    for key in counts:
        match = re.search(rf"(\d+)\s+{key}", summary_line)
        if match:
            counts[key] = int(match.group(1))
    return counts


def run_pytest(label: str, env_overrides: dict[str, str]) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env.update(env_overrides)
    completed = subprocess.run(
        PYTEST_COMMAND,
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    write_text(TEST_ROOT / f"{label}.txt", output)
    return {
        "label": label,
        "command": " ".join(PYTEST_COMMAND),
        "env": env_overrides,
        "returncode": completed.returncode,
        **parse_pytest_counts(output),
    }


def run_case(
    manifest_row: dict[str, str],
    reuse_existing: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    spec_path = SPEC_DIR / manifest_row["spec"]
    netlist_path = BENCH_DIR / manifest_row["netlist"]
    case_id = netlist_path.stem
    case_dir = CASE_ROOT / case_id
    reports_dir = case_dir / "reports"
    stable_report_path = case_dir / "report.json"
    case_dir.mkdir(parents=True, exist_ok=True)

    command = CLI_COMMAND + [
        "--specs",
        str(spec_path.relative_to(ROOT)),
        "--netlist",
        str(netlist_path.relative_to(ROOT)),
        "--no-llm",
        "--format",
        "json",
        "--output",
        str(case_dir.relative_to(ROOT)),
    ]
    write_text(case_dir / "command.txt", " ".join(command) + "\n")
    shutil.copy2(spec_path, case_dir / spec_path.name)
    shutil.copy2(netlist_path, case_dir / netlist_path.name)

    completed_returncode: int
    if reuse_existing and stable_report_path.exists():
        report_data = load_json(stable_report_path)
        completed_returncode = 0 if report_data.get("overall_verdict") == "PASS" else 1
    else:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
        existing_reports = {path.resolve() for path in reports_dir.glob("*.json")}
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        completed_returncode = completed.returncode
        write_text(case_dir / "stdout.txt", completed.stdout or "")
        write_text(case_dir / "stderr.txt", completed.stderr or "")

        report_path = next(
            (
                path
                for path in sorted(reports_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
                if path.resolve() not in existing_reports
            ),
            None,
        )
        if report_path is None:
            raise RuntimeError(
                f"Public CLI replay did not produce a JSON report for {case_id}. "
                f"Return code={completed.returncode}."
            )

        shutil.copy2(report_path, stable_report_path)
        report_data = load_json(stable_report_path)

    write_json(case_dir / "metrics.json", report_data.get("metrics", []))
    write_json(case_dir / "metric_traces.json", report_data.get("metric_traces", []))
    write_json(case_dir / "provenance.json", report_data.get("provenance", {}))

    metric_traces = report_data.get("metric_traces", [])
    metric_rows: list[dict[str, Any]] = []
    for trace in metric_traces:
        metric_rows.append(
            {
                "case_id": case_id,
                "circuit_type": manifest_row["circuit_type"],
                "metric_name": trace.get("metric_name", ""),
                "status": trace.get("status", ""),
                "measured_value": trace.get("measured_value"),
                "unit": trace.get("unit", ""),
                "expected_operator": trace.get("expected_operator", ""),
                "expected_threshold": trace.get("expected_threshold"),
                "source_analysis": trace.get("source_analysis", ""),
                "measurement_backend": trace.get("measurement_backend", ""),
                "measurement_expression_id": trace.get("measurement_expression_id", ""),
                "input_node": trace.get("input_node", ""),
                "output_node": trace.get("output_node", ""),
                "error": trace.get("error"),
                "report_path": str((case_dir / "report.json").relative_to(ROOT)),
            }
        )

    case_row = {
        "case_id": case_id,
        "circuit_type": manifest_row["circuit_type"],
        "execution_status": report_data.get("execution_status", ""),
        "simulation_mode": report_data.get("simulation_mode", ""),
        "compliance_status": report_data.get("compliance_status", ""),
        "scientific_category": report_data.get("scientific_category", ""),
        "scientifically_eligible": report_data.get("scientifically_eligible", False),
        "measurement_backend": report_data.get("provenance", {}).get("measurement_backend", report_data.get("measurement_backend", "")),
        "overall_verdict": report_data.get("overall_verdict", ""),
        "terminal_status": report_data.get("terminal_status", ""),
        "failure_kind": report_data.get("failure_kind", ""),
        "metric_count": len(metric_traces),
        "failed_metric_count": sum(1 for trace in metric_traces if trace.get("status") == "FAIL"),
        "not_evaluated_metric_count": sum(1 for trace in metric_traces if trace.get("status") == "NOT_EVALUATED"),
        "report_path": str((case_dir / "report.json").relative_to(ROOT)),
        "exit_code": completed_returncode,
    }
    return case_row, metric_rows, report_data


def build_nominal_summary(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    execution_counts = Counter(str(row["execution_status"]) for row in case_rows)
    mode_counts = Counter(str(row["simulation_mode"]) for row in case_rows)
    compliance_counts = Counter(str(row["compliance_status"]) for row in case_rows)
    scientific_counts = Counter(str(row["scientific_category"]) for row in case_rows)
    backend_counts = Counter(str(row["measurement_backend"]) for row in case_rows)
    return {
        "cases": len(case_rows),
        "execution_status_counts": dict(execution_counts),
        "simulation_mode_counts": dict(mode_counts),
        "compliance_status_counts": dict(compliance_counts),
        "scientific_category_counts": dict(scientific_counts),
        "measurement_backend_counts": dict(backend_counts),
        "scientifically_eligible_true": sum(1 for row in case_rows if row["scientifically_eligible"]),
        "real_runs": mode_counts.get("REAL", 0),
        "successful": execution_counts.get("SUCCESS", 0),
        "simulable_compliant": scientific_counts.get("SIMULABLE_COMPLIANT", 0),
        "simulable_noncompliant": scientific_counts.get("SIMULABLE_NONCOMPLIANT", 0),
        "unevaluated": scientific_counts.get("UNEVALUATED", 0),
        "noncompliant_case_ids": [row["case_id"] for row in case_rows if row["scientific_category"] == "SIMULABLE_NONCOMPLIANT"],
        "not_evaluated_case_ids": [row["case_id"] for row in case_rows if row["scientific_category"] == "UNEVALUATED"],
    }


def write_nominal_bundle(case_rows: list[dict[str, Any]], metric_rows: list[dict[str, Any]], report_rows: list[dict[str, Any]]) -> dict[str, Any]:
    nominal_summary = build_nominal_summary(case_rows)
    manifest = {
        "freeze_id": FREEZE_ID,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_head(),
        "git_branch": git_branch(),
        "python_command": str(PYTHON),
        "ngspice_version": ngspice_version(),
        "workflow_authority": {
            "name": "public_cli_verify",
            "llm_enabled": False,
            "pyspice_disabled": True,
            "allow_mock": False,
            "spec_dir": str(SPEC_DIR.relative_to(ROOT)),
            "benchmark_dir": str(BENCH_DIR.relative_to(ROOT)),
            "public_command_alias": "spec2testbench verify --specs <SPEC> --netlist <NETLIST> --no-llm --format json --output <CASE_DIR>",
            "executed_command_template": " ".join(CLI_COMMAND + ["--specs", "<SPEC>", "--netlist", "<NETLIST>", "--no-llm", "--format", "json", "--output", "<CASE_DIR>"]),
            "paper_replay_entrypoint": "python reproduce_paper.py",
        },
        "nominal_campaign": nominal_summary,
    }
    write_json(NOMINAL_ROOT / "freeze_manifest.json", manifest)
    write_json(NOMINAL_ROOT / "nominal_summary.json", nominal_summary)
    write_csv(NOMINAL_ROOT / "nominal_summary.csv", case_rows)
    write_csv(NOMINAL_ROOT / "metric_results.csv", metric_rows)
    write_csv(
        NOMINAL_ROOT / "simulability_vs_compliance.csv",
        [
            {
                "case_id": row["case_id"],
                "execution_status": row["execution_status"],
                "simulation_mode": row["simulation_mode"],
                "compliance_status": row["compliance_status"],
                "scientific_category": row["scientific_category"],
                "measurement_backend": row["measurement_backend"],
                "report_path": row["report_path"],
            }
            for row in case_rows
        ],
    )
    write_csv(
        NOMINAL_ROOT / "backend_summary.csv",
        [
            {"measurement_backend": key, "cases": value}
            for key, value in sorted(Counter(row["measurement_backend"] for row in case_rows).items())
        ],
    )
    summary_lines = [
        "# Paper Evidence Freeze 2026-07-24",
        "",
        f"- Freeze id: `{FREEZE_ID}`",
        f"- Git commit: `{manifest['git_commit']}`",
        f"- Workflow authority: `{manifest['workflow_authority']['name']}`",
        "- Replay entrypoint: `python reproduce_paper.py`",
        "- Public workflow: `spec2testbench verify --no-llm` with `SPEC2TESTBENCH_DISABLE_PYSPICE=1`",
        f"- Cases: {nominal_summary['cases']}",
        f"- REAL runs: {nominal_summary['real_runs']}",
        f"- Successful executions: {nominal_summary['successful']}",
        f"- Scientifically eligible: {nominal_summary['scientifically_eligible_true']}",
        f"- SIMULABLE_COMPLIANT: {nominal_summary['simulable_compliant']}",
        f"- SIMULABLE_NONCOMPLIANT: {nominal_summary['simulable_noncompliant']}",
        f"- UNEVALUATED: {nominal_summary['unevaluated']}",
        f"- Noncompliant cases: {', '.join(nominal_summary['noncompliant_case_ids']) or 'none'}",
        f"- Not evaluated cases: {', '.join(nominal_summary['not_evaluated_case_ids']) or 'none'}",
    ]
    write_text(FREEZE_ROOT / "README.md", "\n".join(summary_lines) + "\n")
    return manifest


def write_support_environment(manifest: dict[str, Any], report_rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured_from_case = ""
    if report_rows:
        captured_from_case = str(report_rows[0].get("circuit_name", ""))
    payload = {
        "captured_from_case": captured_from_case,
        "operating_system": platform.platform(),
        "python_version": sys.version,
        "ngspice_version": ngspice_version(),
        "git_commit": manifest["git_commit"],
        "workflow_authority": manifest["workflow_authority"],
    }
    write_json(SUPPORT_ROOT / "environment.json", payload)
    return payload


def write_test_bundle() -> dict[str, Any]:
    runs = {
        "python_m_pytest_q": run_pytest("python_m_pytest_q", {}),
        "python_m_pytest_q_ngspice": run_pytest("python_m_pytest_q_ngspice", {"RUN_NGSPICE_INTEGRATION": "1"}),
        "python_m_pytest_q_ngspice_no_pyspice": run_pytest(
            "python_m_pytest_q_ngspice_no_pyspice",
            {"RUN_NGSPICE_INTEGRATION": "1", "SPEC2TESTBENCH_DISABLE_PYSPICE": "1"},
        ),
    }
    payload = {
        "freeze_id": FREEZE_ID,
        "git_commit": git_head(),
        "runs": runs,
    }
    write_json(TEST_ROOT / "test_results.json", payload)
    return payload


def copy_controlled_artifacts() -> list[str]:
    copied: list[str] = []
    for source in FROZEN_PILOT_FILES:
        if source.exists():
            target = CONTROLLED_ROOT / source.name
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(ROOT)))
    return copied


def main() -> None:
    summary_only = "--summary-only" in sys.argv
    tests_only = "--tests-only" in sys.argv
    reuse_existing = "--reuse-existing" in sys.argv
    if summary_only and tests_only:
        raise SystemExit("Use only one of --summary-only or --tests-only")

    ensure_dirs()
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    nominal_manifest: dict[str, Any]
    test_bundle: dict[str, Any]
    environment_bundle: dict[str, Any]

    if not tests_only:
        case_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []
        report_rows: list[dict[str, Any]] = []

        for manifest_row in read_manifest():
            case_row, case_metric_rows, report_data = run_case(manifest_row, reuse_existing=reuse_existing)
            case_rows.append(case_row)
            metric_rows.extend(case_metric_rows)
            report_rows.append(report_data)

        nominal_manifest = write_nominal_bundle(case_rows, metric_rows, report_rows)
        environment_bundle = write_support_environment(nominal_manifest, report_rows)
    else:
        nominal_manifest = load_json(NOMINAL_ROOT / "freeze_manifest.json")
        environment_bundle = load_json(SUPPORT_ROOT / "environment.json")

    if not summary_only:
        test_bundle = write_test_bundle()
    else:
        test_bundle = load_json(TEST_ROOT / "test_results.json") if (TEST_ROOT / "test_results.json").exists() else {"runs": {}}

    controlled_files = copy_controlled_artifacts()
    write_json(
        FREEZE_ROOT / "bundle_manifest.json",
        {
            "freeze_id": FREEZE_ID,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_head(),
            "git_short_commit": git_short_head(),
            "nominal_manifest": str((NOMINAL_ROOT / "freeze_manifest.json").relative_to(ROOT)),
            "test_results": str((TEST_ROOT / "test_results.json").relative_to(ROOT)),
            "support_environment": str((SUPPORT_ROOT / "environment.json").relative_to(ROOT)),
            "controlled_artifacts": controlled_files,
            "nominal_scientific_category_counts": nominal_manifest["nominal_campaign"]["scientific_category_counts"],
            "operating_system": environment_bundle["operating_system"],
            "python_version": environment_bundle["python_version"],
            "pytest_counts": {
                key: {
                    "passed": value["passed"],
                    "failed": value["failed"],
                    "skipped": value["skipped"],
                    "warnings": value["warnings"],
                }
                for key, value in test_bundle["runs"].items()
            },
        },
    )
    print(
        json.dumps(
            {
                "freeze_root": str(FREEZE_ROOT),
                "cases": nominal_manifest["nominal_campaign"]["cases"],
                "summary_only": summary_only,
                "tests_only": tests_only,
                "reuse_existing": reuse_existing,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
