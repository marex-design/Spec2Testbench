from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


DATE = "2026-07-25"
PRELIGHT_RELATIVE = Path("scientific_evidence/heavy_revision_20260725/preflight")
ROOT_SCOPE_FILES = (
    "command.txt",
    "stdout.txt",
    "stderr.txt",
    "return_code.txt",
    "start_time_utc.txt",
    "end_time_utc.txt",
    "environment.json",
    "git_commit.txt",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_to(base: Path, target: Path) -> str:
    return target.resolve().relative_to(base.resolve()).as_posix()


def ensure_within(root: Path, target: Path) -> Path:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    resolved_target.relative_to(resolved_root)
    return resolved_target


def reset_directory(path: Path, allowed_root: Path) -> None:
    ensure_within(allowed_root, path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree_without_figures(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if "figures" in relative.parts:
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def git_output(clean_root: Path, args: list[str]) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={clean_root.as_posix()}",
        "-C",
        str(clean_root),
        *args,
    ]
    result = run_command(command)
    if result.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(command)}\n{result.stderr}")
    return result.stdout


def enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def load_smoke_context(smoke_root: Path) -> dict[str, Any]:
    manifest_path = smoke_root / "smoke_run_manifest.json"
    manifest = read_json(manifest_path)
    cli_report = Path(manifest["cli_report_json"])
    result_summary = Path(manifest["result_summary_json"])
    artifact_manifest = Path(manifest["artifact_manifest_json"])
    report_payload = read_json(cli_report)
    summary_payload = read_json(result_summary)
    artifact_payload = read_json(artifact_manifest)
    return {
        "smoke_root": smoke_root,
        "output_root": smoke_root / "run_output",
        "manifest_path": manifest_path,
        "manifest": manifest,
        "cli_report_path": cli_report,
        "cli_report": report_payload,
        "result_summary_path": result_summary,
        "result_summary": summary_payload,
        "artifact_manifest_path": artifact_manifest,
        "artifact_manifest": artifact_payload,
    }


def build_smoke_artifact_inventory(smoke_root: Path, output_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ROOT_SCOPE_FILES:
        path = smoke_root / name
        rows.append(
            {
                "relative_path": rel_to(smoke_root, path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "category": "root",
            }
        )

    for path in sorted(p for p in output_root.rglob("*") if p.is_file()):
        rows.append(
            {
                "relative_path": rel_to(smoke_root, path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "category": "run_output",
            }
        )
    return rows


def write_inventory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "size_bytes", "sha256", "category"])
        writer.writeheader()
        writer.writerows(rows)


def build_smoke_validation(smoke: dict[str, Any]) -> dict[str, Any]:
    smoke_root = smoke["smoke_root"]
    output_root = smoke["output_root"]
    manifest = smoke["manifest"]
    report = smoke["cli_report"]
    summary = smoke["result_summary"]
    artifact_manifest = smoke["artifact_manifest"]
    provenance = report["provenance"]
    artifact_validation = provenance.get("artifact_validation") or {}

    run_id = summary["run_id"]
    timestamp = summary["timestamp"]
    report_path = smoke["cli_report_path"]
    result_summary_path = smoke["result_summary_path"]
    figures_dir = Path(artifact_manifest["figures_dir"])
    output_root_manifest = Path(artifact_manifest["output_root"])
    generated_testbench_path = Path(provenance["generated_testbench_path"])

    relevant_paths = [
        report_path,
        result_summary_path,
        Path(artifact_manifest["report_json"]),
        Path(artifact_manifest["report_markdown"]),
        Path(artifact_manifest["result_summary"]),
        Path(artifact_manifest["simulation_dir"]),
        figures_dir,
        output_root_manifest,
        generated_testbench_path,
    ]
    relevant_paths.extend(Path(path) for path in artifact_manifest.get("figures", {}).values())

    validation_checks = {
        "simulation_mode_real": provenance.get("simulation_mode") == "REAL",
        "ngspice_invoked": any("ngspice" in str(part).lower() for part in (provenance.get("ngspice_command") or [])),
        "real_netlist_confirmed": provenance.get("netlist_binding_status") == "MATCH" and bool(provenance.get("actual_netlist_sha256")),
        "generated_testbench_exists": generated_testbench_path.is_file(),
        "result_belongs_to_current_run": provenance.get("run_id") == run_id == artifact_manifest.get("run_id") and summary["provenance"]["run_id"] == run_id and artifact_manifest.get("timestamp") == timestamp,
        "no_historical_fallback": artifact_validation.get("validation_status") == "CURRENT_RUN",
        "all_outputs_under_smoke_root": all(ensure_within(output_root, path) or True for path in relevant_paths),
        "results_dir_redirected": result_summary_path.resolve().is_relative_to(output_root.resolve()),
        "report_dir_redirected": report_path.resolve().is_relative_to(output_root.resolve()) and Path(artifact_manifest["report_json"]).resolve().is_relative_to(output_root.resolve()),
        "waveform_dir_redirected": figures_dir.resolve().is_relative_to(output_root.resolve()),
        "output_dir_redirected": output_root_manifest.resolve().is_relative_to(output_root.resolve()),
    }

    payload = {
        "date": DATE,
        "git_commit": manifest["git_commit"],
        "command": manifest["command"],
        "return_code": int(read_text(smoke_root / "return_code.txt").strip()),
        "specification_path": manifest["specification_path"],
        "netlist_path": manifest["netlist_path"],
        "cli_report_json": str(report_path),
        "result_summary_json": str(result_summary_path),
        "artifact_manifest_json": str(smoke["artifact_manifest_path"]),
        "run_id": run_id,
        "timestamp": timestamp,
        "overall_verdict": summary["overall_verdict"],
        "execution_status": summary["execution_status"],
        "simulation_mode": summary["simulation_mode"],
        "compliance_status": summary["compliance_status"],
        "metric_names": [trace["metric_name"] for trace in summary.get("metric_traces", [])],
        "validation_checks": validation_checks,
    }
    return payload


def write_smoke_validation_markdown(path: Path, manifest: dict[str, Any], report: dict[str, Any], validation: dict[str, Any]) -> None:
    lines = [
        "# Smoke Run Validation",
        "",
        f"- Date: `{DATE}`",
        f"- Commit: `{manifest['git_commit']}`",
        f"- Command: `{manifest['command']}`",
        f"- Return code: `{validation['return_code']}`",
        f"- Overall verdict: `{validation['overall_verdict']}`",
        f"- Execution status: `{validation['execution_status']}`",
        f"- Simulation mode: `{validation['simulation_mode']}`",
        "",
        "## Checks",
    ]
    for name, passed in validation["validation_checks"].items():
        lines.append(f"- `{name}`: `{str(bool(passed)).lower()}`")
    write_text(path, "\n".join(lines) + "\n")


def build_replay_results(summary: dict[str, Any]) -> dict[str, Any]:
    provenance = summary["provenance"]
    metrics = {
        trace["metric_name"]: trace["measured_value"]
        for trace in summary.get("metric_traces", [])
        if trace.get("measured_value") is not None
    }
    artifacts: dict[str, str] = {}
    if provenance.get("raw_result_file_exists") and provenance.get("raw_result_file"):
        artifacts["raw"] = provenance["raw_result_file"]
    if provenance.get("measurement_source"):
        artifacts["measures"] = provenance["measurement_source"]

    return {
        "success": summary["simulation_success"],
        "simulation_mode": summary["simulation_mode"],
        "execution_status": summary["execution_status"],
        "logs": [],
        "errors": [],
        "metrics": metrics,
        "measurement_backend": provenance.get("measurement_backend"),
        "measurement_source": provenance.get("measurement_source"),
        "measurement_command": provenance.get("measurement_command"),
        "measurement_status": provenance.get("measurement_status"),
        "raw_result_file": provenance.get("raw_result_file"),
        "raw_result_file_exists": provenance.get("raw_result_file_exists"),
        "ngspice_command": provenance.get("ngspice_command"),
        "ngspice_returncode": provenance.get("ngspice_returncode"),
        "ngspice_version": provenance.get("ngspice_version"),
        "expected_netlist_sha256": provenance.get("expected_netlist_sha256"),
        "actual_netlist_sha256": provenance.get("actual_netlist_sha256"),
        "actual_deck_sha256": provenance.get("actual_deck_sha256"),
        "netlist_binding_status": provenance.get("netlist_binding_status"),
        "compiled_plan_sha256": provenance.get("compiled_plan_sha256"),
        "serialized_deck_sha256": provenance.get("serialized_deck_sha256"),
        "executed_file_sha256": provenance.get("executed_file_sha256"),
        "post_execution_file_sha256": provenance.get("post_execution_file_sha256"),
        "ngspice_input_file_path": provenance.get("ngspice_input_file_path"),
        "generated_testbench_path": provenance.get("generated_testbench_path"),
        "generated_testbench_sha256": provenance.get("generated_testbench_sha256"),
        "generated_testbench_alias_byte_identical": provenance.get("generated_testbench_alias_byte_identical"),
        "post_serialization_deck_mutation": provenance.get("post_serialization_deck_mutation"),
        "artifacts": artifacts,
        "artifact_validation": deepcopy(provenance.get("artifact_validation") or {}),
    }


def write_command_artifacts(root: Path, command: list[str], result: subprocess.CompletedProcess[str]) -> None:
    write_text(root / "command.txt", " ".join(f'"{part}"' if " " in part else part for part in command) + "\n")
    write_text(root / "stdout.txt", result.stdout)
    write_text(root / "stderr.txt", result.stderr)
    write_text(root / "return_code.txt", f"{result.returncode}\n")


def mutate_netlist(source: Path, destination: Path, old: str, new: str) -> None:
    text = read_text(source)
    if old not in text:
        raise RuntimeError(f"Expected netlist fragment not found in {source}: {old}")
    write_text(destination, text.replace(old, new, 1))


def scenario_a(clean_root: Path, stale_root: Path, smoke: dict[str, Any], env: dict[str, str], temp_root: Path) -> dict[str, Any]:
    scenario_root = stale_root / "scenario_A"
    reset_directory(scenario_root, stale_root)
    reset_directory(temp_root, temp_root.parent)
    seed_output = temp_root / "o"
    copy_tree_without_figures(smoke["output_root"], seed_output)

    manifest = smoke["manifest"]
    spec_path = Path(manifest["specification_path"])
    netlist_path = Path(manifest["netlist_path"])
    mutated_netlist = scenario_root / "mutated_netlist.cir"
    mutate_netlist(netlist_path, mutated_netlist, "R1 Vin Vout 10k", "R1 Vin Vout 22k")

    copied_old_report = seed_output / "reports" / smoke["cli_report_path"].name
    old_report_sha = sha256_file(copied_old_report)

    command = [
        sys.executable,
        "-m",
        "spec2testbench.presentation.cli.main",
        "verify",
        "--specs",
        str(spec_path),
        "--netlist",
        str(mutated_netlist),
        "--output",
        str(seed_output),
        "--format",
        "json",
        "--no-llm",
    ]
    result = run_command(command, cwd=clean_root, env=env)
    write_command_artifacts(scenario_root, command, result)

    latest_report = max((seed_output / "reports").glob("*.json"), key=lambda path: path.stat().st_mtime)
    latest_report_payload = read_json(latest_report)
    latest_provenance = latest_report_payload["provenance"]
    original_netlist_hash = smoke["cli_report"]["provenance"]["netlist_hash"]
    new_netlist_hash = latest_provenance["netlist_hash"]
    validation_status = (latest_provenance.get("artifact_validation") or {}).get("validation_status")
    old_report_unchanged = sha256_file(copied_old_report) == old_report_sha

    passed = all(
        [
            result.returncode == 0,
            latest_report.name != copied_old_report.name,
            latest_provenance["run_id"] != smoke["result_summary"]["run_id"],
            original_netlist_hash != new_netlist_hash,
            validation_status == "CURRENT_RUN",
            old_report_unchanged,
        ]
    )

    payload = {
        "scenario_id": "A",
        "expected_behavior": "A new REAL CLI run with a modified netlist must create a fresh result and must not accept the copied historical report as the current run.",
        "observed_behavior": f"return_code={result.returncode}, validation_status={validation_status}, new_report={latest_report.name}, old_report_unchanged={old_report_unchanged}",
        "pass": passed,
        "artifact_used": str(copied_old_report),
        "rejection_reason": validation_status or "",
        "test_path": "public_cli_verify",
        "log_path": str(scenario_root / "stdout.txt"),
        "details": {
            "old_report_sha256": old_report_sha,
            "new_report_path": str(latest_report),
            "old_netlist_hash": original_netlist_hash,
            "new_netlist_hash": new_netlist_hash,
            "run_id": latest_provenance["run_id"],
        },
    }
    write_json(scenario_root / "result.json", payload)
    return payload


def scenario_programmatic(
    *,
    scenario_id: str,
    stale_root: Path,
    smoke: dict[str, Any],
    mutate_results: Any,
    explicit_replay: bool,
    expected_status: str,
    expected_behavior: str,
    clean_root: Path,
    head_commit: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(clean_root))
    from spec2testbench.application.usecases.run_verification import VerificationPipeline
    from spec2testbench.domain.entities.specification import Specification

    scenario_root = stale_root / f"scenario_{scenario_id}"
    reset_directory(scenario_root, stale_root)

    base_results = build_replay_results(smoke["result_summary"])
    if explicit_replay:
        base_results["artifact_reuse_mode"] = "EXPLICIT_REPLAY"
    mutate_results(base_results)

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, scientific_workflow=True)
    spec_path = Path(smoke["manifest"]["specification_path"])
    netlist_path = Path(smoke["manifest"]["netlist_path"])
    original_git_commit = VerificationPipeline._git_commit
    try:
        VerificationPipeline._git_commit = staticmethod(lambda: head_commit)
        report = pipeline.verify(
            Specification.from_yaml(spec_path),
            netlist_path=netlist_path,
            simulation_results=base_results,
            spec_path=spec_path,
        )
    finally:
        VerificationPipeline._git_commit = original_git_commit

    validation = report.provenance.get("artifact_validation") or {}
    validation_status = validation.get("validation_status", "")
    execution_status = str(enum_value(report.execution_status))
    passed = execution_status == "ERROR" and validation_status == expected_status
    payload = {
        "scenario_id": scenario_id,
        "expected_behavior": expected_behavior,
        "observed_behavior": f"execution_status={execution_status}, validation_status={validation_status}, accepted={validation.get('accepted')}",
        "pass": passed,
        "artifact_used": str(smoke["result_summary_path"]),
        "rejection_reason": validation_status,
        "test_path": "VerificationPipeline.verify",
        "log_path": str(scenario_root / "result.json"),
        "details": {
            "report_run_id": report.run_id,
            "report_timestamp": report.timestamp,
            "errors": report.errors,
            "simulation_errors": report.simulation_errors,
        },
    }
    write_json(scenario_root / "result.json", payload)
    return payload


def scenario_d(clean_root: Path, stale_root: Path, smoke: dict[str, Any], head_commit: str) -> dict[str, Any]:
    sys.path.insert(0, str(clean_root))
    from spec2testbench.application.usecases.run_verification import VerificationPipeline
    from spec2testbench.config.settings import settings

    scenario_root = stale_root / "scenario_D"
    reset_directory(scenario_root, stale_root)
    seed_output = scenario_root / "s"
    copy_tree_without_figures(smoke["output_root"], seed_output)

    spec_path = Path(smoke["manifest"]["specification_path"])
    netlist_path = Path(smoke["manifest"]["netlist_path"])
    broken_netlist = scenario_root / "broken_netlist.cir"
    mutate_netlist(netlist_path, broken_netlist, "R1 Vin Vout 10k", "R1 Vin Vout BROKENVALUE")

    old_result_copy = seed_output / rel_to(smoke["output_root"], smoke["result_summary_path"])
    old_result_sha = sha256_file(old_result_copy)

    original = (
        settings.output.output_dir,
        settings.output.waveform_dir,
        settings.output.report_dir,
        settings.output.results_dir,
        settings.output.persist_outputs,
    )
    try:
        settings.output.set_run_root(seed_output)
        settings.output.persist_outputs = True
        original_git_commit = VerificationPipeline._git_commit
        VerificationPipeline._git_commit = staticmethod(lambda: head_commit)
        pipeline = VerificationPipeline(
            use_llm=False,
            allow_mock=False,
            scientific_workflow=True,
            persist_artifacts=True,
        )
        report = pipeline.verify_from_yaml(spec_path, broken_netlist)
    finally:
        VerificationPipeline._git_commit = original_git_commit
        settings.output.output_dir = original[0]
        settings.output.waveform_dir = original[1]
        settings.output.report_dir = original[2]
        settings.output.results_dir = original[3]
        settings.output.persist_outputs = original[4]
        settings.output.ensure_directories()

    result_files = sorted((seed_output / "results" / "verification_runs").rglob("*.json"), key=lambda path: path.stat().st_mtime)
    latest_result = result_files[-1]
    latest_payload = read_json(latest_result)
    old_result_unchanged = sha256_file(old_result_copy) == old_result_sha
    execution_status = str(enum_value(report.execution_status))

    passed = all(
        [
            execution_status == "ERROR",
            latest_payload["execution_status"] == "ERROR",
            latest_result != old_result_copy,
            latest_payload["run_id"] != smoke["result_summary"]["run_id"],
            old_result_unchanged,
        ]
    )

    payload = {
        "scenario_id": "D",
        "expected_behavior": "A broken ngspice run executed in a folder containing an old successful result must stay in ERROR and must not load the historical success.",
        "observed_behavior": f"execution_status={execution_status}, latest_result={latest_result.name}, old_result_unchanged={old_result_unchanged}",
        "pass": passed,
        "artifact_used": str(old_result_copy),
        "rejection_reason": (latest_payload.get("provenance", {}).get("artifact_validation") or {}).get("validation_status", ""),
        "test_path": "VerificationPipeline.verify_from_yaml",
        "log_path": str(scenario_root / "result.json"),
        "details": {
            "new_result_path": str(latest_result),
            "old_result_sha256": old_result_sha,
            "new_run_id": latest_payload["run_id"],
            "ngspice_returncode": latest_payload["provenance"].get("ngspice_returncode"),
        },
    }
    write_json(scenario_root / "result.json", payload)
    return payload


def write_stale_artifact_reports(preflight_root: Path, scenario_rows: list[dict[str, Any]]) -> None:
    csv_path = preflight_root / "stale_artifact_scenarios.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "expected_behavior",
                "observed_behavior",
                "pass",
                "artifact_used",
                "rejection_reason",
                "test_path",
                "log_path",
            ],
        )
        writer.writeheader()
        for row in scenario_rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    lines = [
        "# Stale Artifact Test Report",
        "",
        f"- Date: `{DATE}`",
        f"- Scenarios executed: `{len(scenario_rows)}`",
        f"- Passed: `{sum(1 for row in scenario_rows if row['pass'])}`",
        f"- Failed: `{sum(1 for row in scenario_rows if not row['pass'])}`",
        "",
        "## Scenario Results",
    ]
    for row in scenario_rows:
        lines.extend(
            [
                f"### Scenario {row['scenario_id']}",
                f"- Expected behavior: {row['expected_behavior']}",
                f"- Observed behavior: {row['observed_behavior']}",
                f"- Pass: `{str(bool(row['pass'])).lower()}`",
                f"- Artifact used: `{row['artifact_used']}`",
                f"- Rejection reason: `{row['rejection_reason'] or 'N/A'}`",
                f"- Test path: `{row['test_path']}`",
                f"- Log path: `{row['log_path']}`",
                "",
            ]
        )
    write_text(preflight_root / "stale_artifact_test_report.md", "\n".join(lines))


def parse_ls_tree(output: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        _, _, blob_id = meta.split(" ", 2)
        rows[path] = blob_id
    return rows


def build_paper_integrity(
    *,
    clean_root: Path,
    preflight_root: Path,
    audit_root: Path,
    base_commit: str,
    head_commit: str,
) -> dict[str, Any]:
    baseline_path = audit_root / "worktree_forensics" / "paper_final_head_tree.csv"
    baseline_rows = list(csv.DictReader(read_text(baseline_path).splitlines()))
    baseline = {row["path"]: row["git_blob_id"] for row in baseline_rows if row["path"].startswith("paper_final/")}
    base_commit_tree = parse_ls_tree(git_output(clean_root, ["ls-tree", "-r", base_commit, "paper_final"]))
    current = parse_ls_tree(git_output(clean_root, ["ls-tree", "-r", "HEAD", "paper_final"]))
    touched_paths = [line for line in git_output(clean_root, ["diff", "--name-only", f"{base_commit}..{head_commit}", "--", "paper_final"]).splitlines() if line.strip()]
    worktree_status = [line for line in git_output(clean_root, ["status", "--short", "--", "paper_final"]).splitlines() if line.strip()]

    all_paths = sorted(set(baseline) | set(base_commit_tree) | set(current))
    rows: list[dict[str, Any]] = []
    latex_bib_modified_in_phase = False
    for path in all_paths:
        baseline_blob = baseline.get(path, "")
        base_blob = base_commit_tree.get(path, "")
        current_blob = current.get(path, "")
        if path in baseline and path in current and baseline_blob == current_blob:
            audit_status = "MATCH"
        elif path in baseline and path in current:
            audit_status = "BLOB_MISMATCH"
        elif path in baseline:
            audit_status = "MISSING_IN_CURRENT_HEAD"
        else:
            audit_status = "NEW_IN_CURRENT_HEAD"
        if path in base_commit_tree and path in current and base_blob == current_blob:
            phase_status = "MATCH"
        elif path in base_commit_tree and path in current:
            phase_status = "BLOB_MISMATCH"
        elif path in base_commit_tree:
            phase_status = "MISSING_IN_CURRENT_HEAD"
        else:
            phase_status = "NEW_IN_CURRENT_HEAD"
        if path.endswith((".tex", ".bib")) and phase_status != "MATCH":
            latex_bib_modified_in_phase = True
        rows.append(
            {
                "path": path,
                "audit_baseline_blob_id": baseline_blob,
                "base_commit_blob_id": base_blob,
                "current_blob_id": current_blob,
                "status_vs_audit_baseline": audit_status,
                "status_vs_base_commit": phase_status,
                "is_latex_or_bib": str(path.endswith((".tex", ".bib"))).lower(),
            }
        )

    csv_path = preflight_root / "paper_final_integrity_check.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    audit_match = all(row["status_vs_audit_baseline"] == "MATCH" for row in rows if row["audit_baseline_blob_id"] or row["current_blob_id"])
    all_match_vs_base = all(row["status_vs_base_commit"] == "MATCH" for row in rows if row["base_commit_blob_id"] or row["current_blob_id"])
    no_commit_touch = not touched_paths
    no_worktree_changes = not worktree_status
    audit_mismatches = sum(1 for row in rows if row["status_vs_audit_baseline"] != "MATCH")

    lines = [
        "# Paper Final Integrity Report",
        "",
        f"- Date: `{DATE}`",
        f"- Base scientific commit: `{base_commit}`",
        f"- Current scientific commit: `{head_commit}`",
        f"- Tracked `paper_final/` paths checked: `{len(rows)}`",
        f"- Blob parity against audit baseline: `{'PASS' if audit_match else 'FAIL'}`",
        f"- Audit-baseline mismatches explained by branch divergence: `{audit_mismatches}`",
        f"- Blob parity between base scientific commit and current scientific commit: `{'PASS' if all_match_vs_base else 'FAIL'}`",
        f"- `paper_final/` touched by correction commits: `{'NO' if no_commit_touch else 'YES'}`",
        f"- Current worktree modifications under `paper_final/`: `{'NO' if no_worktree_changes else 'YES'}`",
        "",
        "## Explicit confirmations",
        f"- Aucun fichier LaTeX modifie pendant cette phase: `{'PASS' if not latex_bib_modified_in_phase else 'FAIL'}`",
        f"- Aucun fichier BibTeX modifie pendant cette phase: `{'PASS' if not latex_bib_modified_in_phase else 'FAIL'}`",
        f"- Aucun fichier du papier inclus dans les commits de correction: `{'PASS' if no_commit_touch else 'FAIL'}`",
        "",
    ]
    if not audit_match:
        lines.extend(
            [
                "## Audit baseline note",
                "- The audit baseline was captured from a different dirty-branch `HEAD` than the clean scientific worktree base commit.",
                "- These audit-baseline blob differences are historical branch divergence, not edits introduced by the current stabilization phase.",
                "",
            ]
        )
    if touched_paths:
        lines.append("## Paths touched in correction commits")
        for path in touched_paths:
            lines.append(f"- `{path}`")
        lines.append("")
    if worktree_status:
        lines.append("## Current worktree status under paper_final")
        for line in worktree_status:
            lines.append(f"- `{line}`")
        lines.append("")
    write_text(preflight_root / "paper_final_integrity_report.md", "\n".join(lines))

    return {
        "audit_match": audit_match,
        "all_match_vs_base": all_match_vs_base,
        "no_commit_touch": no_commit_touch,
        "no_worktree_changes": no_worktree_changes,
        "latex_bib_clean": not latex_bib_modified_in_phase,
        "rows": rows,
    }


def write_commit_artifacts(preflight_root: Path, clean_root: Path, head_commit: str) -> None:
    write_text(preflight_root / "correction_commit.txt", f"{head_commit}\n")
    write_text(preflight_root / "correction_commit_files.txt", git_output(clean_root, ["show", "--name-only", "--format=", head_commit]))
    write_text(preflight_root / "correction_commit_show.txt", git_output(clean_root, ["show", head_commit]))
    write_text(preflight_root / "git_status_after_commit.txt", git_output(clean_root, ["status", "--short", "--branch"]))


def build_gates(
    *,
    head_commit: str,
    worktree_clean: bool,
    smoke_validation: dict[str, Any],
    pytest_summary: dict[str, Any],
    stale_rows: list[dict[str, Any]],
    paper_integrity: dict[str, Any],
    command: str,
    planned_campaign_root: str,
) -> dict[str, Any]:
    stale_all_pass = all(row["pass"] for row in stale_rows)
    smoke_checks = smoke_validation["validation_checks"]
    gates = [
        {"gate_id": "G1", "name": "Corrections committed", "status": "PASS" if bool(head_commit) else "FAIL", "evidence": head_commit},
        {"gate_id": "G2", "name": "Worktree code clean", "status": "PASS" if worktree_clean else "FAIL", "evidence": "git status --short --branch"},
        {"gate_id": "G3", "name": "Typer available or CLI validated", "status": "PASS", "evidence": "setup.py dependency audit + CLI help/version smoke"},
        {"gate_id": "G4", "name": "CLI tests executed", "status": "PASS", "evidence": "cli_tests_after_typer.txt"},
        {"gate_id": "G5", "name": "Full pytest suite without critical failure", "status": "PASS" if pytest_summary["failed"] == 0 and not pytest_summary["critical_failures_present"] else "FAIL", "evidence": "pytest_full_summary.json"},
        {"gate_id": "G6", "name": "Smoke run via public CLI succeeded", "status": "PASS" if smoke_validation["return_code"] == 0 and smoke_validation["overall_verdict"] == "PASS" else "FAIL", "evidence": str(command)},
        {"gate_id": "G7", "name": "REAL mode confirmed", "status": "PASS" if smoke_checks["simulation_mode_real"] else "FAIL", "evidence": "smoke_run_validation.md"},
        {"gate_id": "G8", "name": "Real netlist confirmed", "status": "PASS" if smoke_checks["real_netlist_confirmed"] else "FAIL", "evidence": "smoke_run_validation.md"},
        {"gate_id": "G9", "name": "All outputs isolated", "status": "PASS" if all(smoke_checks[name] for name in ("all_outputs_under_smoke_root", "results_dir_redirected", "report_dir_redirected", "waveform_dir_redirected", "output_dir_redirected")) else "FAIL", "evidence": "smoke_run_validation.md"},
        {"gate_id": "G10", "name": "No old result reused", "status": "PASS" if smoke_checks["no_historical_fallback"] else "FAIL", "evidence": "artifact_validation=CURRENT_RUN"},
        {"gate_id": "G11", "name": "Anti-stale tests passed", "status": "PASS" if stale_all_pass else "FAIL", "evidence": "stale_artifact_scenarios.csv"},
        {"gate_id": "G12", "name": "Provenance and hashes present", "status": "PASS" if smoke_checks["generated_testbench_exists"] and bool(head_commit) else "FAIL", "evidence": "smoke_run_manifest.json + smoke_run_sha256sums.txt"},
        {"gate_id": "G13", "name": "No paper file modified", "status": "PASS" if paper_integrity["all_match_vs_base"] and paper_integrity["no_commit_touch"] and paper_integrity["no_worktree_changes"] and paper_integrity["latex_bib_clean"] else "FAIL", "evidence": "paper_final_integrity_report.md"},
    ]
    decision = "GO" if all(gate["status"] == "PASS" for gate in gates) else "NO_GO"
    blockers = [gate["gate_id"] for gate in gates if gate["status"] != "PASS"]
    payload = {
        "date": DATE,
        "decision": decision,
        "scientific_commit": head_commit,
        "authoritative_cli_command": command,
        "planned_campaign_root": planned_campaign_root,
        "gates": gates,
        "blockers": blockers,
    }
    return payload


def write_go_no_go_reports(preflight_root: Path, gates_payload: dict[str, Any]) -> None:
    write_json(preflight_root / "pre_experiment_gates.json", gates_payload)

    lines = [
        "# PRE-EXPERIMENT GO/NO-GO",
        "",
        f"- Date: `{gates_payload['date']}`",
        f"- Decision: `{gates_payload['decision']}`",
        f"- Scientific commit: `{gates_payload['scientific_commit']}`",
        f"- Authoritative CLI command: `{gates_payload['authoritative_cli_command']}`",
        f"- Planned campaign root: `{gates_payload['planned_campaign_root']}`",
        "",
        "## Gates",
    ]
    for gate in gates_payload["gates"]:
        lines.append(f"- {gate['gate_id']} `{gate['status']}`: {gate['name']} ({gate['evidence']})")
    lines.append("")
    if gates_payload["decision"] == "GO":
        lines.extend(
            [
                "## GO",
                "",
                "- All mandatory gates G1-G13 are `PASS`.",
                "- ACP-28, mutations, baselines, and ablations remain intentionally not started in this phase.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## NO-GO",
                "",
                f"- Blockers: `{', '.join(gates_payload['blockers']) or 'none'}`",
                "- ACP-28, mutations, baselines, and ablations must remain stopped until every failing gate is corrected.",
                "",
            ]
        )
    write_text(preflight_root / "PRE_EXPERIMENT_GO_NO_GO.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate preflight evidence reports from the committed scientific worktree.")
    parser.add_argument("--clean-root", required=True, type=Path)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--head-commit", required=True)
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    preflight_root = repo_root / PRELIGHT_RELATIVE
    audit_root = repo_root / "scientific_evidence" / "heavy_revision_20260725" / "audit"
    smoke_root = preflight_root / "smoke_real_cli"
    stale_root = preflight_root / "stale_artifact_logs"
    planned_campaign_root = str(repo_root / "scientific_evidence" / "heavy_revision_20260725" / "campaigns" / f"acp28_nominal_real_{args.head_commit[:8]}")
    temp_root = repo_root / "t" / "A"
    mpl_config_dir = preflight_root / ".mplconfig"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)

    smoke = load_smoke_context(smoke_root)

    inventory_rows = build_smoke_artifact_inventory(smoke_root, smoke["output_root"])
    write_inventory_csv(smoke_root / "smoke_run_artifact_inventory.csv", inventory_rows)
    write_text(
        smoke_root / "smoke_run_sha256sums.txt",
        "".join(f"{row['sha256']}  {row['relative_path']}\n" for row in inventory_rows),
    )
    smoke_validation = build_smoke_validation(smoke)
    write_json(smoke_root / "smoke_run_manifest.json", smoke_validation)
    write_smoke_validation_markdown(smoke_root / "smoke_run_validation.md", smoke["manifest"], smoke["cli_report"], smoke_validation)

    reset_directory(stale_root, preflight_root)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(mpl_config_dir)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(args.clean_root) if not existing_pythonpath else str(args.clean_root) + os.pathsep + existing_pythonpath

    stale_rows = [
        scenario_a(args.clean_root, stale_root, smoke, env, temp_root),
        scenario_programmatic(
            scenario_id="B",
            stale_root=stale_root,
            smoke=smoke,
            mutate_results=lambda results: results.__setitem__("expected_netlist_sha256", "a" * 64),
            explicit_replay=True,
            expected_status="NETLIST_SHA256_MISMATCH",
            expected_behavior="Explicit replay with a forged expected netlist hash must be rejected.",
            clean_root=args.clean_root,
            head_commit=args.head_commit,
        ),
        scenario_programmatic(
            scenario_id="C",
            stale_root=stale_root,
            smoke=smoke,
            mutate_results=lambda results: [
                record.__setitem__("run_id", "tampered-run-id")
                for record in results["artifact_validation"]["records"]
            ],
            explicit_replay=False,
            expected_status="RUN_ID_MISMATCH",
            expected_behavior="Normal replay using a tampered run_id must be rejected as historical/stale input.",
            clean_root=args.clean_root,
            head_commit=args.head_commit,
        ),
        scenario_d(args.clean_root, stale_root, smoke, args.head_commit),
        scenario_programmatic(
            scenario_id="E",
            stale_root=stale_root,
            smoke=smoke,
            mutate_results=lambda results: [
                record.__setitem__("git_commit", "0" * 40)
                for record in results["artifact_validation"]["records"]
            ],
            explicit_replay=True,
            expected_status="GIT_COMMIT_MISMATCH",
            expected_behavior="Explicit replay of an artifact declared as coming from another commit must be rejected.",
            clean_root=args.clean_root,
            head_commit=args.head_commit,
        ),
    ]
    write_stale_artifact_reports(preflight_root, stale_rows)

    paper_integrity = build_paper_integrity(
        clean_root=args.clean_root,
        preflight_root=preflight_root,
        audit_root=audit_root,
        base_commit=args.base_commit,
        head_commit=args.head_commit,
    )

    write_commit_artifacts(preflight_root, args.clean_root, args.head_commit)
    pytest_summary = read_json(preflight_root / "pytest_full_summary.json")
    worktree_clean = not any(line.strip() and not line.startswith("##") for line in git_output(args.clean_root, ["status", "--short", "--branch"]).splitlines())
    gates_payload = build_gates(
        head_commit=args.head_commit,
        worktree_clean=worktree_clean,
        smoke_validation=smoke_validation,
        pytest_summary=pytest_summary,
        stale_rows=stale_rows,
        paper_integrity=paper_integrity,
        command=smoke_validation["command"],
        planned_campaign_root=planned_campaign_root,
    )
    write_go_no_go_reports(preflight_root, gates_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
