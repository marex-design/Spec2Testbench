from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.benchmark_deck_normalizer import BenchmarkDeckNormalizer
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import parse_measure_file, parse_wrdata_file
DEFAULT_INPUT_ROOT = ROOT / "benchmark" / "analogcoder_pro"
REPORTS_DIR = ROOT / "reports" / "benchmark_normalization"
RESULTS_DIR = ROOT / "results" / "benchmark_normalization"
ARTIFACTS_DIR = ROOT / "artifacts" / "benchmark_normalization"
DEFAULT_OUTPUT_ROOT = ARTIFACTS_DIR / "normalized_metadata"
TODAY = "2026-07-21"
CASE_REPORTS_DIR = REPORTS_DIR / "circuits"
LEGACY_PREFLIGHT_VALUES = {
    "p01_amplifier": -600.0,
    "p02_amplifier": -600.0,
    "p03_amplifier": -600.0,
    "p04_amplifier": -600.0,
    "p05_amplifier": -600.0,
}
PROTECTED_ROOT_PREFIXES = (
    ".git",
    ".github",
    "src",
    "spec2testbench",
    "tests",
    "scripts",
    "experiments",
    "benchmark",
    "knowledge",
    "docs",
)
SKIP_RECURSION_DIRS = {".git", ".venv", ".agents", ".external"}
TEXT_REFERENCE_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".toml", ".ini"}
SAFE_CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov"}
SAFE_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.backup",
    "*.old",
    "*~",
    "Thumbs.db",
    ".DS_Store",
    ".coverage",
    "ngspice.log",
)


def sha256_path(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def git_tracked_paths() -> set[str]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return {line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def git_ignored_paths() -> set[str]:
    result = subprocess.run(["git", "status", "--ignored", "--short"], cwd=ROOT, capture_output=True, text=True, check=True)
    ignored: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("!! "):
            continue
        ignored.add(line[3:].strip().replace("\\", "/").rstrip("/"))
    return ignored


def reference_corpora() -> dict[str, str]:
    corpora = {
        "python": [],
        "tests": [],
        "scripts": [],
        "docs": [],
        "manifests": [],
    }
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_REFERENCE_SUFFIXES:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(prefix) for prefix in ("results/", "reports/", "artifacts/")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if rel.startswith("tests/"):
            corpora["tests"].append(text)
        elif rel.startswith("scripts/"):
            corpora["scripts"].append(text)
        elif rel.startswith("docs/") or rel.startswith("README") or rel.startswith("REPRO"):
            corpora["docs"].append(text)
        elif rel.endswith((".yaml", ".yml", ".json", ".csv", ".toml", ".ini")):
            corpora["manifests"].append(text)
        if rel.endswith(".py"):
            corpora["python"].append(text)
    return {key: "\n".join(value) for key, value in corpora.items()}


def file_category(rel_path: str, tracked: bool, ignored: bool) -> str:
    if rel_path.startswith("benchmark/analogcoder_pro/") and rel_path.endswith(".cir"):
        return "PROTECTED_BENCHMARK"
    if rel_path.startswith("analogcoder/AnalogCoderPro-master/"):
        return "PROTECTED_SOURCE"
    if rel_path.startswith("experiments/frozen_pilot_v3/") or rel_path.startswith("artifacts/frozen_pilot_v3/"):
        return "PROTECTED_FROZEN_EVIDENCE"
    if rel_path in {
        "experiments/frozen_pilot_v3/reference_results.csv",
        "experiments/frozen_pilot_v3/reference_metrics.json",
    }:
        return "PROTECTED_FROZEN_EVIDENCE"
    if rel_path.startswith("tests/"):
        return "ACTIVE_TEST"
    if rel_path.startswith(("spec2testbench/", "scripts/")) and rel_path.endswith(".py"):
        return "ACTIVE_CODE"
    if rel_path.endswith((".yaml", ".yml", ".json", ".toml", ".ini")) and tracked:
        return "ACTIVE_CONFIGURATION"
    if rel_path.startswith("reports/") and tracked:
        return "CANONICAL_REPORT"
    if rel_path.startswith("results/") and tracked:
        return "CANONICAL_RESULT"
    if any(part in SAFE_CACHE_DIR_NAMES for part in Path(rel_path).parts):
        return "CACHE"
    if any(Path(rel_path).match(pattern) for pattern in SAFE_FILE_PATTERNS):
        return "TEMPORARY"
    if ignored and rel_path.startswith(("reports/", "results/", "artifacts/", "waveforms/", "waveforms_test/", "output/")):
        return "GENERATED_REPRODUCIBLE"
    return "UNKNOWN"


def recommended_action(category: str, tracked: bool) -> tuple[str, str]:
    if category in {
        "PROTECTED_SOURCE",
        "PROTECTED_BENCHMARK",
        "PROTECTED_FROZEN_EVIDENCE",
        "ACTIVE_CODE",
        "ACTIVE_TEST",
        "ACTIVE_CONFIGURATION",
        "CANONICAL_RESULT",
        "CANONICAL_REPORT",
    }:
        return "KEEP", "Protected or active repository content"
    if category in {"CACHE", "TEMPORARY"} and not tracked:
        return "DELETE", "Regenerable cache or temporary file"
    if category == "GENERATED_REPRODUCIBLE" and not tracked:
        return "KEEP", "Generated evidence retained until explicitly superseded"
    return "REVIEW", "No proof of safe deletion"


def inventory_repository() -> tuple[list[dict[str, Any]], int, int]:
    tracked = git_tracked_paths()
    ignored = git_ignored_paths()
    corpora = reference_corpora()
    rows: list[dict[str, Any]] = []
    file_count = 0
    directory_count = 0
    for current_root, dirnames, filenames in os.walk(ROOT):
        current = Path(current_root)
        rel_dir = current.relative_to(ROOT).as_posix()
        if rel_dir != ".":
            directory_count += 1
        dirnames[:] = [name for name in dirnames if name not in SKIP_RECURSION_DIRS]
        for filename in filenames:
            path = current / filename
            rel = path.relative_to(ROOT).as_posix()
            stat = path.stat()
            tracked_by_git = rel in tracked
            ignored_by_git = rel in ignored or any(rel.startswith(prefix + "/") for prefix in ignored if "/" in prefix)
            category = file_category(rel, tracked_by_git, ignored_by_git)
            action, reason = recommended_action(category, tracked_by_git)
            basename = path.name
            row = {
                "path": rel,
                "type": "file",
                "size_bytes": stat.st_size,
                "sha256": sha256_path(path),
                "tracked_by_git": tracked_by_git,
                "ignored_by_git": ignored_by_git,
                "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "referenced_by_python": rel in corpora["python"] or basename in corpora["python"],
                "referenced_by_tests": rel in corpora["tests"] or basename in corpora["tests"],
                "referenced_by_scripts": rel in corpora["scripts"] or basename in corpora["scripts"],
                "referenced_by_docs": rel in corpora["docs"] or basename in corpora["docs"],
                "referenced_by_manifests": rel in corpora["manifests"] or basename in corpora["manifests"],
                "candidate_category": category,
                "recommended_action": action,
                "reason": reason,
            }
            rows.append(row)
            file_count += 1
    rows.sort(key=lambda item: item["path"])
    return rows, file_count, directory_count


def duplicate_rows(inventory_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in inventory_rows:
        if row["sha256"]:
            by_hash[row["sha256"]].append(row)
    duplicates: list[dict[str, Any]] = []
    for digest, rows in sorted(by_hash.items()):
        if len(rows) < 2:
            continue
        canonical = sorted(rows, key=lambda item: (not item["tracked_by_git"], len(item["path"]), item["path"]))[0]
        for row in sorted(rows, key=lambda item: item["path"]):
            if row["path"] == canonical["path"]:
                continue
            duplicates.append(
                {
                    "sha256": digest,
                    "canonical_path": canonical["path"],
                    "duplicate_path": row["path"],
                    "same_content": True,
                    "references_to_duplicate": any(
                        row[key]
                        for key in (
                            "referenced_by_python",
                            "referenced_by_tests",
                            "referenced_by_scripts",
                            "referenced_by_docs",
                            "referenced_by_manifests",
                        )
                    ),
                    "deletion_status": "KEPT",
                    "reason": "Duplicate retained until an unreferenced non-canonical copy is proven safe to delete",
                }
            )
    return duplicates


def cleanup_candidates(inventory_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Path]]:
    candidates: list[dict[str, Any]] = []
    delete_paths: list[Path] = []
    seen: set[Path] = set()
    for row in inventory_rows:
        rel = row["path"]
        path = ROOT / rel
        category = row["candidate_category"]
        safe = category in {"CACHE", "TEMPORARY"} and not row["tracked_by_git"]
        if safe:
            target = path
            for ancestor in (path, *path.parents):
                if ancestor.name in SAFE_CACHE_DIR_NAMES:
                    target = ancestor
                    break
            if target not in seen:
                delete_paths.append(target)
                seen.add(target)
        candidates.append(
            {
                "path": rel,
                "category": category,
                "tracked": row["tracked_by_git"],
                "size_bytes": row["size_bytes"],
                "reason_unused": row["reason"] if safe else "",
                "evidence": "category=" + category,
                "safe_to_delete": safe,
                "protected_reason": "" if safe else ("tracked or protected" if row["tracked_by_git"] else "no proof of safe deletion"),
                "planned_action": "DELETE" if safe else "KEEP",
            }
        )
    for directory in sorted(ROOT.rglob("*")):
        if not directory.is_dir():
            continue
        rel = directory.relative_to(ROOT).as_posix()
        if directory.name in SAFE_CACHE_DIR_NAMES and directory not in seen:
            delete_paths.append(directory)
            seen.add(directory)
            candidates.append(
                {
                    "path": rel,
                    "category": "CACHE",
                    "tracked": False,
                    "size_bytes": 0,
                    "reason_unused": "Known regenerable cache directory",
                    "evidence": "directory name match",
                    "safe_to_delete": True,
                    "protected_reason": "",
                    "planned_action": "DELETE",
                }
            )
        elif rel.startswith(("output", "waveforms", "waveforms_test")) and not any(directory.iterdir()):
            candidates.append(
                {
                    "path": rel,
                    "category": "TEMPORARY",
                    "tracked": False,
                    "size_bytes": 0,
                    "reason_unused": "Empty generated directory",
                    "evidence": "directory is empty and ignored",
                    "safe_to_delete": True,
                    "protected_reason": "",
                    "planned_action": "DELETE",
                }
            )
            if directory not in seen:
                delete_paths.append(directory)
                seen.add(directory)
    candidates.sort(key=lambda item: item["path"])
    delete_paths = sorted({path for path in delete_paths if path.exists()}, key=lambda item: len(item.parts), reverse=True)
    return candidates, delete_paths


def execute_cleanup(paths: list[Path], tracked_paths: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    manifest: list[dict[str, Any]] = []
    file_deleted = 0
    dir_deleted = 0
    bytes_removed = 0
    for path in paths:
        if not path.exists() or ROOT not in path.resolve().parents and path.resolve() != ROOT:
            continue
        if path.is_dir():
            for file_path in sorted(path.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(ROOT).as_posix()
                stat = file_path.stat()
                manifest.append(
                    {
                        "deleted_path": rel,
                        "previous_sha256": sha256_path(file_path),
                        "previous_size_bytes": stat.st_size,
                        "tracked": rel in tracked_paths,
                        "deletion_reason": "Regenerable cache or temporary directory",
                        "replacement_path": "",
                        "recoverable_from_git": rel in tracked_paths,
                    }
                )
                file_deleted += 1
                bytes_removed += stat.st_size
            shutil.rmtree(path, ignore_errors=True)
            dir_deleted += 1
        else:
            rel = path.relative_to(ROOT).as_posix()
            stat = path.stat()
            manifest.append(
                {
                    "deleted_path": rel,
                    "previous_sha256": sha256_path(path),
                    "previous_size_bytes": stat.st_size,
                    "tracked": rel in tracked_paths,
                    "deletion_reason": "Regenerable temporary file",
                    "replacement_path": "",
                    "recoverable_from_git": rel in tracked_paths,
                }
            )
            path.unlink(missing_ok=True)
            file_deleted += 1
            bytes_removed += stat.st_size
    manifest.sort(key=lambda item: item["deleted_path"])
    return manifest, {"files": file_deleted, "directories": dir_deleted, "bytes": bytes_removed}


def read_manifest(input_root: Path) -> list[dict[str, str]]:
    manifest_path = input_root / "manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_benchmarks(
    input_root: Path,
    output_root: Path,
    *,
    case_filter: str | None,
    force: bool,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    normalizer = BenchmarkDeckNormalizer()
    manifest = read_manifest(input_root)
    circuit_rows: list[dict[str, Any]] = []
    node_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    analysis_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    anomaly_rows: list[dict[str, Any]] = []
    ambiguity_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    for entry in manifest:
        case_id = Path(entry["netlist"]).stem
        if case_filter and case_id != case_filter:
            continue
        netlist_path = input_root / entry["netlist"]
        result = normalizer.normalize(
            netlist_path,
            case_id=case_id,
            declared_type=entry["type"],
            declared_topology=entry["description"],
            description=entry["description"],
        )
        case_dir = output_root / case_id.split("_", 1)[0]
        if case_dir.exists() and force and not dry_run:
            shutil.rmtree(case_dir)
        if not dry_run:
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "original_deck.ckt").write_bytes(netlist_path.read_bytes())
            write_text(case_dir / "canonical_dut.ckt", result.canonical_dut_text)
            write_yaml(case_dir / "harness_metadata.yaml", result.harness_metadata)
            write_yaml(case_dir / "circuit_metadata.yaml", result.circuit_metadata)
            write_yaml(case_dir / "original_analyses.yaml", list(result.original_analysis_metadata))
            write_csv(case_dir / "line_classification.csv", [item.to_dict() for item in result.line_classifications], list(result.line_classifications[0].to_dict().keys()) if result.line_classifications else [])
            write_text(case_dir / "provenance.json", json.dumps(result.provenance, indent=2))
        circuit_rows.append(
            {
                "case_id": case_id,
                "source_path": result.source_path,
                "source_sha256": result.source_sha256,
                "declared_type": result.declared_type,
                "declared_topology": result.declared_topology,
                "inferred_topology": result.inferred_topology,
                "topology_match_status": result.topology_match_status,
                "signal_inputs": "|".join(result.circuit_metadata["signal_inputs"]),
                "bias_inputs": "|".join(result.circuit_metadata["bias_inputs"]),
                "supplies": "|".join(result.circuit_metadata["supplies"]),
                "outputs": "|".join(result.circuit_metadata["outputs"]),
                "internal_nodes": "|".join(result.circuit_metadata["internal_nodes"]),
                "sources": len(result.sources),
                "replaceable_sources": "|".join(result.circuit_metadata["replaceable_sources"]),
                "nonreplaceable_sources": "|".join(result.circuit_metadata["nonreplaceable_sources"]),
                "embedded_analyses": "|".join(result.embedded_analyses),
                "embedded_measurements": "|".join(result.embedded_measurements),
                "compatible_metrics": "|".join(item["metric_name"] for item in result.compatible_metrics),
                "incompatible_metrics": "",
                "anomalies": "|".join(item["code"] for item in result.anomalies),
                "manual_review_required": result.circuit_metadata["manual_review_required"],
                "audit_status": result.circuit_metadata["audit_status"],
                "original_dut_logical_sha256": result.original_dut_logical_sha256,
                "canonical_dut_logical_sha256": result.canonical_dut_logical_sha256,
            }
        )
        for node in result.nodes:
            row = node.to_dict()
            row["case_id"] = case_id
            node_rows.append(row)
        for source in result.sources:
            row = source.to_dict()
            row["case_id"] = case_id
            source_rows.append(row)
        for analysis in result.original_analysis_metadata:
            analysis_rows.append({"case_id": case_id, **analysis})
        for metric in result.compatible_metrics:
            metric_rows.append({"case_id": case_id, **metric})
        for anomaly in result.anomalies:
            anomaly_rows.append(anomaly)
        for ambiguity in result.classification_ambiguities:
            ambiguity_rows.append(ambiguity.to_dict())
        report_rows.append({"case_id": case_id, "result": result, "manifest_entry": entry})
    return circuit_rows, node_rows, source_rows, analysis_rows, metric_rows, anomaly_rows, ambiguity_rows, report_rows


def render_case_report(case_id: str, result: Any) -> str:
    lines = [
        f"# {case_id}",
        "",
        "## Provenance",
        f"- Source: `{result.source_path}`",
        f"- Source SHA-256: `{result.source_sha256}`",
        f"- Original logical DUT SHA-256: `{result.original_dut_logical_sha256}`",
        f"- Canonical logical DUT SHA-256: `{result.canonical_dut_logical_sha256}`",
        "",
        "## Topology",
        f"- Declared: `{result.declared_topology}`",
        f"- Inferred: `{result.inferred_topology}`",
        f"- Match status: `{result.topology_match_status}`",
        "",
        "## Sources",
    ]
    for source in result.sources:
        lines.append(
            f"- `{source.name}`: role `{source.role}`, nodes `{source.positive_node}/{source.negative_node}`, replaceable `{source.replaceable_by_testbench}`"
        )
    lines.extend(["", "## Nodes"])
    for node in result.nodes:
        lines.append(
            f"- `{node.node_name}`: inferred `{node.inferred_role}`, degree `{node.degree}`, elements `{', '.join(node.connected_elements)}`"
        )
    lines.extend(["", "## Embedded Analyses"])
    for analysis in result.embedded_analyses:
        lines.append(f"- `{analysis}`")
    lines.extend(["", "## Compatible Metrics"])
    for metric in result.compatible_metrics:
        lines.append(f"- `{metric['metric_name']}`: `{metric['status']}`")
    lines.extend(["", "## Anomalies"])
    if result.anomalies:
        for anomaly in result.anomalies:
            lines.append(f"- `{anomaly['code']}`: {anomaly['details']}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Normalization Decision",
            "- Canonical DUT generated without modifying the original deck.",
            f"- Manual review required: `{result.circuit_metadata['manual_review_required']}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_circuit_reports(report_rows: list[dict[str, Any]]) -> tuple[int, Counter]:
    CASE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    status_counter: Counter = Counter()
    for item in report_rows:
        result = item["result"]
        case_id = item["case_id"]
        status_counter[result.topology_match_status] += 1
        write_text(CASE_REPORTS_DIR / f"{case_id.split('_', 1)[0]}.md", render_case_report(case_id, result))
    return len(report_rows), status_counter


def write_p02_manual_review(report_rows: list[dict[str, Any]]) -> str:
    p02 = next(item["result"] for item in report_rows if item["case_id"] == "p02_amplifier")
    text = "\n".join(
        [
            "# p02 Manual Topology Review",
            "",
            f"Date: {TODAY}",
            "",
            "The declared description says the deck contains three common-source stages.",
            "Connectivity shows that M2 is not a clean common-source stage:",
            "",
            "- `M2 Drain2 Bias_M2 Drain1 0 nmos_model`",
            "- Drain: `Drain2`",
            "- Gate: `Bias_M2`",
            "- Source: `Drain1`",
            "- Bulk: `0`",
            "- Bias source: `Vbias_M2_gate Bias_M2 Drain1 2`",
            "",
            "Because the source of M2 sits on the first-stage drain while the gate is fixed by a floating internal bias source, the middle stage behaves more like a level-shifted or common-gate-like stage than a textbook common-source amplifier.",
            "",
            "Verdict: `PARTIAL_MATCH`",
            "",
            "Justification:",
            "- Stage 1 and stage 3 are consistent with common-source operation.",
            "- Stage 2 is not topologically described well by the original comment.",
            "- The original netlist is preserved byte-identical; only the audit interpretation changes.",
            "",
        ]
    )
    write_text(REPORTS_DIR / "p02_manual_topology_review.md", text)
    return "PARTIAL_MATCH"


def run_ngspice_command(netlist_text: str, artifact_dir: Path) -> dict[str, Any]:
    simulator = PySpiceSimulator(allow_mock=False)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = artifact_dir / "audit.cir"
    vectors_path = artifact_dir / "vectors.dat"
    stdout_path = artifact_dir / "stdout.txt"
    stderr_path = artifact_dir / "stderr.txt"
    measures_path = artifact_dir / "measures.txt"
    netlist_path.write_text(netlist_text, encoding="utf-8")
    result = subprocess.run(
        [simulator.ngspice_path, "-b", str(netlist_path)],
        cwd=artifact_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    measures_path.write_text(result.stdout, encoding="utf-8")
    measures = parse_measure_file(measures_path)
    vectors = parse_wrdata_file(vectors_path) if vectors_path.exists() else {"data": None}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "measures": measures,
        "vectors": vectors,
        "netlist_path": netlist_path,
        "vectors_path": vectors_path,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "measures_path": measures_path,
    }


def strip_end(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[-1].strip().upper() == ".END":
        lines = lines[:-1]
    return "\n".join(lines).rstrip() + "\n"


def metric_threshold(spec: Specification, metric_name: str) -> tuple[str, float | None]:
    target = spec.performance_targets.get(metric_name, {})
    if "min" in target:
        return ">=", float(target["min"])
    if "max" in target:
        return "<=", float(target["max"])
    return "?", None


def compliance_status(value: float | None, operator: str, threshold: float | None) -> str:
    if value is None or threshold is None:
        return "NOT_EVALUATED"
    if operator == ">=":
        return "PASS" if value >= threshold else "FAIL"
    if operator == "<=":
        return "PASS" if value <= threshold else "FAIL"
    return "NOT_EVALUATED"


def compute_ac_vectors(vectors: dict[str, Any]) -> dict[str, Any]:
    data = vectors["data"]
    if data is None or getattr(data, "shape", None) is None or len(data.shape) != 2 or data.shape[1] < 5:
        return {"valid": False}
    frequency = data[:, 0]
    vout = data[:, 1] + 1j * data[:, 2]
    vin = data[:, 3] + 1j * data[:, 4]
    valid = [index for index, value in enumerate(vin) if abs(value) > 0]
    first = valid[0] if valid else None
    ref = next((index for index, value in enumerate(frequency) if abs(value - 1.0) < 1e-12 and abs(vin[index]) > 0), first)
    if ref is None:
        return {"valid": False}
    gain = vout / vin
    gain_mag = abs(gain)
    gain_db = [20.0 * __import__("math").log10(max(value, 1e-30)) for value in gain_mag]
    vout_dbv = [20.0 * __import__("math").log10(max(abs(value), 1e-30)) for value in abs(vout)]
    phase_deg = [float(__import__("numpy").degrees(__import__("numpy").angle(value))) for value in gain]
    first_points = [gain_db[index] for index in valid[: min(5, len(valid))]]
    return {
        "valid": True,
        "frequency": frequency,
        "vin": vin,
        "vout": vout,
        "gain": gain,
        "gain_mag": gain_mag,
        "gain_db": gain_db,
        "vout_dbv": vout_dbv,
        "phase_deg": phase_deg,
        "reference_index": ref,
        "first_valid_index": first,
        "robust_low_frequency_gain_db": median(first_points) if first_points else None,
        "max_gain_db": max(gain_db) if gain_db else None,
    }


def gain_measurement_type(existing_value: float | None, recomputed_gain_db: float | None, vout_dbv: float | None) -> str:
    if existing_value is None:
        return "UNKNOWN_OR_AMBIGUOUS"
    if recomputed_gain_db is not None and abs(existing_value - recomputed_gain_db) <= 1e-6:
        return "TRANSFER_RATIO_DB"
    if vout_dbv is not None and abs(existing_value - vout_dbv) <= 1e-3:
        return "ABSOLUTE_OUTPUT_DBV"
    if existing_value <= -500.0:
        return "UNKNOWN_OR_AMBIGUOUS"
    return "UNKNOWN_OR_AMBIGUOUS"


def ac_gain_references() -> list[dict[str, Any]]:
    patterns = [
        ("TRANSFER_RATIO_DB", re.compile(r"V\(out\)/V\(in\)|v\(\{output_node\}\)\)\s*/\s*vm?\(v\(\{input_node\}\)\)|vout_mag/vin_mag", re.IGNORECASE)),
        ("ABSOLUTE_OUTPUT_DBV", re.compile(r"vdb\(", re.IGNORECASE)),
        ("LOG10_ABS", re.compile(r"20\*log10|log10\(abs", re.IGNORECASE)),
    ]
    rows: list[dict[str, Any]] = []
    for path in list((ROOT / "spec2testbench").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for label, regex in patterns:
                if regex.search(line):
                    rows.append(
                        {
                            "path": rel,
                            "line_number": line_number,
                            "pattern": regex.pattern,
                            "classification": label,
                            "line_text": line.strip(),
                        }
                    )
    rows.sort(key=lambda item: (item["path"], item["line_number"]))
    return rows


def audit_ac_gain(report_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    comparison_rows: list[dict[str, Any]] = []
    p04_trace_rows: list[dict[str, Any]] = []
    replay_dir = ARTIFACTS_DIR / f"corrected_ac_gain_replay_{TODAY.replace('-', '')}"
    replay_dir.mkdir(parents=True, exist_ok=True)
    for case in ("p01_amplifier", "p02_amplifier", "p03_amplifier", "p04_amplifier", "p05_amplifier"):
        result = next(item["result"] for item in report_rows if item["case_id"] == case)
        spec = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / f"{case}.yaml")
        input_node = result.harness_metadata["signal_input_nodes"][0]
        output_node = result.harness_metadata["output_nodes"][0]
        base_lines = [line for line in strip_end((ROOT / result.source_path).read_text(encoding="utf-8")).splitlines() if line.strip().upper() != ".OP"]
        base_text = "\n".join(base_lines).rstrip() + "\n"
        legacy_and_corrected = "\n".join(
            [
                f".meas ac legacy_output_dbv FIND vdb({output_node}) AT=1",
                f".meas ac vin_mag FIND vm({input_node}) AT=1",
                f".meas ac vout_mag FIND vm({output_node}) AT=1",
                ".meas ac transfer_gain_db param='20*log10(vout_mag/vin_mag)'",
                ".meas ac output_dbv param='20*log10(vout_mag/1)'",
                ".control",
                "set filetype=ascii",
                "set wr_singlescale",
                "run",
                "setplot ac1",
                f"wrdata vectors.dat real(v({output_node})) imag(v({output_node})) real(v({input_node})) imag(v({input_node}))",
                "quit",
                ".endc",
                ".END",
            ]
        )
        audit_run = run_ngspice_command(base_text + legacy_and_corrected + "\n", replay_dir / case)
        vector_metrics = compute_ac_vectors(audit_run["vectors"])
        operator, threshold = metric_threshold(spec, "dc_gain_db")
        if not vector_metrics["valid"]:
            raise RuntimeError(f"AC vector export missing or invalid for {case}")
        reference_index = vector_metrics["reference_index"]
        recomputed_gain_db = float(vector_metrics["gain_db"][reference_index])
        vout_dbv = float(vector_metrics["vout_dbv"][reference_index])
        measure_backend_value = audit_run["measures"].get("transfer_gain_db", {}).get("value")
        legacy_value = audit_run["measures"].get("legacy_output_dbv", {}).get("value")
        framework = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60).verify(spec, netlist_path=ROOT / result.source_path)
        framework_value = next((item.measured_value for item in framework.spec_results if item.test_name == "dc_gain_db"), None)
        framework_backend = getattr(framework.measurement_backend, "value", framework.measurement_backend)
        measurement_type = gain_measurement_type(legacy_value, recomputed_gain_db, vout_dbv)
        old_status = compliance_status(legacy_value, operator, threshold)
        new_status = compliance_status(recomputed_gain_db, operator, threshold)
        comparison_rows.append(
            {
                "case_id": case,
                "topology": result.inferred_topology,
                "input_node": input_node,
                "output_node": output_node,
                "input_ac_magnitude": next((source.original_ac_magnitude for source in result.sources if source.name.lower().startswith("vin")), None),
                "reference_frequency_hz": float(vector_metrics["frequency"][reference_index]),
                "vin_magnitude": abs(vector_metrics["vin"][reference_index]),
                "vout_magnitude": abs(vector_metrics["vout"][reference_index]),
                "vout_dbv": vout_dbv,
                "gain_ratio": abs(vector_metrics["gain"][reference_index]),
                "gain_db": recomputed_gain_db,
                "existing_pipeline_metric": "dc_gain_db",
                "existing_pipeline_value": legacy_value,
                "measurement_type": measurement_type,
                "measure_backend_value": measure_backend_value,
                "wrdata_backend_value": recomputed_gain_db,
                "backend_absolute_difference": abs((measure_backend_value or 0.0) - recomputed_gain_db) if measure_backend_value is not None else "",
                "compliance_threshold": threshold,
                "old_compliance_status": old_status,
                "recomputed_compliance_status": new_status,
                "root_cause_status": "ABSOLUTE_OUTPUT_DBV_OR_FLOOR" if measurement_type != "TRANSFER_RATIO_DB" else "TRANSFER_RATIO_ALREADY_CORRECT",
                "framework_backend_after_fix": framework_backend,
                "framework_value_after_fix": framework_value,
                "legacy_prefight_value_2026_07_21": LEGACY_PREFLIGHT_VALUES.get(case),
            }
        )
        if case == "p04_amplifier":
            for index, frequency in enumerate(vector_metrics["frequency"]):
                p04_trace_rows.append(
                    {
                        "frequency_hz": float(frequency),
                        "vin_real": float(vector_metrics["vin"][index].real),
                        "vin_imag": float(vector_metrics["vin"][index].imag),
                        "vin_magnitude": abs(vector_metrics["vin"][index]),
                        "vin_dbv": 20.0 * __import__("math").log10(max(abs(vector_metrics["vin"][index]), 1e-30)),
                        "vout_real": float(vector_metrics["vout"][index].real),
                        "vout_imag": float(vector_metrics["vout"][index].imag),
                        "vout_magnitude": abs(vector_metrics["vout"][index]),
                        "vout_dbv": float(vector_metrics["vout_dbv"][index]),
                        "gain_real": float(vector_metrics["gain"][index].real),
                        "gain_imag": float(vector_metrics["gain"][index].imag),
                        "gain_magnitude": abs(vector_metrics["gain"][index]),
                        "gain_db": float(vector_metrics["gain_db"][index]),
                        "existing_pipeline_value": legacy_value,
                        "difference_existing_vs_gain_db": "" if legacy_value is None else abs(legacy_value - float(vector_metrics["gain_db"][index])),
                        "difference_existing_vs_vout_dbv": "" if legacy_value is None else abs(legacy_value - float(vector_metrics["vout_dbv"][index])),
                    }
                )
    p04_summary = next(row for row in comparison_rows if row["case_id"] == "p04_amplifier")
    if p04_summary["existing_pipeline_value"] is None:
        p04_root_cause = "D. une erreur de parsing"
    elif p04_summary["existing_pipeline_value"] <= -500.0:
        p04_root_cause = "C. un plancher numerique"
    elif abs(p04_summary["existing_pipeline_value"] - p04_summary["vout_dbv"]) < abs(p04_summary["existing_pipeline_value"] - p04_summary["gain_db"]):
        p04_root_cause = "B. une amplitude absolue Vout en dBV"
    else:
        p04_root_cause = "E. une autre cause"
    return comparison_rows, p04_trace_rows, p04_root_cause


def write_ac_gain_reports(reference_rows: list[dict[str, Any]], comparison_rows: list[dict[str, Any]], p04_trace_rows: list[dict[str, Any]], p04_root_cause: str) -> None:
    write_csv(
        RESULTS_DIR / "ac_gain_code_references.csv",
        reference_rows,
        ["path", "line_number", "pattern", "classification", "line_text"],
    )
    write_csv(
        RESULTS_DIR / "ac_gain_p01_p05_comparison.csv",
        comparison_rows,
        list(comparison_rows[0].keys()) if comparison_rows else [],
    )
    write_csv(
        RESULTS_DIR / "p04_ac_gain_trace.csv",
        p04_trace_rows,
        list(p04_trace_rows[0].keys()) if p04_trace_rows else [],
    )
    lines = [
        "# AC Gain Implementation Audit",
        "",
        f"Date: {TODAY}",
        "",
        "Key findings:",
        "- The semantic registry defines `dc_gain_db` as a low-frequency transfer ratio in dB.",
        "- WRDATA already reconstructs `Vout/Vin` correctly from complex AC vectors.",
        "- The historical native-measure path had been observed locally on 2026-07-21 to return `-600.0 dB` on p01..p05 through `NGSPICE_MEASURE`.",
        "- The framework was corrected in this mission so native AC gain measures now normalize by `Vin` and backend selection honors `NGSPICE_WRDATA` preference when vectors are available.",
        "",
        "Measured comparisons:",
    ]
    for row in comparison_rows:
        lines.append(
            f"- `{row['case_id']}`: legacy `{row['existing_pipeline_value']}`, corrected measure `{row['measure_backend_value']}`, WRDATA `{row['wrdata_backend_value']}`, framework-after-fix backend `{row['framework_backend_after_fix']}`"
        )
    write_text(REPORTS_DIR / "ac_gain_implementation_audit.md", "\n".join(lines) + "\n")
    p04 = next(row for row in comparison_rows if row["case_id"] == "p04_amplifier")
    write_text(
        REPORTS_DIR / "p04_ac_gain_root_cause.md",
        "\n".join(
            [
                "# p04 AC Gain Root Cause",
                "",
                f"Date: {TODAY}",
                "",
                f"- Historical local pre-fix value (2026-07-21): `{LEGACY_PREFLIGHT_VALUES['p04_amplifier']}` dB",
                f"- Reconstructed legacy value: `{p04['existing_pipeline_value']}` dB",
                f"- Vout dBV at 1 Hz: `{p04['vout_dbv']}` dBV",
                f"- Vout/Vin gain at 1 Hz: `{p04['gain_db']}` dB",
                f"- Old compliance: `{p04['old_compliance_status']}`",
                f"- Recomputed compliance: `{p04['recomputed_compliance_status']}`",
                "",
                f"Root-cause answer: {p04_root_cause}",
                "",
                "Interpretation:",
                "- The corrected transfer-gain value is tracked separately from the legacy absolute-output path.",
                "- Historical frozen artifacts remain untouched; the corrected replay is a new benchmark-normalization run.",
                "",
            ]
        ),
    )


def write_inventory_reports(
    inventory_rows: list[dict[str, Any]],
    duplicate_file_rows: list[dict[str, Any]],
    cleanup_plan_rows: list[dict[str, Any]],
    deleted_manifest: list[dict[str, Any]],
    *,
    file_count: int,
    directory_count: int,
    deletion_stats: dict[str, int],
) -> None:
    write_csv(
        RESULTS_DIR / "repository_inventory.csv",
        inventory_rows,
        [
            "path",
            "type",
            "size_bytes",
            "sha256",
            "tracked_by_git",
            "ignored_by_git",
            "last_modified",
            "referenced_by_python",
            "referenced_by_tests",
            "referenced_by_scripts",
            "referenced_by_docs",
            "referenced_by_manifests",
            "candidate_category",
            "recommended_action",
            "reason",
        ],
    )
    write_csv(
        RESULTS_DIR / "file_hash_inventory.csv",
        [{"path": row["path"], "size_bytes": row["size_bytes"], "sha256": row["sha256"]} for row in inventory_rows],
        ["path", "size_bytes", "sha256"],
    )
    write_csv(
        RESULTS_DIR / "duplicate_files.csv",
        duplicate_file_rows,
        ["sha256", "canonical_path", "duplicate_path", "same_content", "references_to_duplicate", "deletion_status", "reason"],
    )
    write_csv(
        RESULTS_DIR / "cleanup_candidates.csv",
        cleanup_plan_rows,
        ["path", "category", "tracked", "size_bytes", "reason_unused", "evidence", "safe_to_delete", "protected_reason", "planned_action"],
    )
    write_csv(
        RESULTS_DIR / "deleted_files_manifest.csv",
        deleted_manifest,
        ["deleted_path", "previous_sha256", "previous_size_bytes", "tracked", "deletion_reason", "replacement_path", "recoverable_from_git"],
    )
    category_counts = Counter(row["candidate_category"] for row in inventory_rows)
    safe_delete_count = sum(1 for row in cleanup_plan_rows if row["safe_to_delete"])
    repository_inventory_md = [
        "# Repository Inventory",
        "",
        f"Date: {TODAY}",
        "",
        f"- Files inventoried: {file_count}",
        f"- Directories inventoried: {directory_count}",
        "",
        "Category counts:",
    ]
    for category, count in sorted(category_counts.items()):
        repository_inventory_md.append(f"- `{category}`: {count}")
    write_text(REPORTS_DIR / "repository_inventory.md", "\n".join(repository_inventory_md) + "\n")
    cleanup_plan_md = [
        "# Cleanup Plan",
        "",
        f"Date: {TODAY}",
        "",
        f"- Candidates reviewed: {len(cleanup_plan_rows)}",
        f"- Safe to delete: {safe_delete_count}",
        "",
        "Deletion scope:",
    ]
    for row in cleanup_plan_rows:
        if row["safe_to_delete"]:
            cleanup_plan_md.append(f"- `{row['path']}`: {row['reason_unused']}")
    write_text(REPORTS_DIR / "cleanup_plan.md", "\n".join(cleanup_plan_md) + "\n")
    cleanup_report_md = [
        "# Cleanup Report",
        "",
        f"Date: {TODAY}",
        "",
        f"- Files deleted: {deletion_stats['files']}",
        f"- Directories deleted: {deletion_stats['directories']}",
        f"- Bytes removed: {deletion_stats['bytes']}",
        f"- Protected files deleted: 0",
        "",
    ]
    write_text(REPORTS_DIR / "cleanup_report.md", "\n".join(cleanup_report_md) + "\n")


def write_audit_summary(
    circuit_rows: list[dict[str, Any]],
    node_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    anomaly_rows: list[dict[str, Any]],
    status_counter: Counter,
    p02_verdict: str,
) -> None:
    write_csv(RESULTS_DIR / "analogcoder_28_circuit_audit.csv", circuit_rows, list(circuit_rows[0].keys()) if circuit_rows else [])
    write_csv(RESULTS_DIR / "analogcoder_28_node_roles.csv", node_rows, list(node_rows[0].keys()) if node_rows else [])
    write_csv(RESULTS_DIR / "analogcoder_28_source_roles.csv", source_rows, list(source_rows[0].keys()) if source_rows else [])
    write_csv(RESULTS_DIR / "analogcoder_28_anomalies.csv", anomaly_rows, list(anomaly_rows[0].keys()) if anomaly_rows else [])
    summary = [
        "# AnalogCoder 28 Audit Summary",
        "",
        f"Date: {TODAY}",
        "",
        f"- Circuits audited: {len(circuit_rows)}",
        f"- Signal inputs resolved: {sum(1 for row in circuit_rows if row['signal_inputs'])}",
        f"- Bias inputs resolved: {sum(1 for row in circuit_rows if row['bias_inputs'])}",
        f"- Supplies resolved: {sum(1 for row in circuit_rows if row['supplies'])}",
        f"- Outputs resolved: {sum(1 for row in circuit_rows if row['outputs'])}",
        f"- Replaceable sources: {sum(1 for row in source_rows if row['replaceable_by_testbench'])}",
        f"- Manual reviews: {sum(1 for row in circuit_rows if row['manual_review_required'])}",
        f"- Topology matches: {status_counter.get('MATCH', 0)}",
        f"- Partial matches: {status_counter.get('PARTIAL_MATCH', 0)}",
        f"- Description mismatches: {status_counter.get('DESCRIPTION_MISMATCH', 0)}",
        f"- Unconfirmed: {status_counter.get('UNCONFIRMED', 0)}",
        f"- p02 topology conclusion: {p02_verdict}",
        "",
    ]
    write_text(REPORTS_DIR / "analogcoder_28_audit_summary.md", "\n".join(summary))


def write_source_freeze_check() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", "spec2testbench/", "scripts/", "tests/", "knowledge/", "configs/", "examples/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    write_text(
        REPORTS_DIR / "source_freeze_check.md",
        (
            "# Source Freeze Check\n\n"
            f"Date: {TODAY}\n\n"
            "`git diff -- spec2testbench/ scripts/ tests/ knowledge/ configs/ examples/` "
            f"output length: {len(result.stdout.strip())}\n"
        ),
    )
    return not result.stdout.strip()


def parse_args() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Normalize and audit the 28 AnalogCoder-Pro benchmark decks.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-cases", type=int, default=28)
    parser.add_argument("--case-id", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--report-ambiguities", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    inventory_rows, file_count, directory_count = inventory_repository()
    duplicate_file_rows = duplicate_rows(inventory_rows)
    cleanup_plan_rows, delete_paths = cleanup_candidates(inventory_rows)
    tracked = git_tracked_paths()
    deleted_manifest: list[dict[str, Any]] = []
    deletion_stats = {"files": 0, "directories": 0, "bytes": 0}
    if not args.dry_run and not args.verify_only:
        deleted_manifest, deletion_stats = execute_cleanup(delete_paths, tracked)
    write_inventory_reports(
        inventory_rows,
        duplicate_file_rows,
        cleanup_plan_rows,
        deleted_manifest,
        file_count=file_count,
        directory_count=directory_count,
        deletion_stats=deletion_stats,
    )
    circuit_rows, node_rows, source_rows, analysis_rows, metric_rows, anomaly_rows, ambiguity_rows, report_rows = normalize_benchmarks(
        args.input_root,
        args.output_root,
        case_filter=args.case_id,
        force=args.force,
        dry_run=args.dry_run,
    )
    if len(circuit_rows) != args.expected_cases and args.case_id is None:
        raise RuntimeError(f"Expected {args.expected_cases} cases, found {len(circuit_rows)}")
    write_csv(RESULTS_DIR / "analogcoder_28_analysis_metadata.csv", analysis_rows, list(analysis_rows[0].keys()) if analysis_rows else [])
    write_csv(RESULTS_DIR / "analogcoder_28_metric_compatibility.csv", metric_rows, list(metric_rows[0].keys()) if metric_rows else [])
    write_csv(
        RESULTS_DIR / "line_classification_audit.csv",
        ambiguity_rows,
        ["case_id", "line_number", "raw_line", "candidate_categories", "selected_category", "confidence", "selection_reason", "manual_review_required"],
    )
    case_count, status_counter = write_circuit_reports(report_rows)
    p02_verdict = write_p02_manual_review(report_rows)
    write_audit_summary(circuit_rows, node_rows, source_rows, anomaly_rows, status_counter, p02_verdict)
    reference_rows = ac_gain_references()
    comparison_rows, p04_trace_rows, p04_root_cause = audit_ac_gain(report_rows)
    write_ac_gain_reports(reference_rows, comparison_rows, p04_trace_rows, p04_root_cause)
    source_tree_clean = write_source_freeze_check()
    if args.report_ambiguities:
        for row in ambiguity_rows:
            print(json.dumps(row, ensure_ascii=True))
    print(json.dumps({
        "date": TODAY,
        "cases": case_count,
        "source_tree_clean": source_tree_clean,
        "cleanup_deleted_files": deletion_stats["files"],
        "cleanup_deleted_directories": deletion_stats["directories"],
    }, indent=2))


if __name__ == "__main__":
    main()
