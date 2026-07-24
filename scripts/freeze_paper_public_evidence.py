from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_FREEZE_ID = "evidence_freeze_reviewer_revision_20260724"


def resolve_freeze_id() -> str:
    value = os.environ.get("SPEC2TESTBENCH_FREEZE_ID", DEFAULT_FREEZE_ID).strip()
    return value or DEFAULT_FREEZE_ID


def resolve_freeze_root(freeze_id: str) -> Path:
    raw = os.environ.get("SPEC2TESTBENCH_FREEZE_ROOT", "").strip()
    if not raw:
        return ROOT / "paper_final" / freeze_id
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate.resolve(strict=False)


FREEZE_ID = resolve_freeze_id()
FREEZE_ROOT = resolve_freeze_root(FREEZE_ID)
if FREEZE_ROOT != ROOT and ROOT.resolve() not in FREEZE_ROOT.resolve(strict=False).parents:
    raise RuntimeError(f"Freeze root must remain inside the repository: {FREEZE_ROOT}")

NOMINAL_ROOT = FREEZE_ROOT / "nominal"
CASE_ROOT = NOMINAL_ROOT / "cases"
TEST_ROOT = FREEZE_ROOT / "tests"
CONTROLLED_ROOT = FREEZE_ROOT / "controlled"
SUPPORT_ROOT = FREEZE_ROOT / "support"
COMMAND_ROOT = FREEZE_ROOT / "commands"
BENCH_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_nominal_specs"
MANIFEST_PATH = BENCH_DIR / "manifest.csv"
RESULTS_ROOT = ROOT / "results"
REPORTS_ROOT = ROOT / "reports"
ACP28_REPLAY_CASES_PATH = RESULTS_ROOT / "acp28_replay_cases.csv"
ACP28_REPLAY_METRICS_PATH = RESULTS_ROOT / "acp28_replay_metrics.csv"
ACP28_REPLAY_ASSERTIONS_PATH = RESULTS_ROOT / "acp28_replay_assertions.csv"
ACP28_REPLAY_SUMMARY_JSON_PATH = RESULTS_ROOT / "acp28_replay_summary.json"
ACP28_REPLAY_SUMMARY_CSV_PATH = RESULTS_ROOT / "acp28_replay_summary.csv"
ACP28_REPLAY_REPORT_PATH = REPORTS_ROOT / "acp28_replay_report.md"
FROZEN_PILOT_FILES = [
    ROOT / "results" / "frozen_pilot_metrics_v3.json",
    ROOT / "results" / "frozen_pilot_results_v3.csv",
]


def repo_relative_path(path: Path) -> str:
    candidate = path if path.is_absolute() else (ROOT / path)
    return candidate.resolve(strict=False).relative_to(ROOT.resolve()).as_posix()


def relative_path(path: Path) -> str:
    try:
        return repo_relative_path(path)
    except ValueError:
        return path.as_posix().replace("\\", "/")


def portable_path_token(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return repo_relative_path(candidate)
        except ValueError:
            return candidate.name
    return text.replace("\\", "/")


def sanitize_measurement_source(raw: Any) -> Any:
    if isinstance(raw, dict):
        return {str(key): portable_path_token(value) for key, value in raw.items()}
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return raw
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return portable_path_token(stripped)
        return json.dumps(sanitize_measurement_source(parsed), ensure_ascii=True, sort_keys=True)
    return raw


def sanitize_ngspice_command(command: Any) -> list[str]:
    if not isinstance(command, list):
        return []
    sanitized: list[str] = []
    for index, token in enumerate(command):
        token_text = str(token or "").strip()
        if not token_text:
            continue
        if index == 0 and Path(token_text).is_absolute():
            sanitized.append(Path(token_text).name)
        else:
            sanitized.append(portable_path_token(token_text))
    return sanitized


def sanitize_report_data(report_data: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(report_data))
    for trace in sanitized.get("metric_traces", []):
        if isinstance(trace, dict):
            trace["raw_result_file"] = portable_path_token(trace.get("raw_result_file", ""))
    provenance = sanitized.get("provenance", {})
    if isinstance(provenance, dict):
        for key in (
            "raw_result_file",
            "specification_file",
            "netlist_file",
            "testbench_file",
            "ngspice_input_file_path",
            "generated_testbench_path",
        ):
            provenance[key] = portable_path_token(provenance.get(key, ""))
        provenance["measurement_source"] = sanitize_measurement_source(provenance.get("measurement_source"))
        command = sanitize_ngspice_command(provenance.get("ngspice_command", []))
        if command:
            provenance["ngspice_command"] = command
            provenance["measurement_command"] = " ".join(command)
        sanitized["provenance"] = provenance
    return sanitized


def ensure_dirs() -> None:
    for path in (
        FREEZE_ROOT,
        NOMINAL_ROOT,
        CASE_ROOT,
        TEST_ROOT,
        CONTROLLED_ROOT,
        SUPPORT_ROOT,
        COMMAND_ROOT,
        RESULTS_ROOT,
        REPORTS_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


def prepare_fresh_freeze_root() -> None:
    if FREEZE_ROOT.exists():
        shutil.rmtree(FREEZE_ROOT)


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_case_path(case_dir: Path, raw: Any) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate if candidate.exists() else None


def build_artifact_hash_rows(case_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    excluded = {"artifact_hashes.json", "case_manifest.json"}
    for artifact in sorted(case_dir.rglob("*")):
        if not artifact.is_file() or artifact.name in excluded:
            continue
        rows.append(
            {
                "path": relative_path(artifact),
                "sha256": sha256_file(artifact),
                "size_bytes": artifact.stat().st_size,
            }
        )
    return rows


def latest_json_report(report_dir: Path, existing_reports: set[Path]) -> Path | None:
    candidates = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.resolve() not in existing_reports:
            return candidate
    return None


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
PYTEST_COMMAND_DISPLAY = ["python", "-m", "pytest", "-q"]
CLI_COMMAND = [str(PYTHON), "-m", "spec2testbench.presentation.cli.main", "verify"]
CLI_COMMAND_DISPLAY = ["python", "-m", "spec2testbench.presentation.cli.main", "verify"]


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


def ngspice_version_from_reports(report_rows: list[dict[str, Any]]) -> str:
    for report_data in report_rows:
        value = str(report_data.get("provenance", {}).get("ngspice_version", "")).strip()
        if value:
            return value
    return ngspice_version()


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
        "command": " ".join(PYTEST_COMMAND_DISPLAY),
        "env": env_overrides,
        "returncode": completed.returncode,
        **parse_pytest_counts(output),
    }


def functional_prerequisite_status(validation: dict[str, Any]) -> str:
    if not validation:
        return "NOT_REPORTED"
    return "READY" if all(bool(value) for value in validation.values()) else "BLOCKED"


def portable_manifest_row(manifest_row: dict[str, str]) -> dict[str, str]:
    return {
        key: value.replace("\\", "/") if isinstance(value, str) else value
        for key, value in manifest_row.items()
    }


def write_case_command_files(case_dir: Path, command_display: list[str], env_overrides: dict[str, str]) -> None:
    write_text(case_dir / "command.txt", " ".join(command_display) + "\n")
    write_json(
        case_dir / "command.json",
        {
            "command": command_display,
            "command_text": " ".join(command_display),
            "cwd": ".",
            "env_overrides": env_overrides,
        },
    )


def run_case(
    manifest_row: dict[str, str],
    reuse_existing: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    manifest_row = portable_manifest_row(manifest_row)
    spec_path = SPEC_DIR / manifest_row["spec"]
    netlist_path = BENCH_DIR / manifest_row["netlist"]
    case_id = netlist_path.stem
    case_dir = CASE_ROOT / case_id
    reports_dir = case_dir / "reports"
    stable_report_path = case_dir / "report.json"
    metrics_path = case_dir / "metrics.json"
    metric_traces_path = case_dir / "metric_traces.json"
    provenance_path = case_dir / "provenance.json"
    artifact_hashes_path = case_dir / "artifact_hashes.json"
    case_manifest_path = case_dir / "case_manifest.json"
    case_dir.mkdir(parents=True, exist_ok=True)

    public_command = CLI_COMMAND_DISPLAY + [
        "--specs",
        relative_path(spec_path),
        "--netlist",
        relative_path(netlist_path),
        "--no-llm",
        "--format",
        "json",
        "--output",
        relative_path(case_dir),
    ]
    executed_command = CLI_COMMAND + public_command[4:]
    env_overrides = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "SPEC2TESTBENCH_DISABLE_PYSPICE": "1",
        "SPEC2TESTBENCH_PRESERVE_SIM_ARTIFACTS": "1",
    }
    write_case_command_files(case_dir, public_command, env_overrides)
    shutil.copy2(spec_path, case_dir / spec_path.name)
    shutil.copy2(netlist_path, case_dir / netlist_path.name)

    fresh_replay = False
    duration_seconds: float | None = None
    started_at_utc = datetime.now(timezone.utc).isoformat()
    finished_at_utc = started_at_utc

    if reuse_existing and stable_report_path.exists():
        report_data = sanitize_report_data(load_json(stable_report_path))
        write_json(stable_report_path, report_data)
        completed_returncode = 0 if report_data.get("overall_verdict") == "PASS" else 1
    else:
        env = os.environ.copy()
        env.update(env_overrides)
        existing_reports = {path.resolve() for path in reports_dir.glob("*.json")}
        started_timer = time.perf_counter()
        completed = subprocess.run(
            executed_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        duration_seconds = round(time.perf_counter() - started_timer, 6)
        finished_at_utc = datetime.now(timezone.utc).isoformat()
        write_text(case_dir / "stdout.txt", completed.stdout or "")
        write_text(case_dir / "stderr.txt", completed.stderr or "")
        report_path = latest_json_report(reports_dir, existing_reports)
        if report_path is None:
            raise RuntimeError(
                f"Public CLI replay did not produce a JSON report for {case_id}. "
                f"Return code={completed.returncode}."
            )
        report_data = sanitize_report_data(load_json(report_path))
        write_json(report_path, report_data)
        write_json(stable_report_path, report_data)
        completed_returncode = completed.returncode
        fresh_replay = True

    metrics_payload = report_data.get("metrics", [])
    metric_traces = report_data.get("metric_traces", [])
    provenance = report_data.get("provenance", {})
    write_json(metrics_path, metrics_payload)
    write_json(metric_traces_path, metric_traces)
    write_json(provenance_path, provenance)

    generated_testbench_path = existing_case_path(case_dir, provenance.get("generated_testbench_path"))
    executed_testbench_path = existing_case_path(case_dir, provenance.get("ngspice_input_file_path"))
    report_hash = sha256_file(stable_report_path)
    metrics_hash = sha256_file(metrics_path)
    metric_traces_hash = sha256_file(metric_traces_path)
    provenance_hash = sha256_file(provenance_path)
    artifact_rows = build_artifact_hash_rows(case_dir)
    write_json(
        artifact_hashes_path,
        {
            "freeze_id": FREEZE_ID,
            "case_id": case_id,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifact_rows,
        },
    )

    runtime_seconds = provenance.get("runtime_seconds")
    if runtime_seconds in ("", None):
        runtime_seconds = duration_seconds

    important_artifacts: dict[str, dict[str, Any]] = {}
    for label, candidate in (
        ("specification_copy", case_dir / spec_path.name),
        ("netlist_copy", case_dir / netlist_path.name),
        ("generated_testbench", generated_testbench_path),
        ("executed_testbench", executed_testbench_path),
        ("report", stable_report_path),
        ("metrics", metrics_path),
        ("metric_traces", metric_traces_path),
        ("provenance", provenance_path),
        ("stdout", case_dir / "stdout.txt"),
        ("stderr", case_dir / "stderr.txt"),
        ("ngspice_stdout", case_dir / "ngspice_stdout.txt"),
        ("ngspice_stderr", case_dir / "ngspice_stderr.txt"),
        ("measures", case_dir / "measures.txt"),
        ("vectors_dat", case_dir / "vectors.dat"),
        ("vectors_csv", case_dir / "vectors.csv"),
        ("vector_metadata", case_dir / "vector_metadata.json"),
        ("raw_result", case_dir / "simulation.raw"),
    ):
        if candidate is not None and candidate.exists():
            important_artifacts[label] = {
                "path": relative_path(candidate),
                "sha256": sha256_file(candidate),
            }

    write_json(
        case_manifest_path,
        {
            "freeze_id": FREEZE_ID,
            "case_id": case_id,
            "manifest_row": manifest_row,
            "public_command": public_command,
            "exit_code": completed_returncode,
            "started_at_utc": started_at_utc,
            "finished_at_utc": finished_at_utc,
            "duration_seconds": runtime_seconds,
            "fresh_replay": fresh_replay,
            "report_path": relative_path(stable_report_path),
            "report_sha256": report_hash,
            "artifact_hash_manifest": relative_path(artifact_hashes_path),
            "important_artifacts": important_artifacts,
            "scientific_category": report_data.get("scientific_category", ""),
            "overall_verdict": report_data.get("overall_verdict", ""),
            "execution_status": report_data.get("execution_status", ""),
            "simulation_mode": report_data.get("simulation_mode", ""),
            "measurement_backend": provenance.get("measurement_backend", report_data.get("measurement_backend", "")),
            "ngspice_version": provenance.get("ngspice_version", ""),
            "git_commit": git_head(),
        },
    )

    metric_index = {
        str(metric.get("name", "")): metric
        for metric in metrics_payload
        if isinstance(metric, dict) and metric.get("name")
    }
    required_metric_validation = provenance.get("required_metric_validation", {}) or {}
    metric_rows: list[dict[str, Any]] = []
    assertion_rows: list[dict[str, Any]] = []

    for trace in metric_traces:
        validation = required_metric_validation.get(trace.get("metric_name", ""), {})
        prerequisite_status = functional_prerequisite_status(validation)
        metric_summary = metric_index.get(str(trace.get("metric_name", "")), {})
        metric_row = {
            "case_id": case_id,
            "manifest_id": manifest_row.get("id", ""),
            "difficulty_level": manifest_row.get("level", ""),
            "circuit_family": manifest_row.get("type", ""),
            "circuit_type": manifest_row.get("circuit_type", ""),
            "metric_name": trace.get("metric_name", ""),
            "metric_verdict": metric_summary.get("verdict", ""),
            "assertion_status": trace.get("status", ""),
            "measured_value": trace.get("measured_value"),
            "normalized_value": trace.get("normalized_value"),
            "unit": trace.get("unit", ""),
            "raw_metric_message": metric_summary.get("message", ""),
            "metric_category": metric_summary.get("category", ""),
            "expected_operator": trace.get("expected_operator", ""),
            "expected_threshold": trace.get("expected_threshold"),
            "expected_min": metric_summary.get("expected_min"),
            "expected_max": metric_summary.get("expected_max"),
            "source_analysis": trace.get("source_analysis", ""),
            "source_signal": trace.get("source_signal", ""),
            "extraction_method": trace.get("extraction_method", ""),
            "measurement_backend": trace.get("measurement_backend", ""),
            "measurement_expression_id": trace.get("measurement_expression_id", ""),
            "input_node": trace.get("input_node", ""),
            "output_node": trace.get("output_node", ""),
            "functional_prerequisite_status": prerequisite_status,
            "functional_prerequisite_json": json.dumps(validation, ensure_ascii=True, sort_keys=True),
            "required_metric_exists_in_specification": validation.get("target_metric_exists_in_specification"),
            "required_metric_supported_by_extractor": validation.get("target_metric_supported_by_extractor"),
            "required_metric_has_recognized_unit": validation.get("target_metric_has_recognized_unit"),
            "required_metric_has_operator": validation.get("target_metric_has_operator"),
            "required_metric_has_threshold": validation.get("target_metric_has_threshold"),
            "required_signals_available": validation.get("required_signals_available"),
            "required_analysis_generated": validation.get("required_analysis_generated"),
            "scientific_category": report_data.get("scientific_category", ""),
            "overall_verdict": report_data.get("overall_verdict", ""),
            "report_path": relative_path(stable_report_path),
        }
        metric_rows.append(metric_row)
        assertion_rows.append(
            {
                "case_id": case_id,
                "assertion_id": f"{case_id}:{trace.get('metric_name', '')}",
                "metric_name": trace.get("metric_name", ""),
                "analysis_requested": trace.get("source_analysis", ""),
                "expected_operator": trace.get("expected_operator", ""),
                "expected_threshold": trace.get("expected_threshold"),
                "measured_value": trace.get("measured_value"),
                "normalized_value": trace.get("normalized_value"),
                "unit": trace.get("unit", ""),
                "assertion_status": trace.get("status", ""),
                "functional_prerequisite_status": prerequisite_status,
                "functional_prerequisite_json": json.dumps(validation, ensure_ascii=True, sort_keys=True),
                "scientific_category": report_data.get("scientific_category", ""),
                "measurement_backend": trace.get("measurement_backend", ""),
                "report_path": relative_path(stable_report_path),
            }
        )

    requested_analyses = sorted({str(trace.get("source_analysis", "")).strip() for trace in metric_traces if trace.get("source_analysis")})
    measurement_backends = sorted({str(trace.get("measurement_backend", "")).strip() for trace in metric_traces if trace.get("measurement_backend")})
    case_row = {
        "case_id": case_id,
        "manifest_id": manifest_row.get("id", ""),
        "difficulty_level": manifest_row.get("level", ""),
        "circuit_family": manifest_row.get("type", ""),
        "circuit_type": manifest_row.get("circuit_type", ""),
        "description": manifest_row.get("description", ""),
        "source_py": manifest_row.get("source_py", ""),
        "specification_source": relative_path(spec_path),
        "netlist_source": relative_path(netlist_path),
        "specification_hash": provenance.get("specification_hash", ""),
        "netlist_hash": provenance.get("netlist_hash", ""),
        "generated_testbench_path": relative_path(generated_testbench_path) if generated_testbench_path else portable_path_token(provenance.get("generated_testbench_path", "")),
        "generated_testbench_hash": provenance.get("generated_testbench_sha256", ""),
        "executed_testbench_path": relative_path(executed_testbench_path) if executed_testbench_path else portable_path_token(provenance.get("ngspice_input_file_path", "")),
        "executed_testbench_hash": provenance.get("executed_file_sha256", ""),
        "command_file": relative_path(case_dir / "command.txt"),
        "command_json": relative_path(case_dir / "command.json"),
        "public_command": " ".join(public_command),
        "exit_code": completed_returncode,
        "stdout_path": relative_path(case_dir / "stdout.txt") if (case_dir / "stdout.txt").exists() else "",
        "stderr_path": relative_path(case_dir / "stderr.txt") if (case_dir / "stderr.txt").exists() else "",
        "ngspice_stdout_path": relative_path(case_dir / "ngspice_stdout.txt") if (case_dir / "ngspice_stdout.txt").exists() else "",
        "ngspice_stderr_path": relative_path(case_dir / "ngspice_stderr.txt") if (case_dir / "ngspice_stderr.txt").exists() else "",
        "ngspice_version": provenance.get("ngspice_version", "") or ngspice_version(),
        "simulation_mode": report_data.get("simulation_mode", ""),
        "requested_analyses": ",".join(requested_analyses),
        "measurement_backend": provenance.get("measurement_backend", report_data.get("measurement_backend", "")),
        "measurement_backends": ",".join(measurement_backends),
        "measurement_source": provenance.get("measurement_source", ""),
        "metric_count": len(metric_traces),
        "passed_metric_count": sum(1 for trace in metric_traces if trace.get("status") == "PASS"),
        "failed_metric_count": sum(1 for trace in metric_traces if trace.get("status") == "FAIL"),
        "not_evaluated_metric_count": sum(1 for trace in metric_traces if trace.get("status") == "NOT_EVALUATED"),
        "overall_verdict": report_data.get("overall_verdict", ""),
        "terminal_status": report_data.get("terminal_status", ""),
        "execution_status": report_data.get("execution_status", ""),
        "compliance_status": report_data.get("compliance_status", ""),
        "scientific_category": report_data.get("scientific_category", ""),
        "scientifically_eligible": report_data.get("scientifically_eligible", False),
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "runtime_seconds": runtime_seconds,
        "report_timestamp": report_data.get("timestamp", ""),
        "git_commit": git_head(),
        "framework_git_commit": provenance.get("git_commit", ""),
        "report_path": relative_path(stable_report_path),
        "report_sha256": report_hash,
        "metrics_path": relative_path(metrics_path),
        "metrics_sha256": metrics_hash,
        "metric_traces_path": relative_path(metric_traces_path),
        "metric_traces_sha256": metric_traces_hash,
        "provenance_path": relative_path(provenance_path),
        "provenance_sha256": provenance_hash,
        "artifact_hash_manifest": relative_path(artifact_hashes_path),
        "case_manifest_path": relative_path(case_manifest_path),
        "fresh_replay": fresh_replay,
    }
    return case_row, metric_rows, assertion_rows, report_data


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


def build_replay_summary(
    case_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    assertion_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    scientific_counts = Counter(str(row["scientific_category"]) for row in case_rows)
    execution_counts = Counter(str(row["execution_status"]) for row in case_rows)
    mode_counts = Counter(str(row["simulation_mode"]) for row in case_rows)
    backend_counts = Counter(str(row["measurement_backend"]) for row in case_rows)
    metric_status_counts = Counter(str(row["assertion_status"]) for row in metric_rows)

    compliant = scientific_counts.get("SIMULABLE_COMPLIANT", 0)
    noncompliant = scientific_counts.get("SIMULABLE_NONCOMPLIANT", 0)
    not_evaluated = scientific_counts.get("UNEVALUATED", 0)
    real_runs = mode_counts.get("REAL", 0)
    successful_runs = sum(1 for row in case_rows if row["simulation_mode"] == "REAL" and row["execution_status"] == "SUCCESS")
    failed_runs = sum(1 for row in case_rows if row["simulation_mode"] == "REAL" and row["execution_status"] != "SUCCESS")
    total_cases = len(case_rows)
    unexpected_categories = sorted(
        category
        for category in scientific_counts
        if category not in {"SIMULABLE_COMPLIANT", "SIMULABLE_NONCOMPLIANT", "UNEVALUATED"}
    )
    return {
        "freeze_id": FREEZE_ID,
        "bundle_root": relative_path(FREEZE_ROOT),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_head(),
        "git_branch": git_branch(),
        "cases_total": total_cases,
        "real_runs": real_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "scientifically_eligible_true": sum(1 for row in case_rows if row["scientifically_eligible"]),
        "compliant": compliant,
        "noncompliant": noncompliant,
        "not_evaluated": not_evaluated,
        "execution_status_counts": dict(execution_counts),
        "simulation_mode_counts": dict(mode_counts),
        "scientific_category_counts": dict(scientific_counts),
        "measurement_backend_counts": dict(backend_counts),
        "metric_rows": len(metric_rows),
        "assertion_rows": len(assertion_rows),
        "metric_status_counts": dict(metric_status_counts),
        "unexpected_scientific_categories": unexpected_categories,
        "noncompliant_case_ids": [row["case_id"] for row in case_rows if row["scientific_category"] == "SIMULABLE_NONCOMPLIANT"],
        "not_evaluated_case_ids": [row["case_id"] for row in case_rows if row["scientific_category"] == "UNEVALUATED"],
        "invariants": {
            "total_equals_partition": total_cases == compliant + noncompliant + not_evaluated,
            "real_runs_equals_successful_plus_failed": real_runs == successful_runs + failed_runs,
        },
    }


def write_replay_outputs(
    case_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    assertion_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = build_replay_summary(case_rows, metric_rows, assertion_rows)
    write_csv(ACP28_REPLAY_CASES_PATH, case_rows)
    write_csv(ACP28_REPLAY_METRICS_PATH, metric_rows)
    write_csv(ACP28_REPLAY_ASSERTIONS_PATH, assertion_rows)
    write_json(ACP28_REPLAY_SUMMARY_JSON_PATH, summary)
    write_csv(
        ACP28_REPLAY_SUMMARY_CSV_PATH,
        [
            {
                "freeze_id": summary["freeze_id"],
                "git_commit": summary["git_commit"],
                "cases_total": summary["cases_total"],
                "real_runs": summary["real_runs"],
                "successful_runs": summary["successful_runs"],
                "failed_runs": summary["failed_runs"],
                "scientifically_eligible_true": summary["scientifically_eligible_true"],
                "compliant": summary["compliant"],
                "noncompliant": summary["noncompliant"],
                "not_evaluated": summary["not_evaluated"],
                "total_equals_partition": summary["invariants"]["total_equals_partition"],
                "real_runs_equals_successful_plus_failed": summary["invariants"]["real_runs_equals_successful_plus_failed"],
            }
        ],
    )
    report_lines = [
        "# ACP-28 Authoritative Replay Report",
        "",
        f"- Freeze id: `{FREEZE_ID}`",
        f"- Bundle root: `{relative_path(FREEZE_ROOT)}`",
        f"- Git commit: `{summary['git_commit']}`",
        f"- Workflow authority: `spec2testbench verify --no-llm`",
        f"- Cases replayed: {summary['cases_total']}",
        f"- REAL runs: {summary['real_runs']}",
        f"- Successful REAL runs: {summary['successful_runs']}",
        f"- Failed REAL runs: {summary['failed_runs']}",
        f"- Scientifically eligible: {summary['scientifically_eligible_true']}",
        f"- SIMULABLE_COMPLIANT: {summary['compliant']}",
        f"- SIMULABLE_NONCOMPLIANT: {summary['noncompliant']}",
        f"- UNEVALUATED: {summary['not_evaluated']}",
        f"- Noncompliant cases: {', '.join(summary['noncompliant_case_ids']) or 'none'}",
        f"- Not evaluated cases: {', '.join(summary['not_evaluated_case_ids']) or 'none'}",
        f"- Invariant total = compliant + noncompliant + not_evaluated: `{summary['invariants']['total_equals_partition']}`",
        f"- Invariant real_runs = successful_runs + failed_runs: `{summary['invariants']['real_runs_equals_successful_plus_failed']}`",
        f"- Case table: `{relative_path(ACP28_REPLAY_CASES_PATH)}`",
        f"- Metric table: `{relative_path(ACP28_REPLAY_METRICS_PATH)}`",
        f"- Assertion table: `{relative_path(ACP28_REPLAY_ASSERTIONS_PATH)}`",
    ]
    if summary["unexpected_scientific_categories"]:
        report_lines.extend(
            [
                "",
                "## Unexpected Categories",
                "",
                ", ".join(summary["unexpected_scientific_categories"]),
            ]
        )
    write_text(ACP28_REPLAY_REPORT_PATH, "\n".join(report_lines) + "\n")
    return summary


def write_nominal_bundle(
    case_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    assertion_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    nominal_summary = build_nominal_summary(case_rows)
    replay_summary = write_replay_outputs(case_rows, metric_rows, assertion_rows)
    manifest = {
        "freeze_id": FREEZE_ID,
        "freeze_root": relative_path(FREEZE_ROOT),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_head(),
        "git_branch": git_branch(),
        "python_command": "python",
        "ngspice_version": ngspice_version_from_reports(report_rows),
        "workflow_authority": {
            "name": "public_cli_verify",
            "llm_enabled": False,
            "pyspice_disabled": True,
            "allow_mock": False,
            "preserve_sim_artifacts": True,
            "spec_dir": relative_path(SPEC_DIR),
            "benchmark_dir": relative_path(BENCH_DIR),
            "public_command_alias": "spec2testbench verify --specs <SPEC> --netlist <NETLIST> --no-llm --format json --output <CASE_DIR>",
            "executed_command_template": " ".join(
                CLI_COMMAND_DISPLAY + ["--specs", "<SPEC>", "--netlist", "<NETLIST>", "--no-llm", "--format", "json", "--output", "<CASE_DIR>"]
            ),
            "paper_replay_entrypoint": "python reproduce_paper.py",
        },
        "nominal_campaign": nominal_summary,
        "replay_outputs": {
            "cases_csv": relative_path(ACP28_REPLAY_CASES_PATH),
            "metrics_csv": relative_path(ACP28_REPLAY_METRICS_PATH),
            "assertions_csv": relative_path(ACP28_REPLAY_ASSERTIONS_PATH),
            "summary_json": relative_path(ACP28_REPLAY_SUMMARY_JSON_PATH),
            "summary_csv": relative_path(ACP28_REPLAY_SUMMARY_CSV_PATH),
            "report_md": relative_path(ACP28_REPLAY_REPORT_PATH),
            "invariants": replay_summary["invariants"],
        },
    }
    write_json(NOMINAL_ROOT / "freeze_manifest.json", manifest)
    write_json(NOMINAL_ROOT / "nominal_summary.json", nominal_summary)
    write_csv(NOMINAL_ROOT / "nominal_summary.csv", case_rows)
    write_csv(NOMINAL_ROOT / "metric_results.csv", metric_rows)
    write_csv(NOMINAL_ROOT / "assertion_results.csv", assertion_rows)
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
        "# Reviewer Evidence Freeze 2026-07-24",
        "",
        f"- Freeze id: `{FREEZE_ID}`",
        f"- Freeze root: `{relative_path(FREEZE_ROOT)}`",
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
        f"- ACP-28 replay report: `{relative_path(ACP28_REPLAY_REPORT_PATH)}`",
    ]
    write_text(FREEZE_ROOT / "README.md", "\n".join(summary_lines) + "\n")
    write_text(COMMAND_ROOT / "reproduce_summary_command.txt", f"python reproduce_paper.py --freeze-id {FREEZE_ID} --summary-only\n")
    write_text(COMMAND_ROOT / "reproduce_tests_command.txt", f"python reproduce_paper.py --freeze-id {FREEZE_ID} --tests-only\n")
    return manifest


def write_support_environment(manifest: dict[str, Any], report_rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured_from_case = ""
    if report_rows:
        captured_from_case = str(report_rows[0].get("circuit_name", ""))
    payload = {
        "captured_from_case": captured_from_case,
        "operating_system": platform.platform(),
        "python_version": sys.version,
        "ngspice_version": ngspice_version_from_reports(report_rows),
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
            copied.append(relative_path(target))
    return copied


def main() -> None:
    summary_only = "--summary-only" in sys.argv
    tests_only = "--tests-only" in sys.argv
    reuse_existing = "--reuse-existing" in sys.argv
    if summary_only and tests_only:
        raise SystemExit("Use only one of --summary-only or --tests-only")

    if not tests_only and not reuse_existing:
        prepare_fresh_freeze_root()
    ensure_dirs()
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"

    nominal_manifest: dict[str, Any]
    test_bundle: dict[str, Any]
    environment_bundle: dict[str, Any]

    if not tests_only:
        case_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []
        assertion_rows: list[dict[str, Any]] = []
        report_rows: list[dict[str, Any]] = []

        for manifest_row in read_manifest():
            case_row, case_metric_rows, case_assertion_rows, report_data = run_case(
                manifest_row,
                reuse_existing=reuse_existing,
            )
            case_rows.append(case_row)
            metric_rows.extend(case_metric_rows)
            assertion_rows.extend(case_assertion_rows)
            report_rows.append(report_data)

        nominal_manifest = write_nominal_bundle(case_rows, metric_rows, assertion_rows, report_rows)
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
            "freeze_root": relative_path(FREEZE_ROOT),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_head(),
            "git_short_commit": git_short_head(),
            "nominal_manifest": relative_path(NOMINAL_ROOT / "freeze_manifest.json"),
            "test_results": relative_path(TEST_ROOT / "test_results.json"),
            "support_environment": relative_path(SUPPORT_ROOT / "environment.json"),
            "controlled_artifacts": controlled_files,
            "nominal_scientific_category_counts": nominal_manifest["nominal_campaign"]["scientific_category_counts"],
            "replay_summary_json": relative_path(ACP28_REPLAY_SUMMARY_JSON_PATH) if ACP28_REPLAY_SUMMARY_JSON_PATH.exists() else "",
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
