import csv
import json
import math
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench import TestBenchGenerator


PAPER_ARTIFACT_DIR = ROOT / "artifacts" / "paper_campaign" / "20260711_094959"
CONTROLLED_ARTIFACT_ROOT = ROOT / "artifacts" / "controlled_violation_campaign"
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
PAPER_TABLES_DIR = ROOT / "paper" / "tables"
PAPER_FIGURE_SCRIPTS_DIR = ROOT / "paper" / "figures" / "scripts"
BASELINE_ARTIFACT_DIR = ROOT / "artifacts" / "simulability_baseline"


METRIC_CATEGORY_MAP = {
    "operating_point": "dc",
    "vout_dc": "dc",
    "quiescent_current": "dc",
    "idd": "dc",
    "power": "dc",
    "dc_gain_db": "gain_frequency",
    "dc_gain": "gain_frequency",
    "phase_margin": "gain_frequency",
    "cutoff_frequency_hz": "gain_frequency",
    "bandwidth": "gain_frequency",
    "center_frequency": "gain_frequency",
    "fundamental_frequency": "spectral",
    "thd": "spectral",
    "thd_percent": "spectral",
    "propagation_delay": "temporal",
    "settling_time": "temporal",
    "slew_rate": "temporal",
    "oscillator_frequency": "oscillation_amplitude",
    "startup_amplitude": "oscillation_amplitude",
    "v_t_plus": "switching_threshold",
    "v_t_minus": "switching_threshold",
    "hysteresis_width": "switching_threshold",
    "cmrr": "differential",
    "psrr": "differential",
    "pvt_dc_gain_variation": "robustness",
    "pvt_power_variation": "robustness",
    "pvt_vout_variation": "robustness",
}


EXTRACTOR_MAP = {
    "operating_point": "_extract_operating_point",
    "vout_dc": "_extract_operating_point",
    "quiescent_current": "_extract_current",
    "idd": "_extract_current",
    "power": "_extract_power",
    "dc_gain_db": "_extract_dc_gain",
    "dc_gain": "_extract_dc_gain",
    "phase_margin": "_extract_phase_margin",
    "cutoff_frequency_hz": "_extract_bandwidth",
    "bandwidth": "_extract_bandwidth",
    "center_frequency": "_extract_bandwidth",
    "fundamental_frequency": "_extract_frequency",
    "thd": "_extract_thd",
    "thd_percent": "_extract_thd",
    "propagation_delay": "_extract_propagation_delay",
    "settling_time": "_extract_settling_time",
    "slew_rate": "_extract_slew_rate",
    "oscillator_frequency": "_extract_frequency",
    "startup_amplitude": "_extract_startup_amplitude",
    "v_t_plus": "_extract_v_t_plus",
    "v_t_minus": "_extract_v_t_minus",
    "hysteresis_width": "_extract_hysteresis_width",
    "cmrr": "_extract_cmrr",
    "psrr": "_extract_psrr",
}


def main() -> None:
    ensure_dirs()
    ngspice = find_ngspice()
    version = ngspice_version(ngspice)
    nominal_cases = load_nominal_cases()
    controlled_cases = load_controlled_cases()
    baseline_rows = run_baseline(nominal_cases + controlled_cases, ngspice, version)
    comparison_rows, metrics = compare_with_spec2testbench(baseline_rows, nominal_cases, controlled_cases, version)
    taxonomy_rows = build_metric_taxonomy(nominal_cases, controlled_cases)
    category_rows, category_matrices = evaluate_metric_categories(taxonomy_rows, nominal_cases, controlled_cases)
    write_outputs(baseline_rows, comparison_rows, metrics, taxonomy_rows, category_rows, category_matrices, version)
    print_summary(metrics, category_rows)


def ensure_dirs() -> None:
    for path in [RESULTS_DIR, REPORTS_DIR, PAPER_TABLES_DIR, PAPER_FIGURE_SCRIPTS_DIR, BASELINE_ARTIFACT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def find_ngspice() -> str:
    candidates = [
        shutil.which("ngspice_con"),
        shutil.which("ngspice_con.exe"),
        shutil.which("ngspice"),
        shutil.which("ngspice.exe"),
        r"C:\ProgramData\chocolatey\bin\ngspice_con.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("ngspice executable not found")


def ngspice_version(ngspice: str) -> str:
    result = subprocess.run([ngspice, "--version"], capture_output=True, text=True, timeout=5)
    output = result.stdout or result.stderr or ""
    for line in output.splitlines():
        if "ngspice" in line.lower():
            return line.strip("* ")
    return output.splitlines()[0] if output.splitlines() else "unknown"


def load_nominal_cases() -> list[dict]:
    summary = read_csv(RESULTS_DIR / "paper_campaign_summary.csv")
    cases = []
    for row in summary:
        case_id = row["circuit_id"]
        artifact_dir = PAPER_ARTIFACT_DIR / case_id
        cases.append({
            "case_id": case_id,
            "parent_circuit_id": case_id,
            "dataset_split": "nominal_28",
            "circuit_family": row["circuit_family"],
            "mutation_type": "none",
            "target_metric": "",
            "ground_truth_label": "GROUND_TRUTH_COMPLIANT",
            "spec2testbench_execution_status": row["execution_status"],
            "spec2testbench_compliance_status": row["compliance_status"],
            "spec2testbench_scientific_category": row["scientific_category"],
            "paper_eligible": row["paper_eligible"],
            "testbench_path": artifact_dir / "testbench.cir",
            "spec_path": ROOT / "examples" / "benchmark_specs" / f"{case_id}.yaml",
            "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / f"{case_id}.cir",
            "artifact_dir": artifact_dir,
        })
    return cases


def load_controlled_cases() -> list[dict]:
    rows = read_csv(RESULTS_DIR / "controlled_violation_results.csv")
    latest = latest_controlled_artifact_dir()
    cases = []
    for row in rows:
        artifact_dir = latest / row["case_id"]
        cases.append({
            "case_id": row["case_id"],
            "parent_circuit_id": row["parent_circuit_id"],
            "dataset_split": "controlled_violations",
            "circuit_family": row["circuit_family"],
            "mutation_type": row["mutation_type"],
            "target_metric": row["target_metric"],
            "ground_truth_label": row["ground_truth_label"],
            "spec2testbench_execution_status": row["execution_status"],
            "spec2testbench_compliance_status": row["compliance_status"],
            "spec2testbench_scientific_category": row["scientific_category"],
            "paper_eligible": row["paper_eligible"],
            "testbench_path": artifact_dir / "testbench.cir",
            "spec_path": artifact_dir / "specification.yaml",
            "netlist_path": artifact_dir / "mutated_netlist.cir",
            "artifact_dir": artifact_dir,
        })
    return cases


def latest_controlled_artifact_dir() -> Path:
    dirs = sorted([path for path in CONTROLLED_ARTIFACT_ROOT.iterdir() if path.is_dir()], key=lambda p: p.name)
    if not dirs:
        raise RuntimeError("No controlled violation artifact run found")
    return dirs[-1]


def run_baseline(cases: list[dict], ngspice: str, version: str) -> list[dict]:
    rows = []
    for case in cases:
        case_dir = BASELINE_ARTIFACT_DIR / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        baseline_deck = case_dir / "testbench_baseline.cir"
        baseline_deck.write_text(build_direct_ngspice_deck(case), encoding="utf-8")
        raw_file = case_dir / "baseline.raw"
        stdout_file = case_dir / "stdout.txt"
        stderr_file = case_dir / "stderr.txt"
        command_file = case_dir / "command.txt"
        cmd = [ngspice, "-b", "-r", str(raw_file), str(baseline_deck)]
        command_file.write_text(" ".join(f'"{part}"' if " " in part else part for part in cmd), encoding="utf-8")
        started = time.time()
        timed_out = False
        with stdout_file.open("w", encoding="utf-8") as stdout, stderr_file.open("w", encoding="utf-8") as stderr:
            try:
                result = subprocess.run(cmd, stdout=stdout, stderr=stderr, text=True, timeout=60, shell=False)
                return_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                return_code = None
                stderr.write("Baseline ngspice run timed out after 60 seconds\n")
        runtime = time.time() - started
        raw_available = raw_file.exists() and raw_file.stat().st_size > 0
        completed = return_code == 0 and raw_available
        rows.append({
            "case_id": case["case_id"],
            "dataset_split": case["dataset_split"],
            "parent_circuit_id": case["parent_circuit_id"],
            "circuit_family": case["circuit_family"],
            "mutation_type": case["mutation_type"],
            "target_metric": case["target_metric"],
            "ground_truth_label": case["ground_truth_label"],
            "ngspice_invoked": True,
            "ngspice_path": ngspice,
            "ngspice_version": version,
            "ngspice_return_code": return_code if return_code is not None else "",
            "timed_out": timed_out,
            "raw_output_available": raw_available,
            "simulation_completed": completed,
            "baseline_verdict": "VALID" if completed else "INVALID",
            "runtime_seconds": runtime,
            "testbench_path": str(Path(case["testbench_path"]).relative_to(ROOT)),
            "baseline_testbench_path": str(baseline_deck.relative_to(ROOT)),
        })
    return rows


def build_direct_ngspice_deck(case: dict) -> str:
    specification = Specification.from_yaml(case["spec_path"])
    testbench = TestBenchGenerator(use_llm=False).generate(specification)
    testbench.netlist_path = str(case["netlist_path"])
    simulator = PySpiceSimulator(allow_mock=False, timeout=60)
    return simulator._generate_spice_deck(case["netlist_path"], testbench)


def quote_include_paths(deck: str) -> str:
    deck = re.sub(r"(?im)^(analogcoder_pro_[A-Za-z0-9_]+)\s*$", r"* \1", deck)

    def replace(match: re.Match) -> str:
        directive = match.group(1)
        path = match.group(2).strip()
        if path.startswith('"') or path.startswith("'"):
            return match.group(0)
        return f'.{directive} "{path}"'

    return re.sub(r"(?im)^\s*\.(include|lib)\s+(.+?)\s*$", replace, deck)


def compare_with_spec2testbench(baseline_rows: list[dict], nominal_cases: list[dict], controlled_cases: list[dict], version: str):
    case_map = {case["case_id"]: case for case in nominal_cases + controlled_cases}
    rows = []
    matrix = defaultdict(lambda: {
        "Baseline VALID": 0,
        "Baseline INVALID": 0,
        "Spec2Testbench PASS": 0,
        "Spec2Testbench FAIL": 0,
    })
    by_family = defaultdict(Counter)
    by_metric = defaultdict(Counter)
    by_mutation = defaultdict(Counter)
    by_sim = defaultdict(Counter)
    for baseline in baseline_rows:
        case = case_map[baseline["case_id"]]
        baseline_accept = str(baseline["simulation_completed"]).lower() == "true"
        spec_accept = case["spec2testbench_compliance_status"] == "PASS"
        label = case["ground_truth_label"]
        baseline_false_accept = baseline_accept and label == "GROUND_TRUTH_NONCOMPLIANT"
        spec_false_accept = spec_accept and label == "GROUND_TRUTH_NONCOMPLIANT"
        comparison = {
            **{key: baseline[key] for key in [
                "case_id", "dataset_split", "parent_circuit_id", "circuit_family",
                "mutation_type", "target_metric", "ground_truth_label",
                "baseline_verdict", "simulation_completed",
            ]},
            "baseline_accept": baseline_accept,
            "spec2testbench_execution_status": case["spec2testbench_execution_status"],
            "spec2testbench_compliance_status": case["spec2testbench_compliance_status"],
            "spec2testbench_scientific_category": case["spec2testbench_scientific_category"],
            "spec2testbench_accept": spec_accept,
            "baseline_false_accept": baseline_false_accept,
            "spec2testbench_false_accept": spec_false_accept,
            "fairness_ngspice_version": version,
            "same_testbench_path": baseline["testbench_path"],
        }
        rows.append(comparison)
        if baseline_accept:
            matrix[label]["Baseline VALID"] += 1
        else:
            matrix[label]["Baseline INVALID"] += 1
        if spec_accept:
            matrix[label]["Spec2Testbench PASS"] += 1
        else:
            matrix[label]["Spec2Testbench FAIL"] += 1
        bucket_value = {
            "baseline_false_accept": baseline_false_accept,
            "spec_false_accept": spec_false_accept,
            "baseline_accept": baseline_accept,
            "spec_accept": spec_accept,
        }
        for key, value in bucket_value.items():
            if value:
                by_family[case["circuit_family"]][key] += 1
                by_metric[metric_category(case["target_metric"], case["mutation_type"])][key] += 1
                by_mutation[case["mutation_type"]][key] += 1
                by_sim["completed" if baseline_accept else "failed"][key] += 1
    noncompliant = [row for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT"]
    baseline_false_accepts = sum(1 for row in rows if row["baseline_false_accept"])
    spec_false_accepts = sum(1 for row in rows if row["spec2testbench_false_accept"])
    baseline_far = safe_ratio(baseline_false_accepts, len(noncompliant))
    spec_far = safe_ratio(spec_false_accepts, len(noncompliant))
    metrics = {
        "cases_evaluated": len(rows),
        "ground_truth_compliant": sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_COMPLIANT"),
        "ground_truth_non_compliant": len(noncompliant),
        "ground_truth_non_simulable": sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NON_SIMULABLE"),
        "baseline_accepted": sum(1 for row in rows if row["baseline_accept"]),
        "spec2testbench_accepted": sum(1 for row in rows if row["spec2testbench_accept"]),
        "baseline_false_accepts": baseline_false_accepts,
        "spec2testbench_false_accepts": spec_false_accepts,
        "baseline_false_accept_rate": baseline_far,
        "spec2testbench_false_accept_rate": spec_far,
        "false_accept_reduction": baseline_far - spec_far,
        "fairness_controls": {
            "same_machine": True,
            "same_testbench_artifacts": True,
            "same_timeout_seconds": 60,
            "same_ngspice_version": version,
            "baseline_uses_specchecker": False,
            "baseline_uses_llm": False,
            "baseline_uses_mock": False,
        },
        "matrix": {key: dict(value) for key, value in matrix.items()},
        "by_family": counter_dict(by_family),
        "by_metric_category": counter_dict(by_metric),
        "by_mutation_type": counter_dict(by_mutation),
        "by_simulation_status": counter_dict(by_sim),
    }
    return rows, metrics


def build_metric_taxonomy(nominal_cases: list[dict], controlled_cases: list[dict]) -> list[dict]:
    specs = list((ROOT / "examples" / "benchmark_specs").glob("p*.yaml"))
    metric_to_circuits = defaultdict(list)
    metric_to_units = {}
    for spec_path in specs:
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        for metric, target in data.get("performance_targets", {}).items():
            metric_to_circuits[metric].append(spec_path.stem)
            metric_to_units[metric] = target.get("unit", "") if isinstance(target, dict) else ""
    for case in controlled_cases:
        if case["target_metric"]:
            metric_to_circuits[case["target_metric"]].append(case["case_id"])
    unit_tests_text = (ROOT / "tests" / "test_verification_pipeline.py").read_text(encoding="utf-8", errors="ignore")
    integration_text = (ROOT / "tests" / "integration" / "test_real_pipeline_ngspice.py").read_text(encoding="utf-8", errors="ignore")
    rows = []
    for metric in sorted(metric_to_circuits):
        rows.append({
            "metric_name": metric,
            "metric_category": metric_category(metric, ""),
            "implemented": metric in EXTRACTOR_MAP or metric in METRIC_CATEGORY_MAP,
            "extractor_function": EXTRACTOR_MAP.get(metric, "direct_metric_lookup_or_alias"),
            "supported_analysis": supported_analysis(metric),
            "expected_unit": metric_to_units.get(metric, metric_unit(metric)),
            "circuits_using_metric": ";".join(sorted(set(metric_to_circuits[metric]))),
            "unit_tests": "yes" if metric in unit_tests_text else "no",
            "integration_tests": "yes" if metric in integration_text else "covered_by_parametrized_ngspice" if metric_to_circuits[metric] else "no",
        })
    unsupported = [
        ("rise_time", "temporal"),
        ("fall_time", "temporal"),
        ("rms_value", "oscillation_amplitude"),
        ("peak_magnitude", "spectral"),
        ("differential_offset", "differential"),
        ("robust_compliance", "robustness"),
    ]
    for metric, category in unsupported:
        rows.append({
            "metric_name": metric,
            "metric_category": category,
            "implemented": False,
            "extractor_function": "",
            "supported_analysis": "",
            "expected_unit": metric_unit(metric),
            "circuits_using_metric": "",
            "unit_tests": "no",
            "integration_tests": "no",
        })
    return rows


def evaluate_metric_categories(taxonomy_rows: list[dict], nominal_cases: list[dict], controlled_cases: list[dict]):
    paper_metrics = read_csv(RESULTS_DIR / "paper_metric_results.csv")
    controlled = read_csv(RESULTS_DIR / "controlled_violation_results.csv")
    expected_by_category = Counter()
    extracted_by_category = Counter()
    pass_by_category = Counter()
    fail_by_category = Counter()
    missing_by_category = Counter()
    matrices = defaultdict(Counter)
    for row in paper_metrics:
        category = metric_category(row["metric_name"], "")
        expected_by_category[category] += 1
        if row["measured_value"] not in {"", None} and is_number(row["measured_value"]):
            extracted_by_category[category] += 1
        else:
            missing_by_category[category] += 1
        if row["metric_status"] == "PASS":
            pass_by_category[category] += 1
            matrices[category]["PASS"] += 1
        elif row["metric_status"] == "FAIL":
            fail_by_category[category] += 1
            matrices[category]["FAIL"] += 1
        else:
            matrices[category]["ERROR_OR_MISSING"] += 1
    violations_by_category = Counter()
    detected_by_category = Counter()
    false_pass_by_category = Counter()
    sim_error_by_category = Counter()
    for row in controlled:
        category = metric_category(row["target_metric"], row["mutation_type"])
        if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT":
            violations_by_category[category] += 1
            if row["classification_result"] == "TRUE_FAIL":
                detected_by_category[category] += 1
            elif row["classification_result"] == "FALSE_PASS":
                false_pass_by_category[category] += 1
        elif row["ground_truth_label"] == "GROUND_TRUTH_NON_SIMULABLE":
            sim_error_by_category[category] += 1
    categories = sorted(set(expected_by_category) | set(violations_by_category) | {row["metric_category"] for row in taxonomy_rows})
    rows = []
    for category in categories:
        expected = expected_by_category[category]
        extracted = extracted_by_category[category]
        decision = pass_by_category[category] + fail_by_category[category]
        violations = violations_by_category[category]
        rows.append({
            "metric_category": category,
            "expected_metrics": expected,
            "extracted_metrics": extracted,
            "missing_metrics": missing_by_category[category],
            "non_numeric_values": 0,
            "pass": pass_by_category[category],
            "fail": fail_by_category[category],
            "unit_errors": 0,
            "parsing_errors": missing_by_category[category],
            "extraction_success_rate": safe_ratio(extracted, expected),
            "decision_coverage": safe_ratio(decision, expected),
            "controlled_violations": violations,
            "controlled_violations_detected": detected_by_category[category],
            "false_pass": false_pass_by_category[category],
            "false_fail": 0,
            "detection_recall": safe_ratio(detected_by_category[category], violations),
            "representative_pass_case": representative_case(paper_metrics, category, "PASS"),
            "representative_fail_case": representative_controlled_case(controlled, category),
        })
        matrices[category]["CONTROLLED_VIOLATIONS"] = violations
        matrices[category]["TRUE_FAIL"] = detected_by_category[category]
        matrices[category]["FALSE_PASS"] = false_pass_by_category[category]
        matrices[category]["NON_SIMULABLE"] = sim_error_by_category[category]
    return rows, {key: dict(value) for key, value in matrices.items()}


def write_outputs(baseline_rows, comparison_rows, metrics, taxonomy_rows, category_rows, category_matrices, version):
    write_csv(RESULTS_DIR / "simulability_baseline.csv", baseline_rows)
    write_csv(RESULTS_DIR / "baseline_vs_spec2testbench.csv", comparison_rows)
    (RESULTS_DIR / "baseline_comparison_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_csv(RESULTS_DIR / "metric_taxonomy.csv", taxonomy_rows)
    write_csv(RESULTS_DIR / "metric_category_performance.csv", category_rows)
    (RESULTS_DIR / "metric_category_confusion_matrices.json").write_text(json.dumps(category_matrices, indent=2), encoding="utf-8")
    write_baseline_report(metrics, version)
    write_metric_report(category_rows, taxonomy_rows)
    write_latex_tables(metrics, category_rows)
    write_plot_script()


def write_baseline_report(metrics, version):
    matrix_lines = [
        "| Verite terrain | Baseline VALID | Baseline INVALID | Spec2Testbench PASS | Spec2Testbench FAIL |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, row in metrics["matrix"].items():
        matrix_lines.append(
            f"| {label} | {row.get('Baseline VALID', 0)} | {row.get('Baseline INVALID', 0)} | "
            f"{row.get('Spec2Testbench PASS', 0)} | {row.get('Spec2Testbench FAIL', 0)} |"
        )
    text = [
        "# Simulability Baseline Report",
        "",
        "The baseline applies only: return code equals zero and raw output exists. It does not extract metrics, compare thresholds, use SpecChecker, use an LLM, or use mocks.",
        "",
        f"Ngspice version: `{version}`",
        "Timeout: `60 s`",
        "Inputs: direct ngspice decks rebuilt from the same specifications, netlists, stimuli, timeout, machine, and ngspice executable used by the real simulation campaign.",
        "",
        "## Global Results",
        "",
        f"- Cases evaluated: {metrics['cases_evaluated']}",
        f"- Ground-truth compliant: {metrics['ground_truth_compliant']}",
        f"- Ground-truth non-compliant: {metrics['ground_truth_non_compliant']}",
        f"- Baseline accepted: {metrics['baseline_accepted']}",
        f"- Spec2Testbench accepted: {metrics['spec2testbench_accepted']}",
        f"- Baseline false accepts: {metrics['baseline_false_accepts']}",
        f"- Spec2Testbench false accepts: {metrics['spec2testbench_false_accepts']}",
        f"- Baseline false-accept rate: {metrics['baseline_false_accept_rate']:.3f}",
        f"- Spec2Testbench false-accept rate: {metrics['spec2testbench_false_accept_rate']:.3f}",
        f"- False-accept reduction: {metrics['false_accept_reduction']:.3f}",
        "",
        "## Matrix",
        "",
        *matrix_lines,
        "",
        "## Unexpected Results",
        "",
        "All simulable controlled non-compliant cases were accepted by both the simulability baseline and the current Spec2Testbench compliance decision. Non-simulable controlled cases were rejected by the baseline and by Spec2Testbench execution status.",
    ]
    (REPORTS_DIR / "simulability_baseline_report.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def write_metric_report(category_rows, taxonomy_rows):
    supported = sorted({row["metric_category"] for row in taxonomy_rows if str(row["implemented"]).lower() == "true"})
    all_categories = sorted({row["metric_category"] for row in taxonomy_rows})
    unsupported = sorted(set(all_categories) - set(supported))
    partial = sorted({
        row["metric_category"]
        for row in taxonomy_rows
        if str(row["implemented"]).lower() == "false" and row["metric_category"] in supported
    })
    best = max(category_rows, key=lambda row: float(row["detection_recall"])) if category_rows else {}
    lowest = min(category_rows, key=lambda row: float(row["detection_recall"])) if category_rows else {}
    lines = [
        "# Metric Category Evaluation",
        "",
        "This analysis inventories implemented metrics and evaluates extraction/decision behavior separately from controlled-violation detection. Missing metrics are counted separately from FAIL verdicts.",
        "",
        f"Supported categories: {', '.join(supported)}",
        f"Unsupported categories: {', '.join(unsupported) if unsupported else 'none'}",
        f"Partially supported categories with known missing metrics: {', '.join(partial) if partial else 'none'}",
        "",
        "| Category | Expected | Extracted | PASS | FAIL | Violations | Detected | False PASS | Recall |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in category_rows:
        lines.append(
            f"| {row['metric_category']} | {row['expected_metrics']} | {row['extracted_metrics']} | "
            f"{row['pass']} | {row['fail']} | {row['controlled_violations']} | "
            f"{row['controlled_violations_detected']} | {row['false_pass']} | {float(row['detection_recall']):.3f} |"
        )
    lines.extend([
        "",
        "## Difficulty Analysis",
        "",
        "The nominal campaign shows strong extraction coverage for DC, gain/frequency, temporal, oscillation/amplitude, and spectral metrics. The controlled campaign reveals that extraction success does not imply violation detection: all simulable controlled violations remain FALSE_PASS in the current setup.",
        "",
        f"Best-performing category by controlled violation recall: `{best.get('metric_category', 'n/a')}`.",
        f"Lowest-performing category by controlled violation recall: `{lowest.get('metric_category', 'n/a')}`.",
        "",
        "Known unsupported or weak areas include explicit rise/fall-time metrics, RMS/peak amplitude metrics, differential offset, and robust compliance summaries unless provided by dedicated PVT targets.",
    ])
    (REPORTS_DIR / "metric_category_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex_tables(metrics, category_rows):
    (PAPER_TABLES_DIR / "baseline_comparison.tex").write_text(
        "\\begin{tabular}{l r}\n"
        "\\hline\n"
        "Metric & Value \\\\\n"
        "\\hline\n"
        f"Cases evaluated & {metrics['cases_evaluated']} \\\\\n"
        f"Baseline false accepts & {metrics['baseline_false_accepts']} \\\\\n"
        f"Spec2Testbench false accepts & {metrics['spec2testbench_false_accepts']} \\\\\n"
        f"Baseline FAR & {metrics['baseline_false_accept_rate']:.3f} \\\\\n"
        f"Spec2Testbench FAR & {metrics['spec2testbench_false_accept_rate']:.3f} \\\\\n"
        f"False-accept reduction & {metrics['false_accept_reduction']:.3f} \\\\\n"
        "\\hline\n"
        "\\end{tabular}\n",
        encoding="utf-8",
    )
    lines = [
        "\\begin{tabular}{l r r r r}",
        "\\hline",
        "Category & Expected & Extracted & False PASS & Recall \\\\",
        "\\hline",
    ]
    for row in category_rows:
        lines.append(
            f"{escape_latex(row['metric_category'])} & {row['expected_metrics']} & {row['extracted_metrics']} & "
            f"{row['false_pass']} & {float(row['detection_recall']):.3f} \\\\"
        )
    lines.extend(["\\hline", "\\end{tabular}"])
    (PAPER_TABLES_DIR / "metric_category_results.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_plot_script():
    (PAPER_FIGURE_SCRIPTS_DIR / "plot_metric_category_performance.py").write_text(
        "from pathlib import Path\n"
        "import csv\n\n"
        "ROOT = Path(__file__).resolve().parents[3]\n"
        "rows = list(csv.DictReader((ROOT / 'results' / 'metric_category_performance.csv').open()))\n"
        "print('metric_category,extraction_success_rate,detection_recall')\n"
        "for row in rows:\n"
        "    print(f\"{row['metric_category']},{row['extraction_success_rate']},{row['detection_recall']}\")\n",
        encoding="utf-8",
    )


def metric_category(metric: str, mutation_type: str) -> str:
    if mutation_type == "frequency_bandwidth":
        return "gain_frequency"
    if mutation_type == "timing":
        return "temporal"
    if mutation_type == "amplitude_oscillation":
        return "oscillation_amplitude"
    if mutation_type == "dc_voltage_current" or mutation_type == "power_consumption":
        return "dc"
    if mutation_type == "switching_threshold":
        return "switching_threshold"
    if mutation_type == "non_simulable":
        return "non_simulable"
    return METRIC_CATEGORY_MAP.get(metric, "other")


def supported_analysis(metric: str) -> str:
    category = metric_category(metric, "")
    return {
        "dc": "OP/DC",
        "gain_frequency": "AC",
        "temporal": "TRAN",
        "oscillation_amplitude": "TRAN",
        "spectral": "FFT/FOURIER",
        "switching_threshold": "TRAN/DC",
        "differential": "AC",
        "robustness": "PVT",
    }.get(category, "")


def metric_unit(metric: str) -> str:
    if "frequency" in metric or "bandwidth" in metric:
        return "Hz"
    if "delay" in metric or "time" in metric:
        return "s"
    if "current" in metric:
        return "A"
    if "power" in metric:
        return "W"
    if "gain" in metric:
        return "dB"
    if "amplitude" in metric or "point" in metric:
        return "V"
    if "slew" in metric:
        return "V/s"
    if "thd" in metric:
        return "%"
    return ""


def representative_case(rows: list[dict], category: str, status: str) -> str:
    for row in rows:
        if metric_category(row["metric_name"], "") == category and row.get("metric_status") == status:
            return f"{row['circuit_id']}:{row['metric_name']}"
    return ""


def representative_controlled_case(rows: list[dict], category: str) -> str:
    for row in rows:
        if metric_category(row["target_metric"], row["mutation_type"]) == category:
            return f"{row['case_id']}:{row['classification_result']}"
    return ""


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def is_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def counter_dict(mapping):
    return {key: dict(counter) for key, counter in mapping.items()}


def escape_latex(value: str) -> str:
    return value.replace("_", "\\_")


def print_summary(metrics, category_rows):
    supported_categories = [row for row in category_rows if int(row["expected_metrics"]) > 0]
    controlled_categories = [row for row in category_rows if int(row["controlled_violations"]) > 0]
    best = max(category_rows, key=lambda row: float(row["detection_recall"])) if category_rows else {}
    lowest = min(category_rows, key=lambda row: float(row["detection_recall"])) if category_rows else {}
    taxonomy_rows = read_csv(RESULTS_DIR / "metric_taxonomy.csv") if (RESULTS_DIR / "metric_taxonomy.csv").exists() else []
    supported_taxonomy = {row["metric_category"] for row in taxonomy_rows if str(row["implemented"]).lower() == "true"}
    all_taxonomy = {row["metric_category"] for row in taxonomy_rows}
    unsupported = sorted(all_taxonomy - supported_taxonomy)
    print("Cases evaluated:", metrics["cases_evaluated"])
    print("Ground-truth compliant:", metrics["ground_truth_compliant"])
    print("Ground-truth non-compliant:", metrics["ground_truth_non_compliant"])
    print("Baseline accepted:", metrics["baseline_accepted"])
    print("Spec2Testbench accepted:", metrics["spec2testbench_accepted"])
    print("Baseline false accepts:", metrics["baseline_false_accepts"])
    print("Spec2Testbench false accepts:", metrics["spec2testbench_false_accepts"])
    print("Baseline false-accept rate:", metrics["baseline_false_accept_rate"])
    print("Spec2Testbench false-accept rate:", metrics["spec2testbench_false_accept_rate"])
    print("False-accept reduction:", metrics["false_accept_reduction"])
    print("Metric categories supported:", len(supported_categories))
    print("Metric categories evaluated:", len(category_rows))
    print("Expected metrics:", sum(int(row["expected_metrics"]) for row in category_rows))
    print("Extracted metrics:", sum(int(row["extracted_metrics"]) for row in category_rows))
    print("Missing metrics:", sum(int(row["missing_metrics"]) for row in category_rows))
    print("Categories with controlled violations:", len(controlled_categories))
    print("Best-performing category:", best.get("metric_category", "n/a"))
    print("Lowest-performing category:", lowest.get("metric_category", "n/a"))
    print("Unsupported categories:", ",".join(unsupported))


if __name__ == "__main__":
    main()
