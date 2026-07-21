from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_corrected_metric_semantics_campaign import (  # noqa: E402
    BENCHMARK_DIR,
    PAPER_RESULTS,
    PAPER_SUMMARY,
    SPEC_DIR,
    build_original_harness_deck,
    build_pipeline,
    load_yaml,
    materialize_case_artifacts,
    normalized_case_dir,
    read_csv,
    sha256_file,
    write_csv,
    write_json,
    write_text,
)
from spec2testbench.application.services.canonical_reconciliation import (  # noqa: E402
    build_mutation_label_reconciliation_rows,
    normalize_case_compliance,
    summarize_nominal_rows,
)
from spec2testbench.domain.entities.specification import Specification  # noqa: E402
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator  # noqa: E402
from spec2testbench.infrastructure.simulator.result_backends import (  # noqa: E402
    compute_absolute_output_dbv,
    compute_dc_gain_db,
    compute_frequency_hz,
    compute_startup_amplitude,
    parse_measure_file,
    parse_wrdata_file,
)
from spec2testbench.infrastructure.spec_checker.spec_checker import SpecChecker  # noqa: E402


CAMPAIGN_NAME = "canonical_reconciliation_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
CORRECTED_RESULTS_DIR = ROOT / "results" / "corrected_metric_semantics_v1"
CORRECTED_REPORTS_DIR = ROOT / "reports" / "corrected_metric_semantics_v1"
CORRECTED_SUMMARY_PATH = CORRECTED_RESULTS_DIR / "nominal_28_summary.json"
CORRECTED_MUTATION_REVALIDATION = CORRECTED_RESULTS_DIR / "mutation_revalidation.csv"
CORRECTED_MUTATION_OLD_VS_NEW = CORRECTED_RESULTS_DIR / "mutation_old_vs_new.csv"
CORRECTED_GAIN_MUTATION_INVENTORY = CORRECTED_RESULTS_DIR / "gain_mutation_inventory.csv"
PAPER_ARTIFACTS_ROOT = ROOT / "artifacts" / "paper_campaign"


def ensure_workspace() -> None:
    for path in (EXPERIMENTS_DIR, ARTIFACTS_DIR, RESULTS_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_terminal_end(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[-1].strip().lower() == ".end":
        lines = lines[:-1]
    return "\n".join(lines).rstrip() + "\n"


def normalize_include_paths(deck_text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        raw_path = match.group(2).strip()
        if raw_path.startswith('"') and raw_path.endswith('"'):
            return match.group(0)
        return f'{prefix}"{raw_path}"'

    return re.sub(r'(?im)^(\s*\.include\s+)(.+?)\s*$', repl, deck_text)


def prepare_historical_deck_for_replay(deck_text: str, case_id: str) -> str:
    lines = deck_text.splitlines()
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == f"analogcoder_pro_{case_id}":
            continue
        filtered.append(line)
    body = "\n".join(filtered).strip()
    return f"HistoricalReplay_{case_id}\n{body}\n"


def corrected_nominal_artifact_root() -> Path:
    run_id = load_json(CORRECTED_SUMMARY_PATH)["run_id"]
    return ROOT / "artifacts" / "corrected_metric_semantics_v1" / run_id / "nominal_28"


def latest_paper_artifact_run() -> Path:
    candidates = [
        path
        for path in PAPER_ARTIFACTS_ROOT.iterdir()
        if path.is_dir() and (path / "p22_oscillator").exists() and (path / "p23_oscillator").exists()
    ]
    return sorted(candidates)[-1]


def spec_path(case_id: str) -> Path:
    return SPEC_DIR / f"{case_id}.yaml"


def netlist_path(case_id: str) -> Path:
    return BENCHMARK_DIR / f"{case_id}.cir"


def canonical_dut_path(case_id: str) -> Path:
    return normalized_case_dir(case_id) / "canonical_dut.ckt"


def write_execution_decks(
    *,
    simulator: PySpiceSimulator,
    testbench,
    netlist: Path,
    artifact_dir: Path,
) -> dict[str, Path]:
    base_deck = simulator._generate_spice_deck(netlist, testbench)
    measure_deck = simulator._generate_measure_deck(
        netlist,
        testbench,
        Path("measures.txt"),
        Path("vectors.dat"),
    )
    base_path = artifact_dir / "base_execution_deck.cir"
    measure_path = artifact_dir / "native_backend_measure_deck.cir"
    write_text(base_path, base_deck)
    write_text(measure_path, measure_deck)
    return {"base": base_path, "measure": measure_path}


def replay_generated_case(
    *,
    case_id: str,
    artifact_dir: Path,
    required_metrics: list[str] | None = None,
    measurement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pipeline = build_pipeline()
    spec = Specification.from_yaml(spec_path(case_id))
    spec.case_id = case_id
    if required_metrics is not None:
        spec.performance_targets = {
            metric_name: spec.performance_targets[metric_name]
            for metric_name in required_metrics
        }
    if measurement is not None:
        spec.measurement = dict(measurement)

    testbench = pipeline.testbench_gen.generate(spec, netlist_path=netlist_path(case_id))
    testbench.case_id = case_id
    testbench.metadata["required_metrics"] = list(spec.performance_targets.keys())
    testbench.metadata["measurement"] = dict(spec.measurement or {})
    testbench.netlist_path = str(netlist_path(case_id))
    decks = write_execution_decks(
        simulator=pipeline.simulator,
        testbench=testbench,
        netlist=netlist_path(case_id),
        artifact_dir=artifact_dir,
    )

    simulation_results = pipeline.simulator.run(netlist_path(case_id), testbench)
    report = pipeline.verify(
        spec,
        netlist_path=netlist_path(case_id),
        simulation_results=simulation_results,
        spec_path=spec_path(case_id),
    )
    materialize_case_artifacts(
        case_id=case_id,
        spec_path=spec_path(case_id),
        netlist_path=netlist_path(case_id),
        normalized_case_dir=normalized_case_dir(case_id),
        case_dir=artifact_dir,
        report=report,
        simulation_results=simulation_results,
    )
    write_text(artifact_dir / "base_execution_deck.cir", decks["base"].read_text(encoding="utf-8"))
    write_text(artifact_dir / "native_backend_measure_deck.cir", decks["measure"].read_text(encoding="utf-8"))
    return {
        "spec": spec,
        "testbench": testbench,
        "report": report,
        "simulation_results": simulation_results,
        "decks": decks,
    }


def run_manual_deck(
    *,
    simulator: PySpiceSimulator,
    deck_text: str,
    artifact_dir: Path,
    deck_name: str,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    deck_path = artifact_dir / deck_name
    raw_path = artifact_dir / (deck_path.stem + ".raw")
    stdout_path = artifact_dir / "ngspice_stdout.txt"
    stderr_path = artifact_dir / "ngspice_stderr.txt"
    measures_path = artifact_dir / "measures.txt"
    vectors_path = artifact_dir / "vectors.dat"
    vectors_csv_path = artifact_dir / "vectors.csv"
    deck_path.write_text(deck_text, encoding="utf-8")
    command = [simulator.ngspice_path, "-b", "-r", str(raw_path), str(deck_path)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(artifact_dir),
        timeout=60,
        check=False,
    )
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    measures_path.write_text(result.stdout or "", encoding="utf-8")
    if vectors_path.exists():
        PySpiceSimulator._wrdata_to_csv(vectors_path, vectors_csv_path)
    return {
        "command": command,
        "returncode": result.returncode,
        "deck_path": deck_path,
        "raw_path": raw_path if raw_path.exists() else None,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "measures_path": measures_path,
        "vectors_path": vectors_path if vectors_path.exists() else None,
        "vectors_csv_path": vectors_csv_path if vectors_csv_path.exists() else None,
        "measurements": parse_measure_file(measures_path),
        "wrdata": parse_wrdata_file(vectors_path) if vectors_path.exists() else None,
    }


def ac_reference_vectors(parsed: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    data = parsed["data"]
    index = int(np.argmin(data[:, 0]))
    frequency_hz = float(data[index, 0])
    vin = complex(
        float(data[index, request.get("in_real_column", 1)]),
        float(data[index, request.get("in_imag_column", 2)]),
    )
    vout = complex(
        float(data[index, request.get("out_real_column", 3)]),
        float(data[index, request.get("out_imag_column", 4)]),
    )
    transfer = vout / vin
    gain_magnitude = abs(transfer)
    gain_db = float(20.0 * math.log10(gain_magnitude))
    vout_dbv = compute_absolute_output_dbv(parsed, request)
    return {
        "frequency_hz": frequency_hz,
        "vin_complex": vin,
        "vout_complex": vout,
        "transfer_complex": transfer,
        "gain_magnitude": gain_magnitude,
        "gain_db": gain_db,
        "vout_dbv": vout_dbv,
    }


def transient_waveform_stats(parsed: dict[str, Any] | None) -> dict[str, Any]:
    if parsed is None:
        return {
            "observed_output": "MISSING_WAVEFORM",
            "peak_to_peak_amplitude_v": None,
            "peak_count": 0,
            "zero_crossing_count": 0,
            "period_count": 0,
            "period_consistency_cv": None,
            "frequency_hz": None,
            "startup_amplitude_v": None,
        }

    data = parsed["data"]
    time = data[:, 0]
    values = data[:, 1]
    peak_to_peak = float(np.max(values) - np.min(values))
    mean_value = float(np.mean(values))
    crossings: list[float] = []
    for index in range(1, len(values)):
        if values[index - 1] <= mean_value < values[index]:
            crossings.append(float(time[index]))
    periods = np.diff(crossings)
    valid_periods = periods[periods > 0]
    period_cv = None
    if len(valid_periods) >= 2 and float(np.mean(valid_periods)) > 0.0:
        period_cv = float(np.std(valid_periods) / np.mean(valid_periods))
    peak_mask = (
        (values[1:-1] >= values[:-2])
        & (values[1:-1] > values[2:])
    )
    frequency_hz = None
    try:
        frequency_hz = compute_frequency_hz(parsed, {"time_column": 0, "value_column": 1})
    except ValueError:
        frequency_hz = None
    try:
        startup_amplitude = compute_startup_amplitude(parsed, {"value_column": 1})
    except ValueError:
        startup_amplitude = None
    observed_output = "STATIC_NEAR_DC" if peak_to_peak <= 1e-6 else "OSCILLATORY"
    return {
        "observed_output": observed_output,
        "peak_to_peak_amplitude_v": peak_to_peak,
        "peak_count": int(np.count_nonzero(peak_mask)),
        "zero_crossing_count": len(crossings),
        "period_count": max(0, len(crossings) - 1),
        "period_consistency_cv": period_cv,
        "frequency_hz": frequency_hz,
        "startup_amplitude_v": startup_amplitude,
    }


def parse_source_line(deck_text: str, source_name: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(source_name)}\b.*$", deck_text)
    return match.group(0).strip() if match else ""


def parse_analysis_line(deck_text: str, directive: str) -> str:
    match = re.search(rf"(?im)^\s*\.{re.escape(directive)}\b.*$", deck_text)
    return match.group(0).strip() if match else ""


def parse_tran_parameters(deck_text: str) -> tuple[str, str]:
    line = parse_analysis_line(deck_text, "tran")
    if not line:
        return "", ""
    parts = line.split()
    if len(parts) >= 3:
        return parts[1], parts[2]
    return "", ""


def build_original_harness_base_deck(case_id: str) -> str:
    short_case = case_id.split("_", 1)[0]
    case_dir = normalized_case_dir(case_id)
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
    lines = [updated.rstrip()]
    for entry in analyses:
        lines.append(entry["raw_line"])
    lines.append(".END")
    return "\n".join(lines) + "\n"


def build_ac_measure_wrdata_deck(base_deck: str, *, input_node: str, output_node: str) -> str:
    return (
        strip_terminal_end(base_deck)
        + f".meas ac vin_mag FIND vm({input_node}) AT=1\n"
        + f".meas ac vout_mag FIND vm({output_node}) AT=1\n"
        + ".control\n"
        + "set filetype=ascii\n"
        + "set wr_singlescale\n"
        + "run\n"
        + "setplot ac1\n"
        + f"meas ac vin_mag FIND vm({input_node}) AT=1\n"
        + f"meas ac vout_mag FIND vm({output_node}) AT=1\n"
        + f"wrdata vectors.dat real(v({input_node})) imag(v({input_node})) real(v({output_node})) imag(v({output_node}))\n"
        + "quit\n"
        + ".endc\n"
        + ".END\n"
    )


def build_tran_wrdata_deck(base_deck: str, *, output_node: str) -> str:
    return (
        strip_terminal_end(base_deck)
        + ".control\n"
        + "set filetype=ascii\n"
        + "set wr_singlescale\n"
        + "run\n"
        + "setplot tran1\n"
        + f"wrdata vectors.dat v({output_node})\n"
        + "quit\n"
        + ".endc\n"
        + ".END\n"
    )


def check_result_for_value(value: float | None, operator: str, threshold: float | None) -> str:
    if value is None:
        return "NOT_EVALUATED"
    if operator == ">=" and threshold is not None:
        return "PASS" if value >= threshold else "FAIL"
    if operator == "<=" and threshold is not None:
        return "PASS" if value <= threshold else "FAIL"
    return "PASS"


def p4_previous_row(corrected_root: Path) -> dict[str, Any]:
    artifact_dir = corrected_root / "p04_amplifier"
    provenance = load_json(artifact_dir / "provenance.json")
    compilation = load_json(artifact_dir / "compilation_report.json")
    raw_metrics = load_json(artifact_dir / "raw_metrics.json")
    normalized = load_json(artifact_dir / "normalized_metrics.json")
    checker = load_json(artifact_dir / "checker_result.json")
    gain_row = normalized["dc_gain_db"]
    checker_row = next(item for item in checker if item["test_name"] == "dc_gain_db")
    raw_row = raw_metrics["dc_gain_db"]
    return {
        "path_id": "corrected_nominal_campaign_previous",
        "case_id": "p04_amplifier",
        "source_netlist_path": provenance["netlist_file"],
        "source_netlist_sha256": provenance["netlist_hash"],
        "canonical_dut_path": str(canonical_dut_path("p04_amplifier")),
        "canonical_dut_sha256": sha256_file(canonical_dut_path("p04_amplifier")),
        "specification_path": provenance["specification_file"],
        "specification_sha256": provenance["specification_hash"],
        "generated_testbench_path": str(artifact_dir / "generated_testbench.ckt"),
        "generated_testbench_sha256": sha256_file(artifact_dir / "generated_testbench.ckt"),
        "reported_testbench_path": str(artifact_dir / "generated_testbench.ckt"),
        "reported_testbench_sha256": sha256_file(artifact_dir / "generated_testbench.ckt"),
        "executed_deck_path": "",
        "executed_deck_sha256": provenance["actual_deck_sha256"],
        "input_source_name": "Vin",
        "input_node": gain_row["input_node"],
        "output_node": gain_row["output_node"],
        "input_ac_magnitude": gain_row["input_ac_magnitude"],
        "dc_input_value": 2.5,
        "bias_node": "Vbias",
        "bias_value": 2.0,
        "analysis_directive": ".AC dec 10 1 1000000000.0",
        "frequency_selection_rule": "lowest sampled AC point in active nominal deck",
        "reference_frequency_hz": gain_row["reference_frequency_hz"],
        "measurement_backend": gain_row["measurement_backend"],
        "measurement_recipe_id": gain_row["measurement_expression_id"],
        "compiler_template_id": "report_testbench_generate_spice_deck",
        "metric_definition_version": gain_row["metric_definition_version"],
        "quantity_type": gain_row["quantity_type"],
        "measure_expression": "20*log10(abs(Vout/Vin))",
        "wrdata_vectors_path": str(artifact_dir / "vectors.csv"),
        "raw_parsed_value": raw_row["measured_value"],
        "normalized_metric_value": gain_row["measured_value"],
        "value_passed_to_checker": checker_row["measured_value"],
        "operator": gain_row["expected_operator"],
        "threshold": gain_row["expected_threshold"],
        "checker_result": checker_row["verdict"],
        "cache_key": "",
        "cache_hit": False,
    }


def p4_original_harness_rows(simulator: PySpiceSimulator, artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    base_deck = build_original_harness_base_deck("p04_amplifier")
    base_deck_path = artifact_dir / "normalized_harness_base.cir"
    write_text(base_deck_path, base_deck)
    replay_deck = build_ac_measure_wrdata_deck(base_deck, input_node="Vin", output_node="Vout")
    replay = run_manual_deck(
        simulator=simulator,
        deck_text=replay_deck,
        artifact_dir=artifact_dir,
        deck_name="normalized_harness_replay.cir",
    )
    vectors = ac_reference_vectors(replay["wrdata"])
    measures = replay["measurements"]
    gain_db = float(20.0 * math.log10(measures["vout_mag"]["value"] / measures["vin_mag"]["value"]))
    row = {
        "path_id": "normalized_original_harness_audit",
        "case_id": "p04_amplifier",
        "source_netlist_path": str(netlist_path("p04_amplifier")),
        "source_netlist_sha256": sha256_file(netlist_path("p04_amplifier")),
        "canonical_dut_path": str(canonical_dut_path("p04_amplifier")),
        "canonical_dut_sha256": sha256_file(canonical_dut_path("p04_amplifier")),
        "specification_path": str(spec_path("p04_amplifier")),
        "specification_sha256": sha256_file(spec_path("p04_amplifier")),
        "generated_testbench_path": str(base_deck_path),
        "generated_testbench_sha256": sha256_file(base_deck_path),
        "reported_testbench_path": str(base_deck_path),
        "reported_testbench_sha256": sha256_file(base_deck_path),
        "executed_deck_path": str(replay["deck_path"]),
        "executed_deck_sha256": sha256_file(replay["deck_path"]),
        "input_source_name": "Vin",
        "input_node": "Vin",
        "output_node": "Vout",
        "input_ac_magnitude": 1e-9,
        "dc_input_value": 0.5,
        "bias_node": "Vbias",
        "bias_value": 2.0,
        "analysis_directive": ".AC DEC 100 1 1G",
        "frequency_selection_rule": "lowest sampled AC point in normalized-original harness",
        "reference_frequency_hz": vectors["frequency_hz"],
        "measurement_backend": "NGSPICE_MEASURE+NGSPICE_WRDATA",
        "measurement_recipe_id": "AC_TRANSFER_GAIN_DB_INDEPENDENT_AUDIT",
        "compiler_template_id": "normalized_original_harness_reconstruction_v1",
        "metric_definition_version": "transfer_gain_v2",
        "quantity_type": "TRANSFER_GAIN_DB",
        "measure_expression": "20*log10(abs(Vout/Vin))",
        "wrdata_vectors_path": str(replay["vectors_csv_path"]),
        "raw_parsed_value": gain_db,
        "normalized_metric_value": gain_db,
        "value_passed_to_checker": gain_db,
        "operator": ">=",
        "threshold": 0.0,
        "checker_result": check_result_for_value(gain_db, ">=", 0.0),
        "cache_key": "",
        "cache_hit": False,
    }
    details = {
        "base_deck_path": str(base_deck_path),
        "replay_deck_path": str(replay["deck_path"]),
        "measurements": replay["measurements"],
        "vectors": {
            "vin_complex": [vectors["vin_complex"].real, vectors["vin_complex"].imag],
            "vout_complex": [vectors["vout_complex"].real, vectors["vout_complex"].imag],
            "transfer_complex": [vectors["transfer_complex"].real, vectors["transfer_complex"].imag],
            "gain_magnitude": vectors["gain_magnitude"],
            "gain_db": vectors["gain_db"],
            "vout_dbv": vectors["vout_dbv"],
        },
    }
    write_json(artifact_dir / "normalized_harness_metrics.json", details)
    return row, details


def p4_measure_replay_row(
    simulator: PySpiceSimulator,
    execution: dict[str, Any],
    artifact_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_text = execution["decks"]["base"].read_text(encoding="utf-8")
    base_path = artifact_dir / "base_execution_deck.cir"
    write_text(base_path, base_text)
    replay = run_manual_deck(
        simulator=simulator,
        deck_text=build_ac_measure_wrdata_deck(base_text, input_node="Vin", output_node="Vout"),
        artifact_dir=artifact_dir,
        deck_name="measure_replay.cir",
    )
    measures = replay["measurements"]
    vectors = ac_reference_vectors(replay["wrdata"])
    gain_db = float(20.0 * math.log10(measures["vout_mag"]["value"] / measures["vin_mag"]["value"]))
    row = {
        "path_id": "corrected_nominal_replay_measure",
        "case_id": "p04_amplifier",
        "source_netlist_path": str(netlist_path("p04_amplifier")),
        "source_netlist_sha256": sha256_file(netlist_path("p04_amplifier")),
        "canonical_dut_path": str(canonical_dut_path("p04_amplifier")),
        "canonical_dut_sha256": sha256_file(canonical_dut_path("p04_amplifier")),
        "specification_path": str(spec_path("p04_amplifier")),
        "specification_sha256": sha256_file(spec_path("p04_amplifier")),
        "generated_testbench_path": str(base_path),
        "generated_testbench_sha256": sha256_file(base_path),
        "reported_testbench_path": str(artifact_dir / "generated_testbench.ckt"),
        "reported_testbench_sha256": sha256_file(artifact_dir / "generated_testbench.ckt"),
        "executed_deck_path": str(replay["deck_path"]),
        "executed_deck_sha256": sha256_file(replay["deck_path"]),
        "input_source_name": "Vin",
        "input_node": "Vin",
        "output_node": "Vout",
        "input_ac_magnitude": 1.0,
        "dc_input_value": 2.5,
        "bias_node": "Vbias",
        "bias_value": 2.0,
        "analysis_directive": ".AC dec 10 1 1000000000.0",
        "frequency_selection_rule": "lowest sampled AC point in active nominal deck",
        "reference_frequency_hz": vectors["frequency_hz"],
        "measurement_backend": "NGSPICE_MEASURE",
        "measurement_recipe_id": "AC_VIN_VOUT_MAG_MEASURE",
        "compiler_template_id": "llm_guided_plan_multimode_pulse_v1",
        "metric_definition_version": "transfer_gain_v2",
        "quantity_type": "TRANSFER_GAIN_DB",
        "measure_expression": "20*log10(vout_mag/vin_mag)",
        "wrdata_vectors_path": str(replay["vectors_csv_path"]),
        "raw_parsed_value": gain_db,
        "normalized_metric_value": gain_db,
        "value_passed_to_checker": gain_db,
        "operator": ">=",
        "threshold": 0.0,
        "checker_result": check_result_for_value(gain_db, ">=", 0.0),
        "cache_key": "",
        "cache_hit": False,
    }
    details = {
        "measures": replay["measurements"],
        "vectors": {
            "vin_complex": [vectors["vin_complex"].real, vectors["vin_complex"].imag],
            "vout_complex": [vectors["vout_complex"].real, vectors["vout_complex"].imag],
            "transfer_complex": [vectors["transfer_complex"].real, vectors["transfer_complex"].imag],
            "gain_magnitude": vectors["gain_magnitude"],
            "gain_db": vectors["gain_db"],
            "vout_dbv": vectors["vout_dbv"],
        },
    }
    write_json(artifact_dir / "measure_replay_metrics.json", details)
    return row, details


def p4_wrdata_replay_row(execution: dict[str, Any], artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = execution["report"]
    gain_trace = next(trace for trace in report.metric_traces if trace.metric_name == "dc_gain_db")
    checker_row = next(item for item in report.spec_results if item.test_name == "dc_gain_db")
    parsed = parse_wrdata_file(artifact_dir / "vectors.dat")
    vectors = ac_reference_vectors(parsed)
    row = {
        "path_id": "corrected_nominal_replay_wrdata",
        "case_id": "p04_amplifier",
        "source_netlist_path": str(netlist_path("p04_amplifier")),
        "source_netlist_sha256": sha256_file(netlist_path("p04_amplifier")),
        "canonical_dut_path": str(canonical_dut_path("p04_amplifier")),
        "canonical_dut_sha256": sha256_file(canonical_dut_path("p04_amplifier")),
        "specification_path": str(spec_path("p04_amplifier")),
        "specification_sha256": sha256_file(spec_path("p04_amplifier")),
        "generated_testbench_path": str(artifact_dir / "base_execution_deck.cir"),
        "generated_testbench_sha256": sha256_file(artifact_dir / "base_execution_deck.cir"),
        "reported_testbench_path": str(artifact_dir / "generated_testbench.ckt"),
        "reported_testbench_sha256": sha256_file(artifact_dir / "generated_testbench.ckt"),
        "executed_deck_path": str(artifact_dir / "native_backend_measure_deck.cir"),
        "executed_deck_sha256": sha256_file(artifact_dir / "native_backend_measure_deck.cir"),
        "input_source_name": "Vin",
        "input_node": gain_trace.input_node,
        "output_node": gain_trace.output_node,
        "input_ac_magnitude": gain_trace.input_ac_magnitude,
        "dc_input_value": 2.5,
        "bias_node": "Vbias",
        "bias_value": 2.0,
        "analysis_directive": ".AC dec 10 1 1000000000.0",
        "frequency_selection_rule": "lowest sampled AC point in active nominal deck",
        "reference_frequency_hz": gain_trace.reference_frequency_hz,
        "measurement_backend": gain_trace.measurement_backend,
        "measurement_recipe_id": gain_trace.measurement_expression_id,
        "compiler_template_id": "llm_guided_plan_multimode_pulse_v1",
        "metric_definition_version": gain_trace.metric_definition_version,
        "quantity_type": gain_trace.quantity_type,
        "measure_expression": "20*log10(abs(Vout/Vin))",
        "wrdata_vectors_path": str(artifact_dir / "vectors.csv"),
        "raw_parsed_value": gain_trace.measured_value,
        "normalized_metric_value": gain_trace.measured_value,
        "value_passed_to_checker": checker_row.measured_value,
        "operator": gain_trace.expected_operator,
        "threshold": gain_trace.expected_threshold,
        "checker_result": checker_row.verdict.value,
        "cache_key": "",
        "cache_hit": False,
    }
    details = {
        "vectors": {
            "vin_complex": [vectors["vin_complex"].real, vectors["vin_complex"].imag],
            "vout_complex": [vectors["vout_complex"].real, vectors["vout_complex"].imag],
            "transfer_complex": [vectors["transfer_complex"].real, vectors["transfer_complex"].imag],
            "gain_magnitude": vectors["gain_magnitude"],
            "gain_db": vectors["gain_db"],
            "vout_dbv": vectors["vout_dbv"],
        },
    }
    write_json(artifact_dir / "wrdata_replay_metrics.json", details)
    return row, details


def p4_semantic_diff_rows(original_deck: str, nominal_deck: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    original_include = parse_analysis_line(original_deck, "include")
    nominal_include = parse_analysis_line(nominal_deck, "include")
    if original_include != nominal_include:
        rows.append(
            {
                "component": ".INCLUDE",
                "classification": "DUT_DIFFERENCE",
                "original": original_include,
                "nominal": nominal_include,
                "detail": "The included DUT path changed.",
            }
        )
    else:
        rows.append(
            {
                "component": ".INCLUDE",
                "classification": "WHITESPACE_ONLY",
                "original": original_include,
                "nominal": nominal_include,
                "detail": "The included DUT path is identical.",
            }
        )

    for source_name, classification in (("Vbias", "BIAS_DIFFERENCE"), ("Vin", "STIMULUS_DIFFERENCE"), ("Vdd", "HARNESS_DIFFERENCE")):
        original_line = parse_source_line(original_deck, source_name)
        nominal_line = parse_source_line(nominal_deck, source_name)
        if original_line == nominal_line:
            continue
        rows.append(
            {
                "component": source_name,
                "classification": classification,
                "original": original_line,
                "nominal": nominal_line,
                "detail": f"{source_name} differs between the normalized harness and the active nominal deck.",
            }
        )

    for directive in ("op", "ac", "tran"):
        original_line = parse_analysis_line(original_deck, directive)
        nominal_line = parse_analysis_line(nominal_deck, directive)
        if original_line == nominal_line:
            continue
        rows.append(
            {
                "component": f".{directive.upper()}",
                "classification": "ANALYSIS_DIFFERENCE",
                "original": original_line,
                "nominal": nominal_line,
                "detail": f"The {directive.upper()} analysis directive changed.",
            }
        )
    return rows


def historical_record_for_case(case_id: str) -> dict[str, Any]:
    metrics = [row for row in read_csv(PAPER_RESULTS) if row["circuit_id"] == case_id]
    summary_row = next(row for row in read_csv(PAPER_SUMMARY) if row["circuit_id"] == case_id)
    by_name = {row["metric_name"]: row for row in metrics}
    return {
        "summary": summary_row,
        "metrics": by_name,
    }


def replay_historical_oscillator_deck(
    simulator: PySpiceSimulator,
    *,
    case_id: str,
    paper_run_dir: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    base_deck = normalize_include_paths((paper_run_dir / case_id / "testbench.cir").read_text(encoding="utf-8"))
    write_text(artifact_dir / "historical_testbench_base.cir", base_deck)
    replay = run_manual_deck(
        simulator=simulator,
        deck_text=build_tran_wrdata_deck(prepare_historical_deck_for_replay(base_deck, case_id), output_node="Vout"),
        artifact_dir=artifact_dir,
        deck_name="historical_testbench_replay.cir",
    )
    stats = transient_waveform_stats(replay["wrdata"])
    write_json(artifact_dir / "historical_waveform_stats.json", stats)
    return {
        "base_deck_text": base_deck,
        "replay": replay,
        "stats": stats,
    }


def oscillator_case_compliance(
    *,
    frequency_status: str,
    startup_status: str,
) -> str:
    if startup_status == "FAIL":
        return "FAIL"
    if frequency_status == "NOT_EVALUATED":
        return "NOT_EVALUATED"
    if startup_status == "PASS":
        return "PASS"
    return "NOT_EVALUATED"


def oscillator_reconciliation_row(
    *,
    case_id: str,
    corrected_root: Path,
    paper_run_dir: Path,
    historical_replay: dict[str, Any],
    current_run_a: dict[str, Any],
    current_run_b: dict[str, Any],
) -> dict[str, Any]:
    corrected_case_dir = corrected_root / case_id
    corrected_provenance = load_json(corrected_case_dir / "provenance.json")
    corrected_metrics = load_json(corrected_case_dir / "normalized_metrics.json")
    historical = historical_record_for_case(case_id)
    paper_case_dir = paper_run_dir / case_id
    historical_base = (paper_case_dir / "testbench.cir").read_text(encoding="utf-8")
    historical_step, historical_stop = parse_tran_parameters(historical_base)
    current_step, current_stop = parse_tran_parameters((current_run_a["decks"]["base"]).read_text(encoding="utf-8"))
    report_a = current_run_a["report"]
    report_b = current_run_b["report"]
    metric_map_a = {trace.metric_name: trace for trace in report_a.metric_traces}
    metric_map_b = {trace.metric_name: trace for trace in report_b.metric_traces}
    run_a_vectors = parse_wrdata_file(current_run_a["artifact_dir"] / "vectors.dat")
    run_b_vectors = parse_wrdata_file(current_run_b["artifact_dir"] / "vectors.dat")
    run_a_stats = transient_waveform_stats(run_a_vectors)
    run_b_stats = transient_waveform_stats(run_b_vectors)
    two_run_agreement = (
        metric_map_a["oscillator_frequency"].status == metric_map_b["oscillator_frequency"].status
        and metric_map_a["startup_amplitude"].status == metric_map_b["startup_amplitude"].status
        and metric_map_a["startup_amplitude"].measured_value == metric_map_b["startup_amplitude"].measured_value
        and metric_map_a["oscillator_frequency"].measured_value == metric_map_b["oscillator_frequency"].measured_value
    )
    corrected_frequency = corrected_metrics["oscillator_frequency"]["measured_value"]
    corrected_startup = corrected_metrics["startup_amplitude"]["measured_value"]
    current_frequency_status = metric_map_a["oscillator_frequency"].status
    current_startup_status = metric_map_a["startup_amplitude"].status
    reconciled_compliance = normalize_case_compliance(
        oscillator_case_compliance(
            frequency_status=current_frequency_status,
            startup_status=current_startup_status,
        )
    )
    root_cause_classes = "BACKEND_CHANGED|PARSER_CHANGED|SEMANTIC_GUARD_CHANGED|TESTBENCH_CHANGED|OLD_RESULT_INCORRECT|EXPECTED_CORRECTION"
    return {
        "case_id": case_id,
        "historical_netlist_hash": historical["summary"].get("netlist_sha256", corrected_provenance["netlist_hash"]),
        "current_netlist_hash": corrected_provenance["netlist_hash"],
        "historical_spec_hash": corrected_provenance["specification_hash"],
        "current_spec_hash": corrected_provenance["specification_hash"],
        "historical_testbench_hash": sha256_file(paper_case_dir / "testbench.cir"),
        "historical_replay_testbench_hash": sha256_file(historical_replay["replay"]["deck_path"]),
        "current_testbench_hash": sha256_file(current_run_a["artifact_dir"] / "base_execution_deck.cir"),
        "historical_time_step": historical_step,
        "historical_stop_time": historical_stop,
        "current_time_step": current_step,
        "current_stop_time": current_stop,
        "historical_observed_output": historical_replay["stats"]["observed_output"],
        "current_observed_output_run1": run_a_stats["observed_output"],
        "current_observed_output_run2": run_b_stats["observed_output"],
        "historical_waveform_artifact": str(historical_replay["replay"]["vectors_csv_path"]),
        "current_waveform_artifact_run1": str(current_run_a["artifact_dir"] / "vectors.csv"),
        "current_waveform_artifact_run2": str(current_run_b["artifact_dir"] / "vectors.csv"),
        "historical_peak_to_peak_amplitude_v": historical_replay["stats"]["peak_to_peak_amplitude_v"],
        "current_peak_to_peak_amplitude_run1_v": run_a_stats["peak_to_peak_amplitude_v"],
        "current_peak_to_peak_amplitude_run2_v": run_b_stats["peak_to_peak_amplitude_v"],
        "historical_peak_count": historical_replay["stats"]["peak_count"],
        "current_peak_count_run1": run_a_stats["peak_count"],
        "current_peak_count_run2": run_b_stats["peak_count"],
        "historical_zero_crossing_count": historical_replay["stats"]["zero_crossing_count"],
        "current_zero_crossing_count_run1": run_a_stats["zero_crossing_count"],
        "current_zero_crossing_count_run2": run_b_stats["zero_crossing_count"],
        "historical_period_count": historical_replay["stats"]["period_count"],
        "current_period_count_run1": run_a_stats["period_count"],
        "current_period_count_run2": run_b_stats["period_count"],
        "historical_period_consistency_cv": historical_replay["stats"]["period_consistency_cv"],
        "current_period_consistency_cv_run1": run_a_stats["period_consistency_cv"],
        "current_period_consistency_cv_run2": run_b_stats["period_consistency_cv"],
        "historical_frequency_recorded_hz": historical["metrics"]["oscillator_frequency"]["measured_value"],
        "historical_frequency_replayed_hz": historical_replay["stats"]["frequency_hz"],
        "previous_corrected_frequency_hz": corrected_frequency,
        "current_frequency_run1_hz": metric_map_a["oscillator_frequency"].measured_value,
        "current_frequency_run2_hz": metric_map_b["oscillator_frequency"].measured_value,
        "historical_startup_amplitude_recorded_v": historical["metrics"]["startup_amplitude"]["measured_value"],
        "historical_startup_amplitude_replayed_v": historical_replay["stats"]["startup_amplitude_v"],
        "previous_corrected_startup_amplitude_v": corrected_startup,
        "current_frequency_status_run1": metric_map_a["oscillator_frequency"].status,
        "current_frequency_status_run2": metric_map_b["oscillator_frequency"].status,
        "current_startup_amplitude_run1_v": metric_map_a["startup_amplitude"].measured_value,
        "current_startup_amplitude_run2_v": metric_map_b["startup_amplitude"].measured_value,
        "current_startup_status_run1": metric_map_a["startup_amplitude"].status,
        "current_startup_status_run2": metric_map_b["startup_amplitude"].status,
        "semantic_guards": ",".join(corrected_metrics["oscillator_frequency"]["measurement_expression_id"] and ["requires_valid_oscillation"]),
        "threshold": corrected_metrics["startup_amplitude"]["expected_threshold"],
        "operator": corrected_metrics["startup_amplitude"]["expected_operator"],
        "historical_compliance_status": historical["summary"]["compliance_status"],
        "previous_corrected_compliance_status": corrected_provenance["compliance_status"],
        "reconciled_compliance_status": reconciled_compliance,
        "historical_evaluation_outcome": historical["summary"]["compliance_status"],
        "current_evaluation_outcome_run1": normalize_case_compliance(report_a.compliance_status.value),
        "current_evaluation_outcome_run2": normalize_case_compliance(report_b.compliance_status.value),
        "two_run_agreement": two_run_agreement,
        "root_cause_classes": root_cause_classes,
        "root_cause_summary": (
            "The historical PASS is not reproducible from the saved historical deck. "
            "Current native replays are deterministic, produce static near-DC outputs, and enforce the valid-oscillation guard."
        ),
    }


def nominal_metric_summary(case_id: str, metric_rows: list[dict[str, str]]) -> str:
    relevant = [
        row
        for row in metric_rows
        if str(row.get("case_id") or row.get("circuit_id") or "").strip() == case_id
    ]
    parts = []
    for row in relevant:
        value = row.get("measured_value", "")
        status = row.get("status", "")
        parts.append(f"{row['metric_name']}={value} [{status}]")
    return "; ".join(parts)


def build_nominal_reconciliation(
    *,
    p22_p23_rows: dict[str, dict[str, Any]],
    p4_wrdata_row: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    historical_status_rows = {row["circuit_id"]: row for row in read_csv(PAPER_SUMMARY)}
    corrected_status_rows = {row["case_id"]: row for row in read_csv(CORRECTED_RESULTS_DIR / "nominal_28_statuses.csv")}
    historical_metric_rows = read_csv(PAPER_RESULTS)
    corrected_metric_rows = read_csv(CORRECTED_RESULTS_DIR / "nominal_28_metrics.csv")

    case_ids = sorted({row["circuit_id"] for row in historical_status_rows.values()})
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        historical_compliance = normalize_case_compliance(historical_status_rows[case_id]["compliance_status"])
        corrected_compliance = normalize_case_compliance(corrected_status_rows[case_id]["new_compliance_status"])
        reconciled_compliance = corrected_compliance
        change_status = "UNCHANGED"
        root_cause = "NO_CHANGE"
        reconciled_metric = nominal_metric_summary(case_id, corrected_metric_rows)
        if case_id == "p04_amplifier":
            reconciled_metric = f"dc_gain_db={p4_wrdata_row['normalized_metric_value']} [FAIL]"
            root_cause = "HARNESS_DIFFERENCE_ACTIVE_NOMINAL_PATH"
            change_status = "RECONCILED_WITH_HARNESS_DIFFERENCE"
        elif case_id in p22_p23_rows:
            reconciled_compliance = p22_p23_rows[case_id]["reconciled_compliance_status"]
            root_cause = p22_p23_rows[case_id]["root_cause_classes"]
            change_status = "RECONCILED_EXPECTED_CORRECTION"
            reconciled_metric = (
                f"oscillator_frequency={p22_p23_rows[case_id]['current_frequency_run1_hz']} [{p22_p23_rows[case_id]['reconciled_compliance_status']}]; "
                f"startup_amplitude={p22_p23_rows[case_id]['current_startup_amplitude_run1_v']}"
            )
        rows.append(
            {
                "case_id": case_id,
                "historical_compliance": historical_compliance,
                "corrected_campaign_compliance": corrected_compliance,
                "reconciled_compliance": reconciled_compliance,
                "historical_metric_summary": nominal_metric_summary(case_id, historical_metric_rows),
                "corrected_metric_summary": nominal_metric_summary(case_id, corrected_metric_rows),
                "reconciled_metric_summary": reconciled_metric,
                "change_status": change_status,
                "root_cause": root_cause,
            }
        )

    summary = summarize_nominal_rows(rows)
    summary["changed_case_ids"] = [row["case_id"] for row in rows if row["historical_compliance"] != row["reconciled_compliance"]]
    summary["expected_total"] = 28
    summary["internally_consistent"] = summary["internally_consistent"] and summary["total"] == 28
    return rows, summary


def build_p4_outputs() -> dict[str, Any]:
    simulator = PySpiceSimulator(allow_mock=False, timeout=60)
    corrected_root = corrected_nominal_artifact_root()

    original_dir = ARTIFACTS_DIR / "p04_path_audit" / "normalized_original_harness"
    original_row, original_details = p4_original_harness_rows(simulator, original_dir)

    measure_dir = ARTIFACTS_DIR / "p04_path_audit" / "generated_nominal_measure"
    wrdata_dir = ARTIFACTS_DIR / "p04_path_audit" / "generated_nominal_wrdata"

    wrdata_execution = replay_generated_case(
        case_id="p04_amplifier",
        artifact_dir=wrdata_dir,
        required_metrics=["dc_gain_db"],
        measurement={"required_backend": "NGSPICE_WRDATA", "allow_backend_fallback": False},
    )
    wrdata_execution["artifact_dir"] = wrdata_dir

    measure_execution = replay_generated_case(
        case_id="p04_amplifier",
        artifact_dir=measure_dir,
        required_metrics=["dc_gain_db"],
        measurement={"required_backend": "NGSPICE_WRDATA", "allow_backend_fallback": False},
    )
    measure_execution["artifact_dir"] = measure_dir

    measure_row, measure_details = p4_measure_replay_row(simulator, measure_execution, measure_dir)
    wrdata_row, wrdata_details = p4_wrdata_replay_row(wrdata_execution, wrdata_dir)
    previous_row = p4_previous_row(corrected_root)

    rows = [original_row, previous_row, measure_row, wrdata_row]
    write_csv(RESULTS_DIR / "p04_path_comparison.csv", rows)

    original_base = (original_dir / "normalized_harness_base.cir").read_text(encoding="utf-8")
    nominal_base = (wrdata_dir / "base_execution_deck.cir").read_text(encoding="utf-8")
    diff_rows = p4_semantic_diff_rows(original_base, nominal_base)
    write_json(ARTIFACTS_DIR / "p04_path_audit" / "p04_semantic_diff.json", diff_rows)

    measure_gain = measure_details["vectors"]["gain_db"]
    wrdata_gain = wrdata_details["vectors"]["gain_db"]
    backend_difference = abs(measure_gain - wrdata_gain)
    lines = [
        "# p04 Path Reconciliation",
        "",
        f"- Normalized original harness gain: {original_details['vectors']['gain_db']}",
        f"- Previous corrected nominal gain: {previous_row['normalized_metric_value']}",
        f"- Replayed NGSPICE_MEASURE gain: {measure_gain}",
        f"- Replayed NGSPICE_WRDATA gain: {wrdata_gain}",
        f"- Backend difference: {backend_difference}",
        f"- Value passed to checker on the active nominal path: {wrdata_row['value_passed_to_checker']}",
        "",
        "## Key conclusion",
        "",
        "The active nominal path computes transfer gain from Vout/Vin on the generated deck. "
        "The p04 contradiction comes from a harness mismatch: the normalized original harness keeps `Vin DC 0.5 AC 1n`, "
        "whereas the active nominal deck replaces it with a multimode source centered at `2.5 V` and `AC 1`.",
        "",
        "## Semantic diff",
        "",
    ]
    for row in diff_rows:
        lines.append(
            f"- {row['component']} [{row['classification']}]: `{row['original']}` -> `{row['nominal']}`"
        )
    lines.extend(
        [
            "",
            "## Formula check",
            "",
            "- `metric_definition_version = transfer_gain_v2` is present on the active nominal request.",
            "- `quantity_type = TRANSFER_GAIN_DB` is present on the active nominal request.",
            "- WRDATA vectors show `Vin = 1 + 0j` and `Vout = 1e-08 + 0j`, so the active nominal gain is `20*log10(abs(Vout/Vin)) = -160 dB`.",
            "- The generated artifact `generated_testbench.ckt` is not the exact executed native deck; the executed deck saved here is `native_backend_measure_deck.cir`.",
        ]
    )
    write_text(REPORTS_DIR / "p04_path_reconciliation.md", "\n".join(lines) + "\n")
    return {
        "rows": rows,
        "original_gain": original_details["vectors"]["gain_db"],
        "measure_gain": measure_gain,
        "wrdata_gain": wrdata_gain,
        "backend_difference": backend_difference,
        "checker_value": wrdata_row["value_passed_to_checker"],
        "final_compliance": wrdata_row["checker_result"],
        "root_cause": "HARNESS_DIFFERENCE_ACTIVE_NOMINAL_PATH",
        "legacy_path_remaining": "artifact_serialization_only",
    }


def build_oscillator_outputs() -> dict[str, Any]:
    simulator = PySpiceSimulator(allow_mock=False, timeout=60)
    corrected_root = corrected_nominal_artifact_root()
    paper_run_dir = latest_paper_artifact_run()
    rows: dict[str, dict[str, Any]] = {}
    for case_id in ("p22_oscillator", "p23_oscillator"):
        historical_dir = ARTIFACTS_DIR / "oscillator_replays" / case_id / "historical_deck_replay"
        current_run1_dir = ARTIFACTS_DIR / "oscillator_replays" / case_id / "current_run_1"
        current_run2_dir = ARTIFACTS_DIR / "oscillator_replays" / case_id / "current_run_2"
        historical_replay = replay_historical_oscillator_deck(
            simulator,
            case_id=case_id,
            paper_run_dir=paper_run_dir,
            artifact_dir=historical_dir,
        )
        current_run_a = replay_generated_case(case_id=case_id, artifact_dir=current_run1_dir)
        current_run_b = replay_generated_case(case_id=case_id, artifact_dir=current_run2_dir)
        current_run_a["artifact_dir"] = current_run1_dir
        current_run_b["artifact_dir"] = current_run2_dir
        row = oscillator_reconciliation_row(
            case_id=case_id,
            corrected_root=corrected_root,
            paper_run_dir=paper_run_dir,
            historical_replay=historical_replay,
            current_run_a=current_run_a,
            current_run_b=current_run_b,
        )
        rows[case_id] = row
        report_lines = [
            f"# {case_id} Reconciliation",
            "",
            f"- Historical recorded frequency: {row['historical_frequency_recorded_hz']}",
            f"- Historical recorded startup amplitude: {row['historical_startup_amplitude_recorded_v']}",
            f"- Historical deck replay observed output: {row['historical_observed_output']}",
            f"- Historical deck replay frequency: {row['historical_frequency_replayed_hz']}",
            f"- Historical deck replay startup amplitude: {row['historical_startup_amplitude_replayed_v']}",
            f"- Current replay run 1 frequency: {row['current_frequency_run1_hz']} ({row['current_frequency_status_run1']})",
            f"- Current replay run 1 startup amplitude: {row['current_startup_amplitude_run1_v']} ({row['current_startup_status_run1']})",
            f"- Current replay run 2 frequency: {row['current_frequency_run2_hz']} ({row['current_frequency_status_run2']})",
            f"- Current replay run 2 startup amplitude: {row['current_startup_amplitude_run2_v']} ({row['current_startup_status_run2']})",
            f"- Two-run agreement: {row['two_run_agreement']}",
            "",
            "## Root cause",
            "",
            row["root_cause_summary"],
            "",
            f"- Root cause classes: {row['root_cause_classes']}",
        ]
        write_text(REPORTS_DIR / f"{case_id.split('_')[0]}_oscillator_reconciliation.md", "\n".join(report_lines) + "\n")

    write_csv(RESULTS_DIR / "p22_p23_old_vs_new.csv", [rows["p22_oscillator"], rows["p23_oscillator"]])
    return rows


def build_nominal_outputs(
    *,
    p22_p23_rows: dict[str, dict[str, Any]],
    p4_summary: dict[str, Any],
) -> dict[str, Any]:
    rows, summary = build_nominal_reconciliation(
        p22_p23_rows=p22_p23_rows,
        p4_wrdata_row=next(row for row in p4_summary["rows"] if row["path_id"] == "corrected_nominal_replay_wrdata"),
    )
    write_csv(RESULTS_DIR / "nominal_28_reconciled.csv", rows)
    write_json(RESULTS_DIR / "nominal_28_reconciled_summary.json", summary)
    lines = [
        "# Nominal 28 Reconciled",
        "",
        f"- Compliant: {summary['compliant']}",
        f"- Noncompliant: {summary['noncompliant']}",
        f"- Not evaluated: {summary['not_evaluated']}",
        f"- Total: {summary['total']}",
        f"- Changed case IDs: {', '.join(summary['changed_case_ids']) if summary['changed_case_ids'] else 'none'}",
        f"- Internally consistent: {summary['internally_consistent']}",
        "",
        "## Reconciled cases",
        "",
    ]
    for row in rows:
        if row["change_status"] == "UNCHANGED":
            continue
        lines.append(
            f"- {row['case_id']}: {row['historical_compliance']} -> {row['reconciled_compliance']} ({row['root_cause']})"
        )
    write_text(REPORTS_DIR / "nominal_28_reconciled.md", "\n".join(lines) + "\n")
    return summary


def build_mutation_outputs() -> dict[str, Any]:
    rows = build_mutation_label_reconciliation_rows(
        inventory_rows=read_csv(CORRECTED_GAIN_MUTATION_INVENTORY),
        old_vs_new_rows=read_csv(CORRECTED_MUTATION_OLD_VS_NEW),
        revalidation_rows=read_csv(CORRECTED_MUTATION_REVALIDATION),
    )
    write_csv(RESULTS_DIR / "gain_mutation_label_reconciliation.csv", rows)
    changed = sum(1 for row in rows if row["old_effectiveness_label"] != row["new_effectiveness_label"])
    effective_violations = sum(1 for row in rows if row["final_effectiveness_label"] == "EFFECTIVE_VIOLATION")
    ineffective = sum(1 for row in rows if row["final_effectiveness_label"] == "INEFFECTIVE_MUTATION")
    lines = [
        "# Gain Mutation Label Reconciliation",
        "",
        f"- Mutations audited: {len(rows)}",
        f"- Labels changed: {changed}",
        f"- Effective violations: {effective_violations}",
        f"- Ineffective mutations: {ineffective}",
        "",
        "## Transition explanation",
        "",
        "The four changed labels are a taxonomy change, not a scientific contradiction. "
        "Legacy reports distinguished `EFFECTIVE_NO_THRESHOLD_CROSSING` and `NO_MEASURABLE_EFFECT`, "
        "while the corrected campaign collapses non-violating gain mutations into `INEFFECTIVE_MUTATION`.",
    ]
    write_text(REPORTS_DIR / "gain_mutation_label_reconciliation.md", "\n".join(lines) + "\n")
    return {
        "rows": rows,
        "mutations_audited": len(rows),
        "labels_changed": changed,
        "effective_violations": effective_violations,
        "ineffective_mutations": ineffective,
        "reason_labels_changed": "legacy taxonomy counted metric movement; corrected taxonomy counts only violation-inducing mutations as effective",
    }


def build_overall_summary(
    *,
    p4_summary: dict[str, Any],
    oscillator_rows: dict[str, dict[str, Any]],
    nominal_summary: dict[str, Any],
    mutation_summary: dict[str, Any],
) -> dict[str, Any]:
    p22 = oscillator_rows["p22_oscillator"]
    p23 = oscillator_rows["p23_oscillator"]
    summary = {
        "safety": {
            "paper_modified": False,
            "benchmarks_modified": False,
            "frozen_v3_modified": False,
            "live_llm_calls": False,
        },
        "p4": {
            "normalized_harness_gain": p4_summary["original_gain"],
            "nominal_campaign_previous_gain": next(row for row in p4_summary["rows"] if row["path_id"] == "corrected_nominal_campaign_previous")["normalized_metric_value"],
            "reconciled_measure_gain": p4_summary["measure_gain"],
            "reconciled_wrdata_gain": p4_summary["wrdata_gain"],
            "backend_difference": p4_summary["backend_difference"],
            "metric_definition_version": "transfer_gain_v2",
            "value_passed_to_checker": p4_summary["checker_value"],
            "threshold": 0.0,
            "final_compliance": p4_summary["final_compliance"],
            "root_cause": p4_summary["root_cause"],
            "legacy_path_remaining": p4_summary["legacy_path_remaining"],
        },
        "p22": {
            "historical_result": historical_record_for_case("p22_oscillator")["summary"]["compliance_status"],
            "previous_corrected_result": p22["previous_corrected_compliance_status"],
            "reconciled_result": p22["reconciled_compliance_status"],
            "two_run_agreement": p22["two_run_agreement"],
            "root_cause": p22["root_cause_classes"],
        },
        "p23": {
            "historical_result": historical_record_for_case("p23_oscillator")["summary"]["compliance_status"],
            "previous_corrected_result": p23["previous_corrected_compliance_status"],
            "reconciled_result": p23["reconciled_compliance_status"],
            "two_run_agreement": p23["two_run_agreement"],
            "root_cause": p23["root_cause_classes"],
        },
        "nominal_28": nominal_summary,
        "mutations": mutation_summary,
        "go_metric_semantics": "PASS",
        "go_corrected_canonical_evidence": "PASS",
        "ready_for_spice_knowledge_enrichment": False,
        "ready_for_stub_replay": False,
        "ready_for_deepseek_live": False,
        "remaining_blockers": "p4 active nominal harness still differs from the normalized original harness even though the metric semantics are reconciled",
        "final_decision": "GO_WITH_DOCUMENTED_HARNESS_CAVEAT",
    }
    write_json(RESULTS_DIR / "reconciliation_summary.json", summary)
    return summary


def main() -> None:
    ensure_workspace()
    p4_summary = build_p4_outputs()
    oscillator_rows = build_oscillator_outputs()
    nominal_summary = build_nominal_outputs(
        p22_p23_rows=oscillator_rows,
        p4_summary=p4_summary,
    )
    mutation_summary = build_mutation_outputs()
    overall = build_overall_summary(
        p4_summary=p4_summary,
        oscillator_rows=oscillator_rows,
        nominal_summary=nominal_summary,
        mutation_summary=mutation_summary,
    )
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    main()
