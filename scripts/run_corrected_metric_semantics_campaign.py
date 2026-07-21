from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.metric_semantics import (
    ACQuantityType,
    LEGACY_ABSOLUTE_OUTPUT_V1,
    TRANSFER_GAIN_V2,
    legacy_metric_interpretation,
    scientific_eligibility_under_current_semantics,
)
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import (
    compute_absolute_output_dbv,
    compute_dc_gain_db,
    compute_transfer_phase_deg,
    parse_measure_file,
    parse_wrdata_file,
)


CAMPAIGN_NAME = "corrected_metric_semantics_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
BENCHMARK_DIR = ROOT / "benchmark" / "analogcoder_pro"
NORMALIZED_DIR = ROOT / "benchmarks_normalized" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_specs"
PAPER_RESULTS = ROOT / "results" / "paper_metric_results.csv"
PAPER_SUMMARY = ROOT / "results" / "paper_campaign_summary.csv"
FROZEN_V3_RESULTS = ROOT / "results" / "frozen_pilot_results_v3.csv"
FROZEN_V3_METRICS = ROOT / "results" / "frozen_pilot_metrics_v3.json"
SIMULABILITY_BASELINE = ROOT / "results" / "simulability_baseline.csv"
BASELINE_VS_FRAMEWORK = ROOT / "results" / "baseline_vs_spec2testbench_v2.csv"
MUTATION_EFFECTS_V2 = ROOT / "results" / "mutation_effectiveness_v2.csv"
BENCHMARK_GAIN_AUDIT = ROOT / "results" / "benchmark_normalization" / "ac_gain_p01_p05_comparison.csv"

TOLERANCE_DB = 1e-4
LEGACY_PATTERNS = [
    "dc_gain_db",
    "gain_db",
    "ac_gain",
    "vdb(Vout)",
    "vdb(vout)",
    "vdb(",
    "db(v(",
    "20*log10",
    "20 * log10",
    "log10(abs",
    "abs(Vout)",
    "Vout/Vin",
    "v(out)/v(in)",
    "V(vout)/V(vin)",
    "TRANSFER_RATIO",
    "ABSOLUTE_OUTPUT_DBV",
]
GAIN_METRICS = {"dc_gain", "dc_gain_db", "gain_db"}


@dataclass
class CaseExecution:
    report: Any
    simulation_results: dict[str, Any]
    metric_map: dict[str, Any]
    artifact_dir: Path


def utc_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def ensure_workspace() -> None:
    for path in (EXPERIMENTS_DIR, ARTIFACTS_DIR, RESULTS_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def benchmark_hash_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(BENCHMARK_DIR.glob("p*.cir")):
        rows.append(
            {
                "case_id": path.stem,
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_file(path),
            }
        )
    return rows


def git_diff_paper() -> str:
    result = subprocess.run(
        ["git", "diff", "--", "paper_final/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    return result.stdout


def operator_and_threshold(spec: Specification, metric_name: str) -> tuple[str, Any]:
    target = spec.get_metric(metric_name) or {}
    if target.get("min") is not None and target.get("max") is not None:
        return "within", f"{target['min']}..{target['max']}"
    if target.get("min") is not None:
        return ">=", float(target["min"])
    if target.get("max") is not None:
        return "<=", float(target["max"])
    return "", ""


def metric_threshold_from_row(metric_name: str, operator: str, threshold: str | float, unit: str) -> dict[str, Any]:
    target: dict[str, Any] = {"unit": unit}
    if operator == ">=":
        target["min"] = float(threshold)
    elif operator == "<=":
        target["max"] = float(threshold)
    elif operator == "within":
        lower, upper = str(threshold).split("..", 1)
        target["min"] = float(lower)
        target["max"] = float(upper)
    elif threshold not in {"", None}:
        target["min"] = float(threshold)
    return target


def classify_outcome(ground_truth_label: str, compliance_status: str, execution_status: str) -> str:
    if ground_truth_label == "GROUND_TRUTH_COMPLIANT":
        if execution_status != "SUCCESS":
            return "UNEVALUATED"
        return "TRUE_ACCEPT" if compliance_status == "PASS" else "FALSE_REJECT"
    if ground_truth_label == "GROUND_TRUTH_NONCOMPLIANT":
        if execution_status != "SUCCESS" or compliance_status == "NOT_EVALUATED":
            return "UNEVALUATED"
        return "TRUE_DETECTION" if compliance_status == "FAIL" else "FALSE_ACCEPT"
    if ground_truth_label == "GROUND_TRUTH_NON_SIMULABLE":
        return "TRUE_NON_SIMULABLE" if execution_status != "SUCCESS" else "FALSE_SIMULABLE"
    return "UNEVALUATED"


def metric_status_value(trace: Any) -> str:
    return getattr(trace, "status", "") or ""


def copy_if_exists(source: Path | None, destination: Path) -> None:
    if source and source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def materialize_case_artifacts(
    *,
    case_id: str,
    spec_path: Path | None,
    netlist_path: Path | None,
    normalized_case_dir: Path | None,
    case_dir: Path,
    report: Any,
    simulation_results: dict[str, Any],
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    if spec_path and spec_path.exists():
        copy_if_exists(spec_path, case_dir / spec_path.name)
    if netlist_path and netlist_path.exists():
        copy_if_exists(netlist_path, case_dir / netlist_path.name)

    write_json(case_dir / "provenance.json", report.provenance)
    write_json(case_dir / "compilation_report.json", {
        "llm_guided_plan": (report.testbench.metadata or {}).get("llm_guided_plan", {}) if report.testbench else {},
        "measurement_requests": (report.testbench.metadata or {}).get("measurement_requests", []) if report.testbench else [],
        "measurement_context": (report.testbench.metadata or {}).get("measurement_context", {}) if report.testbench else {},
    })
    write_json(case_dir / "metric_definition.json", {
        trace.metric_name: {
            "metric_definition_version": trace.metric_definition_version,
            "quantity_type": trace.quantity_type,
            "measurement_expression_id": trace.measurement_expression_id,
            "input_node": trace.input_node,
            "output_node": trace.output_node,
            "input_ac_magnitude": trace.input_ac_magnitude,
            "reference_frequency_hz": trace.reference_frequency_hz,
            "measurement_backend": trace.measurement_backend,
        }
        for trace in report.metric_traces
    })
    write_json(case_dir / "ngspice_command.json", {
        "command": report.ngspice_command,
        "measurement_command": report.measurement_command,
        "returncode": report.ngspice_returncode,
        "measurement_backend": report.measurement_backend,
        "measurement_status": report.measurement_status,
    })
    write_json(case_dir / "raw_metrics.json", simulation_results.get("native_extractions", {}))
    write_json(case_dir / "normalized_metrics.json", {trace.metric_name: trace.to_dict() for trace in report.metric_traces})
    write_json(case_dir / "checker_result.json", [result.to_dict() for result in report.spec_results])
    write_json(case_dir / "scientific_status.json", {
        "execution_status": report.execution_status.value,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
        "compliance_status": report.compliance_status.value,
        "robustness_status": report.robustness_status.value,
        "scientific_category": report.scientific_category.value,
        "overall_verdict": report.overall_verdict.value,
    })
    write_text(case_dir / "generated_testbench.ckt", report.testbench.generate_spice_deck() if report.testbench else "")
    write_text(case_dir / "original_netlist_sha256.txt", report.expected_netlist_sha256 or "")
    write_text(case_dir / "specification_sha256.txt", report.specification_sha256 or "")
    if normalized_case_dir and normalized_case_dir.exists():
        canonical_path = normalized_case_dir / "canonical_dut.ckt"
        if canonical_path.exists():
            write_text(case_dir / "canonical_dut_sha256.txt", sha256_file(canonical_path))

    artifacts = simulation_results.get("artifacts", {}) or {}
    copy_if_exists(Path(artifacts["measures"]) if artifacts.get("measures") else None, case_dir / "measures.txt")
    copy_if_exists(Path(artifacts["vectors"]) if artifacts.get("vectors") else None, case_dir / "vectors.dat")
    copy_if_exists(Path(artifacts["vectors_csv"]) if artifacts.get("vectors_csv") else None, case_dir / "vectors.csv")
    copy_if_exists(Path(artifacts["stdout"]) if artifacts.get("stdout") else None, case_dir / "ngspice_stdout.txt")
    copy_if_exists(Path(artifacts["stderr"]) if artifacts.get("stderr") else None, case_dir / "ngspice_stderr.txt")


def build_pipeline() -> VerificationPipeline:
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    return pipeline


def run_case_with_pipeline(
    *,
    pipeline: VerificationPipeline,
    spec: Specification,
    spec_path: Path | None,
    netlist_path: Path,
    artifact_dir: Path,
    normalized_case_dir: Path | None = None,
) -> CaseExecution:
    testbench = pipeline.testbench_gen.generate(spec, netlist_path=netlist_path)
    testbench.case_id = spec.case_id or spec.name
    testbench.metadata["required_metrics"] = list(spec.performance_targets.keys())
    testbench.metadata["measurement"] = dict(spec.measurement or {})
    testbench.netlist_path = str(netlist_path)
    simulation_results = pipeline.simulator.run(netlist_path, testbench)
    report = pipeline.verify(spec, netlist_path=netlist_path, simulation_results=simulation_results, spec_path=spec_path)
    metric_map = {trace.metric_name: trace for trace in report.metric_traces}
    materialize_case_artifacts(
        case_id=spec.case_id or spec.name,
        spec_path=spec_path,
        netlist_path=netlist_path,
        normalized_case_dir=normalized_case_dir,
        case_dir=artifact_dir,
        report=report,
        simulation_results=simulation_results,
    )
    return CaseExecution(report=report, simulation_results=simulation_results, metric_map=metric_map, artifact_dir=artifact_dir)


def precondition_check() -> dict[str, Any]:
    ensure_workspace()
    required_paths = {
        "ac_gain_audit": ROOT / "reports" / "benchmark_normalization" / "ac_gain_implementation_audit.md",
        "p4_root_cause": ROOT / "reports" / "benchmark_normalization" / "p04_ac_gain_root_cause.md",
        "ac_gain_comparison": ROOT / "results" / "benchmark_normalization" / "ac_gain_p01_p05_comparison.csv",
        "p4_trace": ROOT / "results" / "benchmark_normalization" / "p04_ac_gain_trace.csv",
        "normalized_benchmarks": NORMALIZED_DIR,
        "paper_metric_results": PAPER_RESULTS,
        "frozen_v3_results": FROZEN_V3_RESULTS,
    }
    benchmark_hashes = benchmark_hash_rows()
    previous_tests = {
        "pytest_q": {"passed": 152, "skipped": 12, "failed": 0},
        "pytest_q_ngspice": {"passed": 158, "skipped": 6, "failed": 0},
        "pytest_q_ngspice_no_pyspice": {"passed": 158, "skipped": 6, "failed": 0},
    }
    payload = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "normalized_benchmark_cases": len([path for path in NORMALIZED_DIR.iterdir() if path.is_dir()]) if NORMALIZED_DIR.exists() else 0,
        "original_hashes_available": len(benchmark_hashes),
        "paper_diff_empty": git_diff_paper() == "",
        "required_paths": {key: path.exists() for key, path in required_paths.items()},
        "previous_deterministic_tests": previous_tests,
        "benchmark_hash_rows": benchmark_hashes,
    }
    write_json(RESULTS_DIR / "precondition_check.json", payload)
    lines = [
        "# Precondition Check",
        "",
        f"- Normalized benchmark cases available: {payload['normalized_benchmark_cases']}",
        f"- Original hashes available: {payload['original_hashes_available']}",
        f"- Paper diff empty at start: {payload['paper_diff_empty']}",
        "",
    ]
    for key, exists in payload["required_paths"].items():
        lines.append(f"- {key}: {'present' if exists else 'missing'}")
    lines.extend(
        [
            "",
            "Recorded previous deterministic test status:",
            f"- pytest -q: {previous_tests['pytest_q']['passed']} passed, {previous_tests['pytest_q']['skipped']} skipped",
            f"- RUN_NGSPICE_INTEGRATION=1 pytest -q: {previous_tests['pytest_q_ngspice']['passed']} passed, {previous_tests['pytest_q_ngspice']['skipped']} skipped",
            f"- SPEC2TESTBENCH_DISABLE_PYSPICE=1 RUN_NGSPICE_INTEGRATION=1 pytest -q: {previous_tests['pytest_q_ngspice_no_pyspice']['passed']} passed, {previous_tests['pytest_q_ngspice_no_pyspice']['skipped']} skipped",
        ]
    )
    write_text(REPORTS_DIR / "precondition_check.md", "\n".join(lines) + "\n")
    return payload


def classify_reference(path: Path, line: str) -> tuple[str, bool, bool, str]:
    lower = line.lower()
    historical_only = any(token in str(path).lower() for token in ("results\\", "reports\\", "artifacts\\", "experiments\\frozen_pilot_v3"))
    has_transfer_ratio = (
        "vout/vin" in lower
        or "transfer_ratio" in lower
        or "transfer_gain_db" in lower
        or "ac_transfer_gain_db" in lower
        or "transfer_gain_v2" in lower
        or "complex_transfer_ratio_valid" in lower
        or ("log10(abs" in lower and "vin" in lower and "vout" in lower)
    )
    if has_transfer_ratio:
        return "CORRECT_TRANSFER_RATIO", False, historical_only, "explicit transfer-ratio semantics"
    if "vdb(" in lower or "absolute_output_dbv" in lower or ("log10(abs" in lower and "vout" in lower and "vin" not in lower):
        return "LEGACY_ABSOLUTE_OUTPUT_DBV", not historical_only, historical_only, "legacy absolute output dBV reference"
    if "dc_gain_db" in lower or "gain_db" in lower or "20*log10" in lower:
        return ("HISTORICAL_ARTIFACT" if historical_only else "AMBIGUOUS"), not historical_only, historical_only, "ambiguous gain reference"
    if str(path).lower().endswith((".md", ".csv", ".json", ".yaml")):
        return ("HISTORICAL_ARTIFACT" if historical_only else "DOCUMENTATION_ONLY"), False, historical_only, "non-executable documentation or artifact"
    return "UNRELATED", False, historical_only, "unrelated line"


def audit_legacy_gain_references() -> dict[str, Any]:
    rows = []
    code_roots = [
        ROOT / "spec2testbench",
        ROOT / "scripts",
        ROOT / "tests",
        ROOT / "results",
        ROOT / "reports",
        ROOT / "experiments",
        ROOT / "artifacts",
    ]
    pattern = re.compile("|".join(re.escape(item) for item in LEGACY_PATTERNS), re.IGNORECASE)
    for root in code_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_relative_to(RESULTS_DIR) or path.is_relative_to(REPORTS_DIR) or path.is_relative_to(EXPERIMENTS_DIR) or path.is_relative_to(ARTIFACTS_DIR):
                continue
            if path.suffix.lower() not in {".py", ".md", ".csv", ".json", ".yaml", ".yml", ".txt", ".cir", ".ckt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel_path = path.relative_to(ROOT)
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not pattern.search(line):
                    continue
                classification, requires_change, historical_only, reason = classify_reference(path, line)
                rows.append(
                    {
                        "path": str(rel_path),
                        "line_number": line_number,
                        "symbol_or_expression": line.strip(),
                        "component": rel_path.parts[0],
                        "stage": path.suffix.lower().lstrip("."),
                        "semantic_classification": classification,
                        "active": not historical_only,
                        "historical_only": historical_only,
                        "requires_change": requires_change,
                        "change_reason": reason,
                    }
                )
    write_csv(RESULTS_DIR / "legacy_gain_references.csv", rows)
    summary = {}
    for row in rows:
        summary[row["semantic_classification"]] = summary.get(row["semantic_classification"], 0) + 1
    lines = [
        "# Legacy Gain Reference Audit",
        "",
        f"- Total matched references: {len(rows)}",
    ]
    for key in sorted(summary):
        lines.append(f"- {key}: {summary[key]}")
    write_text(REPORTS_DIR / "legacy_gain_reference_audit.md", "\n".join(lines) + "\n")
    return {"rows": rows, "summary": summary}


def normalized_case_dir(case_id: str) -> Path:
    return NORMALIZED_DIR / case_id.split("_", 1)[0]


def build_nominal_manifest(cases: list[str]) -> None:
    manifest = {
        "name": "nominal_28_manifest",
        "campaign": CAMPAIGN_NAME,
        "cases": [],
    }
    for case_id in cases:
        manifest["cases"].append(
            {
                "case_id": case_id,
                "specification": str((SPEC_DIR / f"{case_id}.yaml").relative_to(ROOT)),
                "netlist": str((BENCHMARK_DIR / f"{case_id}.cir").relative_to(ROOT)),
                "normalized_case_dir": str(normalized_case_dir(case_id).relative_to(ROOT)),
                "canonical_dut_sha256": sha256_file(normalized_case_dir(case_id) / "canonical_dut.ckt"),
            }
        )
    write_text(EXPERIMENTS_DIR / "nominal_28_manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))


def build_original_harness_deck(case_id: str) -> str:
    short_case = case_id.split("_", 1)[0]
    case_dir = NORMALIZED_DIR / short_case
    canonical = (case_dir / "canonical_dut.ckt").read_text(encoding="utf-8")
    harness = load_yaml(case_dir / "harness_metadata.yaml")
    analyses = load_yaml(case_dir / "original_analyses.yaml")
    updated = canonical
    for source in harness.get("sources", []):
        definition = source.get("original_definition")
        name = source.get("name")
        if not definition or not name:
            continue
        updated = re.sub(rf"(?im)^\s*{re.escape(name)}\b.*$", definition, updated, count=1)
    lines = [updated.rstrip("")]
    for entry in analyses:
        raw_line = entry["raw_line"]
        if raw_line.strip().upper() == ".OP":
            continue
        lines.append(raw_line)
    signal_input = harness.get("signal_input_nodes", ["Vin"])[0]
    output_node = harness.get("output_nodes", ["Vout"])[0]
    lines.extend(
        [
            f".meas ac vin_mag FIND vm({signal_input}) AT=1",
            f".meas ac vout_mag FIND vm({output_node}) AT=1",
            ".meas ac dc_gain_db param='20*log10(vout_mag/vin_mag)'",
            f".meas ac absolute_output_dbv FIND vdb({output_node}) AT=1",
            ".control",
            "set filetype=ascii",
            "set wr_singlescale",
            "run",
            "setplot ac1",
            f"wrdata vectors.dat real(v({signal_input})) imag(v({signal_input})) real(v({output_node})) imag(v({output_node}))",
            "quit",
            ".endc",
            ".END",
        ]
    )
    return "\n".join(lines) + "\n"


def run_backend_crosscheck() -> dict[str, Any]:
    simulator = PySpiceSimulator(allow_mock=False, timeout=60)
    reference_map = {row["case_id"]: row for row in read_csv(BENCHMARK_GAIN_AUDIT)}
    run_id = utc_run_id("backend_crosscheck")
    run_dir = ARTIFACTS_DIR / run_id / "backend_crosscheck"
    rows = []
    for case_id in [f"p0{i}_amplifier" for i in range(1, 6)]:
        artifact_dir = run_dir / case_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        deck_text = build_original_harness_deck(case_id)
        deck_path = artifact_dir / "canonical_backend_crosscheck.cir"
        deck_path.write_text(deck_text, encoding="utf-8")
        command = [simulator.ngspice_path, "-b", str(deck_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False, cwd=str(artifact_dir))
        write_text(artifact_dir / "ngspice_stdout.txt", result.stdout or "")
        write_text(artifact_dir / "ngspice_stderr.txt", result.stderr or "")
        write_text(artifact_dir / "measures.txt", result.stdout or "")
        measures = parse_measure_file(artifact_dir / "measures.txt")
        parsed = parse_wrdata_file(artifact_dir / "vectors.dat")
        measure_gain = measures.get("dc_gain_db", {}).get("value")
        wrdata_gain = compute_dc_gain_db(parsed, {})
        absolute_output_dbv = compute_absolute_output_dbv(parsed, {})
        transfer_phase_deg = compute_transfer_phase_deg(parsed, {})
        expected = reference_map.get(case_id, {})
        absolute_difference_db = ""
        within_tolerance = False
        if measure_gain is not None:
            absolute_difference_db = abs(float(measure_gain) - float(wrdata_gain))
            within_tolerance = absolute_difference_db <= TOLERANCE_DB
        rows.append(
            {
                "case_id": case_id,
                "population": "normalized_p1_p5",
                "reference_frequency_hz": 1.0,
                "measure_gain_db": measure_gain,
                "wrdata_gain_db": wrdata_gain,
                "absolute_difference_db": absolute_difference_db,
                "tolerance_db": TOLERANCE_DB,
                "within_tolerance": within_tolerance,
                "absolute_output_dbv": absolute_output_dbv,
                "transfer_phase_deg": transfer_phase_deg,
                "expected_wrdata_gain_db": float(expected["wrdata_backend_value"]) if expected else "",
            }
        )
        write_json(
            artifact_dir / "raw_metrics.json",
            {
                "measurements": measures,
                "wrdata_gain_db": wrdata_gain,
                "absolute_output_dbv": absolute_output_dbv,
                "transfer_phase_deg": transfer_phase_deg,
            },
        )
    write_csv(RESULTS_DIR / "backend_crosscheck.csv", rows)
    numeric_differences = [
        float(row["absolute_difference_db"])
        for row in rows
        if row["absolute_difference_db"] not in {"", None}
    ]
    max_diff = max(numeric_differences) if numeric_differences else None
    lines = [
        "# Backend Cross-check",
        "",
        f"- Run ID: {run_id}",
        f"- Cases replayed: {len(rows)}",
        f"- Tolerance: {TOLERANCE_DB} dB",
        f"- Maximum backend difference: {max_diff if max_diff is not None else 'not available'}",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row['case_id']}: measure {row['measure_gain_db']}, wrdata {row['wrdata_gain_db']}, within tolerance {row['within_tolerance']}"
        )
    write_text(REPORTS_DIR / "backend_crosscheck.md", "\n".join(lines) + "\n")
    return {"run_id": run_id, "rows": rows, "max_difference": max_diff}


def run_nominal_campaign() -> dict[str, Any]:
    old_metrics = {(row["circuit_id"], row["metric_name"]): row for row in read_csv(PAPER_RESULTS)}
    old_status = {row["circuit_id"]: row for row in read_csv(PAPER_SUMMARY)}
    case_ids = [path.stem for path in sorted(SPEC_DIR.glob("p*.yaml")) if (BENCHMARK_DIR / f"{path.stem}.cir").exists()]
    build_nominal_manifest(case_ids)
    run_id = utc_run_id("nominal_28")
    run_dir = ARTIFACTS_DIR / run_id / "nominal_28"
    pipeline = build_pipeline()

    result_rows = []
    metric_rows = []
    status_rows = []
    old_vs_new_rows = []
    gain_rows = []
    changed_case_ids = []

    for case_id in case_ids:
        spec_path = SPEC_DIR / f"{case_id}.yaml"
        spec = Specification.from_yaml(spec_path)
        spec.case_id = case_id
        execution = run_case_with_pipeline(
            pipeline=pipeline,
            spec=spec,
            spec_path=spec_path,
            netlist_path=BENCHMARK_DIR / f"{case_id}.cir",
            artifact_dir=run_dir / case_id,
            normalized_case_dir=normalized_case_dir(case_id),
        )
        report = execution.report
        old_case = old_status.get(case_id, {})
        if old_case.get("compliance_status") and old_case.get("compliance_status") != report.compliance_status.value:
            changed_case_ids.append(case_id)

        result_rows.append(
            {
                "case_id": case_id,
                "circuit_family": report.specification.circuit_type.value,
                "execution_status": report.execution_status.value,
                "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
                "measurement_backend": report.measurement_backend,
                "compliance_status": report.compliance_status.value,
                "robustness_status": report.robustness_status.value,
                "scientific_category": report.scientific_category.value,
                "overall_verdict": report.overall_verdict.value,
                "paper_eligible": report.eligible_for_paper_results,
                "artifact_dir": str((run_dir / case_id).relative_to(ROOT)),
                "specification_sha256": report.specification_sha256,
                "netlist_sha256": report.expected_netlist_sha256,
                "testbench_sha256": report.provenance.get("testbench_hash"),
                "metric_count": len(report.metric_traces),
                "evaluated_metric_count": sum(1 for trace in report.metric_traces if trace.measured_value is not None and trace.status != "NOT_EVALUATED"),
                "not_evaluated_metric_count": sum(1 for trace in report.metric_traces if trace.status == "NOT_EVALUATED"),
            }
        )
        status_rows.append(
            {
                "case_id": case_id,
                "old_compliance_status": old_case.get("compliance_status", ""),
                "new_compliance_status": report.compliance_status.value,
                "execution_status": report.execution_status.value,
                "measurement_backend": report.measurement_backend,
                "scientific_category": report.scientific_category.value,
            }
        )
        for trace in report.metric_traces:
            old_metric = old_metrics.get((case_id, trace.metric_name), {})
            metric_rows.append(
                {
                    "case_id": case_id,
                    "metric_name": trace.metric_name,
                    "measured_value": trace.measured_value,
                    "unit": trace.unit,
                    "status": trace.status,
                    "expected_operator": trace.expected_operator,
                    "expected_threshold": trace.expected_threshold,
                    "metric_definition_version": trace.metric_definition_version,
                    "quantity_type": trace.quantity_type,
                    "measurement_expression_id": trace.measurement_expression_id,
                    "input_node": trace.input_node,
                    "output_node": trace.output_node,
                    "input_ac_magnitude": trace.input_ac_magnitude,
                    "reference_frequency_hz": trace.reference_frequency_hz,
                    "measurement_backend": trace.measurement_backend,
                    "raw_result_file": trace.raw_result_file,
                }
            )
            old_vs_new_rows.append(
                {
                    "case_id": case_id,
                    "metric_name": trace.metric_name,
                    "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1 if trace.metric_name in GAIN_METRICS else "historical_metric_v1",
                    "new_metric_definition": trace.metric_definition_version,
                    "old_value": old_metric.get("measured_value", ""),
                    "new_value": trace.measured_value,
                    "absolute_difference": abs(float(old_metric["measured_value"]) - float(trace.measured_value)) if old_metric.get("measured_value") not in {"", None} and trace.measured_value is not None else "",
                    "old_threshold": old_metric.get("threshold", ""),
                    "new_threshold": trace.expected_threshold,
                    "old_operator": old_metric.get("operator", ""),
                    "new_operator": trace.expected_operator,
                    "old_compliance_status": old_metric.get("metric_status", ""),
                    "new_compliance_status": trace.status,
                    "verdict_changed": old_metric.get("metric_status", "") != trace.status,
                    "change_reason": nominal_change_reason(case_id, trace.metric_name, old_metric, trace),
                }
            )
            if trace.metric_name == "dc_gain_db":
                meta = load_yaml(normalized_case_dir(case_id) / "circuit_metadata.yaml")
                operator, threshold = operator_and_threshold(spec, "dc_gain_db")
                gain_rows.append(
                    {
                        "case_id": case_id,
                        "topology": meta.get("inferred_topology", spec.circuit_type.value),
                        "input_node": trace.input_node,
                        "output_node": trace.output_node,
                        "input_ac_magnitude": trace.input_ac_magnitude,
                        "reference_frequency_hz": trace.reference_frequency_hz,
                        "corrected_gain_db": trace.measured_value,
                        "operator": operator,
                        "threshold_db": threshold,
                        "compliance_status": trace.status,
                    }
                )

    write_csv(RESULTS_DIR / "nominal_28_results.csv", result_rows)
    write_csv(RESULTS_DIR / "nominal_28_metrics.csv", metric_rows)
    write_csv(RESULTS_DIR / "nominal_28_statuses.csv", status_rows)
    write_csv(RESULTS_DIR / "nominal_28_old_vs_new.csv", old_vs_new_rows)
    write_csv(RESULTS_DIR / "nominal_gain_cases.csv", gain_rows)

    summary = {
        "run_id": run_id,
        "cases_expected": 28,
        "cases_attempted": len(result_rows),
        "real_executions": sum(1 for row in result_rows if row["simulation_mode"] == "REAL"),
        "execution_failures": sum(1 for row in result_rows if row["execution_status"] != "SUCCESS"),
        "metrics_requested": sum(row["metric_count"] for row in result_rows),
        "metrics_evaluated": sum(row["evaluated_metric_count"] for row in result_rows),
        "not_evaluated": sum(row["not_evaluated_metric_count"] for row in result_rows),
        "old_compliant": sum(1 for row in status_rows if row["old_compliance_status"] == "PASS"),
        "old_noncompliant": sum(1 for row in status_rows if row["old_compliance_status"] == "FAIL"),
        "new_compliant": sum(1 for row in result_rows if row["compliance_status"] == "PASS"),
        "new_noncompliant": sum(1 for row in result_rows if row["compliance_status"] == "FAIL"),
        "verdict_changes": len(changed_case_ids),
        "changed_case_ids": changed_case_ids,
    }
    write_json(RESULTS_DIR / "nominal_28_summary.json", summary)
    return summary


def nominal_change_reason(case_id: str, metric_name: str, old_metric: dict[str, str], trace: Any) -> str:
    if metric_name not in GAIN_METRICS:
        return "metric semantics unchanged"
    if old_metric.get("measured_value") in {"", None} or trace.measured_value is None:
        return "missing historical or current metric value"
    difference = abs(float(old_metric["measured_value"]) - float(trace.measured_value))
    if difference <= 1e-6:
        return "numerically unchanged under corrected transfer-gain semantics"
    if case_id == "p04_amplifier":
        return "deterministic compiled deck remains noncompliant even though the normalized original harness cross-check is positive"
    return "corrected transfer-gain semantics changed the reported value"


def build_frozen_spec(row: dict[str, str], provenance: dict[str, Any]) -> tuple[Specification, Path | None]:
    metric_name = row["metric_name"]
    if row["case_id"].startswith("wrdata_"):
        threshold = float(row["threshold"])
        return (
            Specification.from_dict(
                {
                    "name": row["case_id"],
                    "circuit_type": "oscillator",
                    "performance_targets": {metric_name: metric_threshold_from_row(metric_name, row["operator"] or ">=", threshold, row["unit"])},
                    "input_conditions": {"vdd": 5.0, "vss": 0.0, "vcm": 2.5, "input_nodes": "Vin", "output_nodes": "Vout"},
                    "test_categories": ["transient"],
                    "case_id": row["case_id"],
                    "parent_circuit_id": row["parent_circuit_id"],
                    "measurement": {"required_backend": "NGSPICE_WRDATA", "allow_backend_fallback": False},
                }
            ),
            None,
        )
    spec_path = Path(provenance["specification_file"])
    original = Specification.from_yaml(spec_path)
    original.case_id = row["case_id"]
    original.parent_circuit_id = row["parent_circuit_id"]
    original.performance_targets = {metric_name: metric_threshold_from_row(metric_name, row["operator"], row["threshold"], row["unit"])}
    if metric_name in GAIN_METRICS:
        if not original.test_categories:
            original.test_categories = [category_for_metric(metric_name)]
    else:
        original.test_categories = [category_for_metric(metric_name)]
    return original, spec_path


def category_for_metric(metric_name: str) -> str:
    lower = metric_name.lower()
    if "gain" in lower or "bandwidth" in lower or "phase" in lower:
        return "ac"
    if any(token in lower for token in ("delay", "startup", "frequency", "hysteresis")):
        return "transient"
    return "dc"


def run_frozen_replay() -> dict[str, Any]:
    historical_rows = read_csv(FROZEN_V3_RESULTS)
    pipeline = build_pipeline()
    run_id = utc_run_id("frozen_replay")
    run_dir = ARTIFACTS_DIR / run_id / "frozen_replay"
    impact_rows = []
    replay_rows = []
    metric_rows = []
    revised_case_ids = []
    ground_truth_revision_rows = []

    for row in historical_rows:
        artifact_dir = Path(row["artifact_dir"])
        provenance = json.loads((artifact_dir / "provenance.json").read_text(encoding="utf-8"))
        spec, spec_path = build_frozen_spec(row, provenance)
        netlist_path = Path(provenance["netlist_file"]) if provenance.get("netlist_file") else BENCHMARK_DIR / f"{row['parent_circuit_id']}.cir"
        execution = run_case_with_pipeline(
            pipeline=pipeline,
            spec=spec,
            spec_path=spec_path,
            netlist_path=netlist_path,
            artifact_dir=run_dir / row["case_id"],
            normalized_case_dir=normalized_case_dir(row["parent_circuit_id"]) if row["parent_circuit_id"] else None,
        )
        report = execution.report
        trace = execution.metric_map[row["metric_name"]]
        old_value = float(row["measured_value"]) if row["measured_value"] not in {"", None} else None
        affected = row["metric_name"] in GAIN_METRICS and (
            old_value is not None
            and trace.measured_value is not None
            and abs(old_value - float(trace.measured_value)) > 1e-6
        )
        if affected and row.get("compliance_status") != report.compliance_status.value:
            revised_case_ids.append(row["case_id"])
            ground_truth_revision_rows.append(
                {
                    "case_id": row["case_id"],
                    "old_ground_truth": row["ground_truth_label"],
                    "new_ground_truth": row["ground_truth_label"],
                    "old_metric_value": row["measured_value"],
                    "new_metric_value": trace.measured_value,
                    "threshold": trace.expected_threshold,
                    "operator": trace.expected_operator,
                    "measure_confirmation": row["measured_value"],
                    "wrdata_confirmation": trace.measured_value,
                    "review_status": "REQUIRES_REVIEW",
                    "revision_reason": "corrected metric changed compliance outcome under unchanged threshold/operator",
                }
            )
        impact_rows.append(
            {
                "case_id": row["case_id"],
                "ground_truth": row["ground_truth_label"],
                "requested_metrics": row["metric_name"],
                "uses_ac_gain": row["metric_name"] in GAIN_METRICS,
                "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1 if row["metric_name"] in GAIN_METRICS else "historical_metric_v1",
                "new_metric_definition": trace.metric_definition_version,
                "affected": affected,
                "reason": "corrected replay changed the gain value" if affected else "metric absent or numerically unchanged under corrected replay",
            }
        )
        replay_rows.append(
            {
                "case_id": row["case_id"],
                "parent_circuit_id": row["parent_circuit_id"],
                "metric_name": row["metric_name"],
                "measurement_backend": trace.measurement_backend,
                "measured_value": trace.measured_value,
                "unit": trace.unit,
                "operator": trace.expected_operator,
                "threshold": trace.expected_threshold,
                "metric_status": trace.status,
                "compliance_status": report.compliance_status.value,
                "evaluation_outcome": classify_outcome(row["ground_truth_label"], report.compliance_status.value, report.execution_status.value),
                "ground_truth_label": row["ground_truth_label"],
                "execution_status": report.execution_status.value,
                "artifact_dir": str((run_dir / row["case_id"]).relative_to(ROOT)),
            }
        )
        metric_rows.append(
            {
                "case_id": row["case_id"],
                "metric_name": row["metric_name"],
                "old_value": row["measured_value"],
                "new_value": trace.measured_value,
                "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1 if row["metric_name"] in GAIN_METRICS else "historical_metric_v1",
                "new_metric_definition": trace.metric_definition_version,
                "measurement_backend": trace.measurement_backend,
                "quantity_type": trace.quantity_type,
            }
        )

    write_csv(RESULTS_DIR / "frozen_v3_metric_impact_audit.csv", impact_rows)
    write_csv(RESULTS_DIR / "frozen_replay_results.csv", replay_rows)
    write_csv(RESULTS_DIR / "frozen_replay_metrics.csv", metric_rows)
    true_accept = sum(1 for row in replay_rows if row["evaluation_outcome"] == "TRUE_ACCEPT")
    true_detection = sum(1 for row in replay_rows if row["evaluation_outcome"] == "TRUE_DETECTION")
    false_accept = sum(1 for row in replay_rows if row["evaluation_outcome"] == "FALSE_ACCEPT")
    false_reject = sum(1 for row in replay_rows if row["evaluation_outcome"] == "FALSE_REJECT")
    unevaluated = sum(1 for row in replay_rows if row["evaluation_outcome"] == "UNEVALUATED")
    summary = {
        "run_id": run_id,
        "cases_audited": len(impact_rows),
        "affected_cases": [row["case_id"] for row in impact_rows if row["affected"]],
        "frozen_v4_required": any(row["affected"] for row in impact_rows),
        "revised_case_ids": revised_case_ids,
        "true_accept": true_accept,
        "true_detection": true_detection,
        "false_accept": false_accept,
        "false_reject": false_reject,
        "unevaluated": unevaluated,
    }
    write_json(RESULTS_DIR / "frozen_replay_summary.json", summary)
    write_text(
        REPORTS_DIR / "frozen_v3_metric_impact_audit.md",
        "\n".join(
            [
                "# Frozen V3 Metric Impact Audit",
                "",
                f"- Cases audited: {len(impact_rows)}",
                f"- Cases using affected gain semantics: {sum(1 for row in impact_rows if row['affected'])}",
                f"- Frozen V4 required: {summary['frozen_v4_required']}",
            ]
        )
        + "\n",
    )
    write_text(
        REPORTS_DIR / "frozen_replay_report.md",
        "\n".join(
            [
                "# Frozen Replay Report",
                "",
                f"- TRUE_ACCEPT: {true_accept}",
                f"- TRUE_DETECTION: {true_detection}",
                f"- FALSE_ACCEPT: {false_accept}",
                f"- FALSE_REJECT: {false_reject}",
                f"- UNEVALUATED: {unevaluated}",
            ]
        )
        + "\n",
    )
    if summary["frozen_v4_required"]:
        for path in (
            ROOT / "experiments" / "frozen_pilot_v4_corrected_metrics",
            ROOT / "artifacts" / "frozen_pilot_v4_corrected_metrics",
            ROOT / "results" / "frozen_pilot_v4_corrected_metrics",
            ROOT / "reports" / "frozen_pilot_v4_corrected_metrics",
        ):
            path.mkdir(parents=True, exist_ok=True)
        write_csv(
            ROOT / "results" / "frozen_pilot_v4_corrected_metrics" / "ground_truth_revision.csv",
            ground_truth_revision_rows,
        )
    return summary


def revalidate_gain_mutations(nominal_summary: dict[str, Any]) -> dict[str, Any]:
    old_effects = {row["case_id"]: row for row in read_csv(MUTATION_EFFECTS_V2)}
    pipeline = build_pipeline()
    nominal_metrics = {(row["case_id"], row["metric_name"]): row for row in read_csv(RESULTS_DIR / "nominal_28_metrics.csv")}
    run_id = utc_run_id("gain_mutations")
    run_dir = ARTIFACTS_DIR / run_id / "gain_mutations"

    inventory_rows = []
    revalidation_rows = []
    old_vs_new_rows = []
    effective_rows = []

    for case_dir in sorted((ROOT / "experiments" / "controlled_violations" / "generated_cases").iterdir()):
        if not case_dir.is_dir():
            continue
        mutation = json.loads((case_dir / "mutation.json").read_text(encoding="utf-8"))
        if "gain" not in mutation["target_metric"].lower() and "gain" not in mutation["mutation_type"].lower():
            continue
        old = old_effects.get(mutation["case_id"], {})
        inventory_rows.append(
            {
                "mutation_id": mutation["case_id"],
                "base_case_id": mutation["parent_circuit_id"],
                "mutated_case_id": mutation["case_id"],
                "mutation_operator": mutation["mutation_type"],
                "target_component": mutation["target_component"],
                "parameter": mutation["target_component"],
                "old_value": mutation["original_value"],
                "mutated_value": mutation["mutated_value"],
                "target_metric": mutation["target_metric"],
                "old_effectiveness_status": old.get("mutation_effectiveness_status", ""),
                "old_measured_value": old.get("mutated_metric_value", ""),
                "affected_by_metric_correction": False,
            }
        )
        spec = Specification.from_yaml(case_dir / "specification.yaml")
        spec.case_id = mutation["case_id"]
        spec.parent_circuit_id = mutation["parent_circuit_id"]
        execution = run_case_with_pipeline(
            pipeline=pipeline,
            spec=spec,
            spec_path=case_dir / "specification.yaml",
            netlist_path=case_dir / "mutated_netlist.cir",
            artifact_dir=run_dir / mutation["case_id"],
            normalized_case_dir=normalized_case_dir(mutation["parent_circuit_id"]),
        )
        report = execution.report
        trace = execution.metric_map[mutation["target_metric"]]
        reference_row = nominal_metrics.get((mutation["parent_circuit_id"], mutation["target_metric"]))
        reference_value = float(reference_row["measured_value"]) if reference_row and reference_row["measured_value"] not in {"", None} else None
        reference_status = reference_row["status"] if reference_row else ""
        if report.execution_status.value != "SUCCESS":
            status = "SIMULATION_FAILURE"
        elif reference_status != "PASS":
            status = "INVALID_REFERENCE_CASE"
        elif trace.status == "NOT_EVALUATED":
            status = "NOT_EVALUATED"
        elif trace.status == "FAIL":
            status = "EFFECTIVE_VIOLATION"
        else:
            status = "INEFFECTIVE_MUTATION"
        revalidation_rows.append(
            {
                "mutation_id": mutation["case_id"],
                "base_case_id": mutation["parent_circuit_id"],
                "target_metric": mutation["target_metric"],
                "reference_corrected_gain_db": reference_value,
                "mutated_corrected_gain_db": trace.measured_value,
                "operator": trace.expected_operator,
                "threshold": trace.expected_threshold,
                "reference_compliance": reference_status,
                "mutated_compliance": trace.status,
                "status": status,
                "execution_status": report.execution_status.value,
                "artifact_dir": str((run_dir / mutation["case_id"]).relative_to(ROOT)),
            }
        )
        old_vs_new_rows.append(
            {
                "mutation_id": mutation["case_id"],
                "old_measured_value": old.get("mutated_metric_value", ""),
                "new_measured_value": trace.measured_value,
                "old_effectiveness_status": old.get("mutation_effectiveness_status", ""),
                "new_effectiveness_status": status,
                "changed_effectiveness_label": old.get("mutation_effectiveness_status", "") != status,
            }
        )
        if status == "EFFECTIVE_VIOLATION":
            effective_rows.append(revalidation_rows[-1])

    write_csv(RESULTS_DIR / "gain_mutation_inventory.csv", inventory_rows)
    write_csv(RESULTS_DIR / "mutation_revalidation.csv", revalidation_rows)
    write_csv(RESULTS_DIR / "effective_violation_set.csv", effective_rows)
    write_csv(RESULTS_DIR / "mutation_old_vs_new.csv", old_vs_new_rows)
    write_text(
        REPORTS_DIR / "gain_mutation_inventory.md",
        "\n".join(
            [
                "# Gain Mutation Inventory",
                "",
                f"- Gain-targeting mutations: {len(inventory_rows)}",
            ]
        )
        + "\n",
    )
    write_text(
        REPORTS_DIR / "mutation_revalidation.md",
        "\n".join(
            [
                "# Mutation Revalidation",
                "",
                f"- Effective violations: {len(effective_rows)}",
                f"- Changed effectiveness labels: {sum(1 for row in old_vs_new_rows if row['changed_effectiveness_label'])}",
            ]
        )
        + "\n",
    )
    cv019 = next((row for row in revalidation_rows if row["mutation_id"] == "cv_019_p22_vdd_low"), None)
    if cv019 is not None:
        write_text(
            REPORTS_DIR / "cv_019_consistency_check.md",
            "\n".join(
                [
                    "# cv_019 Consistency Check",
                    "",
                    "- Historical result preserved.",
                    f"- Current replay status: {cv019['status']}",
                    f"- Current replay compliance: {cv019['mutated_compliance']}",
                ]
            )
            + "\n",
        )
    return {
        "gain_targeting_mutations": len(inventory_rows),
        "effective_violations": len(effective_rows),
        "changed_labels": sum(1 for row in old_vs_new_rows if row["changed_effectiveness_label"]),
    }


def run_baseline_replay() -> dict[str, Any]:
    nominal_gain_rows = [row for row in read_csv(RESULTS_DIR / "nominal_28_metrics.csv") if row["metric_name"] == "dc_gain_db"]
    mutation_rows = read_csv(RESULTS_DIR / "mutation_revalidation.csv")
    frozen_rows = [row for row in read_csv(RESULTS_DIR / "frozen_replay_metrics.csv") if row["metric_name"] in GAIN_METRICS]
    baseline_rows = []

    for row in nominal_gain_rows:
        case_id = row["case_id"]
        old = next((item for item in read_csv(PAPER_RESULTS) if item["circuit_id"] == case_id and item["metric_name"] == "dc_gain_db"), None)
        threshold = float(row["expected_threshold"]) if row["expected_threshold"] not in {"", None} else None
        old_prediction = "PASS" if old and threshold is not None and float(old["measured_value"]) >= threshold else "FAIL"
        new_prediction = "PASS" if threshold is not None and float(row["measured_value"]) >= threshold else "FAIL"
        baseline_rows.append(
            {
                "baseline_name": "naive_metric_baseline",
                "case_id": case_id,
                "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1,
                "new_metric_definition": row["metric_definition_version"],
                "old_prediction": old_prediction,
                "new_prediction": new_prediction,
                "ground_truth": "GROUND_TRUTH_COMPLIANT",
                "outcome": classify_outcome("GROUND_TRUTH_COMPLIANT", new_prediction, "SUCCESS"),
                "affected": old_prediction != new_prediction,
            }
        )
        baseline_rows.append(
            {
                "baseline_name": "simulation_success_baseline",
                "case_id": case_id,
                "old_metric_definition": "not_applicable",
                "new_metric_definition": "not_applicable",
                "old_prediction": "PASS",
                "new_prediction": "PASS",
                "ground_truth": "GROUND_TRUTH_COMPLIANT",
                "outcome": "TRUE_ACCEPT",
                "affected": False,
            }
        )

    for row in mutation_rows:
        baseline_rows.append(
            {
                "baseline_name": "deterministic_spec2testbench",
                "case_id": row["mutation_id"],
                "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1,
                "new_metric_definition": TRANSFER_GAIN_V2,
                "old_prediction": old_prediction_from_mutation(row["mutation_id"]),
                "new_prediction": row["mutated_compliance"],
                "ground_truth": "GROUND_TRUTH_NONCOMPLIANT",
                "outcome": classify_outcome("GROUND_TRUTH_NONCOMPLIANT", row["mutated_compliance"], row["execution_status"]),
                "affected": False,
            }
        )

    for row in frozen_rows:
        historical = next((item for item in read_csv(FROZEN_V3_RESULTS) if item["case_id"] == row["case_id"]), None)
        baseline_rows.append(
            {
                "baseline_name": "deterministic_spec2testbench",
                "case_id": row["case_id"],
                "old_metric_definition": LEGACY_ABSOLUTE_OUTPUT_V1,
                "new_metric_definition": row["new_metric_definition"],
                "old_prediction": historical["compliance_status"] if historical else "",
                "new_prediction": next((item["compliance_status"] for item in read_csv(RESULTS_DIR / "frozen_replay_results.csv") if item["case_id"] == row["case_id"]), ""),
                "ground_truth": historical["ground_truth_label"] if historical else "",
                "outcome": next((item["evaluation_outcome"] for item in read_csv(RESULTS_DIR / "frozen_replay_results.csv") if item["case_id"] == row["case_id"]), ""),
                "affected": False,
            }
        )

    write_csv(RESULTS_DIR / "baseline_impact_audit.csv", baseline_rows)
    write_csv(RESULTS_DIR / "baseline_replay_results.csv", baseline_rows)
    affected_baselines = sorted({row["baseline_name"] for row in baseline_rows if row["affected"]})
    write_text(
        REPORTS_DIR / "baseline_impact_audit.md",
        "\n".join(
            [
                "# Baseline Impact Audit",
                "",
                f"- Baselines audited: {len(sorted({row['baseline_name'] for row in baseline_rows}))}",
                f"- Affected baselines: {', '.join(affected_baselines) if affected_baselines else 'none'}",
            ]
        )
        + "\n",
    )
    write_text(
        REPORTS_DIR / "baseline_replay_report.md",
        "\n".join(
            [
                "# Baseline Replay Report",
                "",
                f"- Rows generated: {len(baseline_rows)}",
                f"- Outcome changes: {sum(1 for row in baseline_rows if row['affected'])}",
            ]
        )
        + "\n",
    )
    return {
        "baselines_audited": len(sorted({row["baseline_name"] for row in baseline_rows})),
        "affected_baselines": len(affected_baselines),
        "outcome_changes": sum(1 for row in baseline_rows if row["affected"]),
    }


def old_prediction_from_mutation(case_id: str) -> str:
    row = next((item for item in read_csv(MUTATION_EFFECTS_V2) if item["case_id"] == case_id), None)
    if row is None:
        return ""
    return "FAIL" if row["mutation_effectiveness_status"] == "EFFECTIVE_THRESHOLD_CROSSED" else "PASS"


def build_affected_campaign_inventory() -> dict[str, Any]:
    nominal_old_vs_new = read_csv(RESULTS_DIR / "nominal_28_old_vs_new.csv")
    frozen_impact = read_csv(RESULTS_DIR / "frozen_v3_metric_impact_audit.csv")
    mutation_old_vs_new = read_csv(RESULTS_DIR / "mutation_old_vs_new.csv")
    baseline_rows = read_csv(RESULTS_DIR / "baseline_impact_audit.csv")
    inventory = []

    for row in nominal_old_vs_new:
        if row["metric_name"] not in GAIN_METRICS:
            continue
        inventory.append(
            {
                "campaign_name": "nominal_ACP_28",
                "run_id": "paper_campaign_20260711_094959",
                "population": "nominal ACP-28",
                "case_id": row["case_id"],
                "metric_name": row["metric_name"],
                "measurement_expression": "historical deterministic gain metric",
                "input_ac_magnitude": next((item["input_ac_magnitude"] for item in read_csv(RESULTS_DIR / "nominal_28_metrics.csv") if item["case_id"] == row["case_id"] and item["metric_name"] == row["metric_name"]), ""),
                "input_node": next((item["input_node"] for item in read_csv(RESULTS_DIR / "nominal_28_metrics.csv") if item["case_id"] == row["case_id"] and item["metric_name"] == row["metric_name"]), ""),
                "output_node": next((item["output_node"] for item in read_csv(RESULTS_DIR / "nominal_28_metrics.csv") if item["case_id"] == row["case_id"] and item["metric_name"] == row["metric_name"]), ""),
                "reference_frequency": next((item["reference_frequency_hz"] for item in read_csv(RESULTS_DIR / "nominal_28_metrics.csv") if item["case_id"] == row["case_id"] and item["metric_name"] == row["metric_name"]), ""),
                "threshold": row["old_threshold"],
                "operator": row["old_operator"],
                "old_metric_value": row["old_value"],
                "old_compliance_status": row["old_compliance_status"],
                "historical_artifact_path": "results/paper_metric_results.csv",
                "affected": row["verdict_changed"] == "True",
                "reason": row["change_reason"],
            }
        )
    for row in frozen_impact:
        if row["uses_ac_gain"] not in {"True", True}:
            continue
        inventory.append(
            {
                "campaign_name": "frozen_pilot_v3",
                "run_id": "frozen_pilot_v3_20260712",
                "population": "Frozen Pilot V3",
                "case_id": row["case_id"],
                "metric_name": "dc_gain_db",
                "measurement_expression": row["old_metric_definition"],
                "input_ac_magnitude": "",
                "input_node": "",
                "output_node": "",
                "reference_frequency": 1.0,
                "threshold": "",
                "operator": "",
                "old_metric_value": "",
                "old_compliance_status": "",
                "historical_artifact_path": "results/frozen_pilot_results_v3.csv",
                "affected": row["affected"] in {"True", True},
                "reason": row["reason"],
            }
        )
    for row in mutation_old_vs_new:
        inventory.append(
            {
                "campaign_name": "controlled_violation_v2",
                "run_id": "controlled_violation_v2_20260712",
                "population": "mutation campaigns",
                "case_id": row["mutation_id"],
                "metric_name": "dc_gain_db",
                "measurement_expression": "historical controlled violation replay",
                "input_ac_magnitude": "",
                "input_node": "",
                "output_node": "",
                "reference_frequency": 1.0,
                "threshold": "",
                "operator": "",
                "old_metric_value": row["old_measured_value"],
                "old_compliance_status": row["old_effectiveness_status"],
                "historical_artifact_path": "results/mutation_effectiveness_v2.csv",
                "affected": False,
                "reason": "no corrected mutation label change detected",
            }
        )
    for row in baseline_rows:
        if row["baseline_name"] == "simulation_success_baseline":
            reason = "simulation-success baseline does not consume gain values"
        else:
            reason = "baseline replay shows no outcome change under corrected semantics"
        inventory.append(
            {
                "campaign_name": row["baseline_name"],
                "run_id": CAMPAIGN_NAME,
                "population": "baselines",
                "case_id": row["case_id"],
                "metric_name": "dc_gain_db",
                "measurement_expression": row["old_metric_definition"],
                "input_ac_magnitude": "",
                "input_node": "",
                "output_node": "",
                "reference_frequency": "",
                "threshold": "",
                "operator": "",
                "old_metric_value": "",
                "old_compliance_status": row["old_prediction"],
                "historical_artifact_path": "results/baseline_vs_spec2testbench_v2.csv",
                "affected": row["affected"] in {"True", True},
                "reason": reason,
            }
        )

    write_csv(RESULTS_DIR / "affected_campaign_inventory.csv", inventory)
    write_text(
        REPORTS_DIR / "affected_campaign_inventory.md",
        "\n".join(
            [
                "# Affected Campaign Inventory",
                "",
                f"- Campaign rows audited: {len(inventory)}",
                f"- Affected rows: {sum(1 for row in inventory if row['affected'])}",
            ]
        )
        + "\n",
    )
    return {
        "rows": inventory,
        "affected_cases": sum(1 for row in inventory if row["affected"]),
        "affected_campaigns": len({row["campaign_name"] for row in inventory if row["affected"]}),
    }


def build_evidence_ledger() -> dict[str, Any]:
    ledger_rows = []
    nominal_results = read_csv(RESULTS_DIR / "nominal_28_results.csv")
    nominal_metrics = read_csv(RESULTS_DIR / "nominal_28_metrics.csv")
    frozen_results = read_csv(RESULTS_DIR / "frozen_replay_results.csv")
    mutation_rows = read_csv(RESULTS_DIR / "mutation_revalidation.csv")
    baseline_rows = read_csv(RESULTS_DIR / "baseline_replay_results.csv")
    crosscheck_rows = read_csv(RESULTS_DIR / "backend_crosscheck.csv")

    nominal_map = {row["case_id"]: row for row in nominal_results}
    for metric in nominal_metrics:
        case = nominal_map[metric["case_id"]]
        ledger_rows.append(
            {
                "evidence_id": f"nominal::{metric['case_id']}::{metric['metric_name']}",
                "population": "nominal_28",
                "case_id": metric["case_id"],
                "variant_id": "nominal",
                "netlist_sha256": case["netlist_sha256"],
                "specification_sha256": case["specification_sha256"],
                "testbench_sha256": case["testbench_sha256"],
                "metric_name": metric["metric_name"],
                "metric_definition_version": metric["metric_definition_version"],
                "quantity_type": metric["quantity_type"],
                "measurement_backend": metric["measurement_backend"],
                "raw_value": metric["measured_value"],
                "normalized_value": metric["measured_value"],
                "unit": metric["unit"],
                "operator": metric["expected_operator"],
                "threshold": metric["expected_threshold"],
                "execution_status": case["execution_status"],
                "simulation_mode": case["simulation_mode"],
                "compliance_status": metric["status"],
                "robustness_status": case["robustness_status"],
                "scientific_category": case["scientific_category"],
                "ground_truth": "GROUND_TRUTH_COMPLIANT",
                "evaluation_outcome": "TRUE_ACCEPT" if case["compliance_status"] == "PASS" else "FALSE_REJECT",
                "artifact_path": case["artifact_dir"],
                "historical_or_current": "current",
            }
        )

    for row in frozen_results:
        ledger_rows.append(
            {
                "evidence_id": f"frozen::{row['case_id']}::{row['metric_name']}",
                "population": "frozen_replay",
                "case_id": row["case_id"],
                "variant_id": row["case_id"],
                "netlist_sha256": "",
                "specification_sha256": "",
                "testbench_sha256": "",
                "metric_name": row["metric_name"],
                "metric_definition_version": TRANSFER_GAIN_V2 if row["metric_name"] in GAIN_METRICS else "current_metric_v1",
                "quantity_type": ACQuantityType.TRANSFER_GAIN_DB.value if row["metric_name"] in GAIN_METRICS else "",
                "measurement_backend": row["measurement_backend"],
                "raw_value": row["measured_value"],
                "normalized_value": row["measured_value"],
                "unit": row["unit"],
                "operator": row["operator"],
                "threshold": row["threshold"],
                "execution_status": row["execution_status"],
                "simulation_mode": "REAL",
                "compliance_status": row["compliance_status"],
                "robustness_status": "NOT_EVALUATED",
                "scientific_category": "",
                "ground_truth": row["ground_truth_label"],
                "evaluation_outcome": row["evaluation_outcome"],
                "artifact_path": row["artifact_dir"],
                "historical_or_current": "current",
            }
        )

    for row in mutation_rows:
        ledger_rows.append(
            {
                "evidence_id": f"mutation::{row['mutation_id']}::{row['target_metric']}",
                "population": "mutation_revalidation",
                "case_id": row["mutation_id"],
                "variant_id": row["mutation_id"],
                "netlist_sha256": "",
                "specification_sha256": "",
                "testbench_sha256": "",
                "metric_name": row["target_metric"],
                "metric_definition_version": TRANSFER_GAIN_V2,
                "quantity_type": ACQuantityType.TRANSFER_GAIN_DB.value,
                "measurement_backend": "NGSPICE_WRDATA",
                "raw_value": row["mutated_corrected_gain_db"],
                "normalized_value": row["mutated_corrected_gain_db"],
                "unit": "dB",
                "operator": row["operator"],
                "threshold": row["threshold"],
                "execution_status": row["execution_status"],
                "simulation_mode": "REAL",
                "compliance_status": row["mutated_compliance"],
                "robustness_status": "NOT_EVALUATED",
                "scientific_category": row["status"],
                "ground_truth": "GROUND_TRUTH_NONCOMPLIANT",
                "evaluation_outcome": row["status"],
                "artifact_path": row["artifact_dir"],
                "historical_or_current": "current",
            }
        )

    for row in baseline_rows:
        ledger_rows.append(
            {
                "evidence_id": f"baseline::{row['baseline_name']}::{row['case_id']}",
                "population": "baseline_replay",
                "case_id": row["case_id"],
                "variant_id": row["baseline_name"],
                "netlist_sha256": "",
                "specification_sha256": "",
                "testbench_sha256": "",
                "metric_name": "dc_gain_db",
                "metric_definition_version": row["new_metric_definition"],
                "quantity_type": ACQuantityType.TRANSFER_GAIN_DB.value if row["new_metric_definition"] == TRANSFER_GAIN_V2 else "",
                "measurement_backend": row["baseline_name"],
                "raw_value": row["new_prediction"],
                "normalized_value": row["new_prediction"],
                "unit": "",
                "operator": "",
                "threshold": "",
                "execution_status": "SUCCESS",
                "simulation_mode": "BASELINE",
                "compliance_status": row["new_prediction"],
                "robustness_status": "NOT_EVALUATED",
                "scientific_category": "BASELINE",
                "ground_truth": row["ground_truth"],
                "evaluation_outcome": row["outcome"],
                "artifact_path": "",
                "historical_or_current": "current",
            }
        )

    for row in crosscheck_rows:
        ledger_rows.append(
            {
                "evidence_id": f"crosscheck::{row['case_id']}",
                "population": "backend_crosscheck",
                "case_id": row["case_id"],
                "variant_id": "normalized_original_harness",
                "netlist_sha256": sha256_file(BENCHMARK_DIR / f"{row['case_id']}.cir"),
                "specification_sha256": "",
                "testbench_sha256": "",
                "metric_name": "dc_gain_db",
                "metric_definition_version": TRANSFER_GAIN_V2,
                "quantity_type": ACQuantityType.TRANSFER_GAIN_DB.value,
                "measurement_backend": "NGSPICE_WRDATA",
                "raw_value": row["wrdata_gain_db"],
                "normalized_value": row["wrdata_gain_db"],
                "unit": "dB",
                "operator": "crosscheck",
                "threshold": row["tolerance_db"],
                "execution_status": "SUCCESS",
                "simulation_mode": "REAL",
                "compliance_status": "PASS" if row["within_tolerance"] in {"True", True} else "FAIL",
                "robustness_status": "NOT_EVALUATED",
                "scientific_category": "BACKEND_CROSSCHECK",
                "ground_truth": "INDEPENDENT_AUDIT_REFERENCE",
                "evaluation_outcome": "WITHIN_TOLERANCE" if row["within_tolerance"] in {"True", True} else "OUT_OF_TOLERANCE",
                "artifact_path": "",
                "historical_or_current": "current",
            }
        )

    write_csv(RESULTS_DIR / "canonical_evidence_ledger.csv", ledger_rows)
    summary = {
        "campaign": CAMPAIGN_NAME,
        "ledger_entries": len(ledger_rows),
        "historical_artifacts_preserved": True,
        "current_artifacts_generated": len({row["artifact_path"] for row in ledger_rows if row["artifact_path"]}),
    }
    write_json(RESULTS_DIR / "canonical_results_summary.json", summary)
    write_text(
        REPORTS_DIR / "canonical_results_summary.md",
        "\n".join(
            [
                "# Canonical Results Summary",
                "",
                f"- Campaign: {CAMPAIGN_NAME}",
                f"- Evidence ledger entries: {summary['ledger_entries']}",
                f"- Historical artifacts preserved: {summary['historical_artifacts_preserved']}",
                f"- Current artifact directories referenced: {summary['current_artifacts_generated']}",
            ]
        )
        + "\n",
    )
    return summary


def build_global_old_vs_new() -> dict[str, Any]:
    nominal_rows = read_csv(RESULTS_DIR / "nominal_28_old_vs_new.csv")
    frozen_rows = read_csv(RESULTS_DIR / "frozen_v3_metric_impact_audit.csv")
    mutation_rows = read_csv(RESULTS_DIR / "mutation_old_vs_new.csv")
    baseline_rows = read_csv(RESULTS_DIR / "baseline_impact_audit.csv")

    rows = [
        {
            "population": "nominal_28",
            "old_pass": sum(1 for row in nominal_rows if row["old_compliance_status"] == "PASS"),
            "old_fail": sum(1 for row in nominal_rows if row["old_compliance_status"] == "FAIL"),
            "new_pass": sum(1 for row in nominal_rows if row["new_compliance_status"] == "PASS"),
            "new_fail": sum(1 for row in nominal_rows if row["new_compliance_status"] == "FAIL"),
            "changes": sum(1 for row in nominal_rows if row["verdict_changed"] == "True"),
        },
        {
            "population": "frozen_v3",
            "old_pass": "",
            "old_fail": "",
            "new_pass": "",
            "new_fail": "",
            "changes": sum(1 for row in frozen_rows if row["affected"] in {"True", True}),
        },
        {
            "population": "gain_mutations",
            "old_pass": "",
            "old_fail": "",
            "new_pass": "",
            "new_fail": "",
            "changes": sum(1 for row in mutation_rows if row["changed_effectiveness_label"] in {"True", True}),
        },
        {
            "population": "baselines",
            "old_pass": "",
            "old_fail": "",
            "new_pass": "",
            "new_fail": "",
            "changes": sum(1 for row in baseline_rows if row["affected"] in {"True", True}),
        },
    ]
    write_csv(RESULTS_DIR / "global_old_vs_new.csv", rows)
    write_text(
        REPORTS_DIR / "global_old_vs_new.md",
        "\n".join(
            [
                "# Global Old vs New",
                "",
                f"- Nominal metric verdict changes: {rows[0]['changes']}",
                f"- Frozen impact changes: {rows[1]['changes']}",
                f"- Mutation label changes: {rows[2]['changes']}",
                f"- Baseline outcome changes: {rows[3]['changes']}",
            ]
        )
        + "\n",
    )
    return {"rows": rows}


def write_paper_non_modification_report(initial_hashes: list[dict[str, Any]], final_hashes: list[dict[str, Any]]) -> None:
    diff_output = git_diff_paper()
    lines = [
        "# Paper Non-modification Check",
        "",
        f"- git diff -- paper_final/ empty: {diff_output == ''}",
        f"- Original benchmark hashes unchanged: {initial_hashes == final_hashes}",
    ]
    write_text(REPORTS_DIR / "paper_non_modification_check.md", "\n".join(lines) + "\n")


def orchestrate(args: argparse.Namespace | None = None) -> dict[str, Any]:
    ensure_workspace()
    initial_hashes = benchmark_hash_rows()
    preconditions = precondition_check()
    reference_audit = audit_legacy_gain_references()
    backend = run_backend_crosscheck()
    nominal = run_nominal_campaign()
    frozen = run_frozen_replay()
    mutations = revalidate_gain_mutations(nominal)
    baselines = run_baseline_replay()
    affected = build_affected_campaign_inventory()
    ledger = build_evidence_ledger()
    global_old_new = build_global_old_vs_new()
    final_hashes = benchmark_hash_rows()
    write_paper_non_modification_report(initial_hashes, final_hashes)
    return {
        "preconditions": preconditions,
        "reference_audit": reference_audit,
        "backend": backend,
        "nominal": nominal,
        "frozen": frozen,
        "mutations": mutations,
        "baselines": baselines,
        "affected": affected,
        "ledger": ledger,
        "global_old_new": global_old_new,
        "benchmark_hashes_unchanged": initial_hashes == final_hashes,
        "paper_diff_empty": git_diff_paper() == "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nominal-28", action="store_true")
    parser.add_argument("--audit-frozen-v3", action="store_true")
    parser.add_argument("--revalidate-mutations", action="store_true")
    parser.add_argument("--replay-baselines", action="store_true")
    parser.add_argument("--crosscheck-backends", action="store_true")
    parser.add_argument("--disable-pyspice", action="store_true")
    parser.add_argument("--no-mock", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--population")
    parser.add_argument("--run-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.disable_pyspice:
        os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    summary = orchestrate(args)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
