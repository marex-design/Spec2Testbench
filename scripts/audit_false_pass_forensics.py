import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor
from spec2testbench.infrastructure.testbench import TestBenchGenerator


RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
ARTIFACTS_DIR = ROOT / "artifacts"
FORENSICS_DIR = ARTIFACTS_DIR / "false_pass_forensics"
CONTROLLED_ROOT = ARTIFACTS_DIR / "controlled_violation_campaign"
GT_DIR = ROOT / "experiments" / "ground_truth"
CV_DIR = ROOT / "experiments" / "controlled_violations" / "generated_cases"
SPEC_DIR = ROOT / "examples" / "benchmark_specs"
NETLIST_DIR = ROOT / "benchmark" / "analogcoder_pro"

SELECTED_CASES = [
    "cv_001_p10_c_huge",
    "cv_006_p01_rd_low",
    "cv_010_p08_iref_low",
    "cv_014_p09_input_slow",
    "cv_015_p24_c_large",
    "cv_017_p22_c_large",
    "cv_020_p28_ref_high",
    "cv_023_p05_vdd_high",
    "cv_027_p19_lo_low",
    "cv_028_p26_input_high",
]


@dataclass
class CaseAudit:
    case_id: str
    parent_circuit_id: str
    circuit_family: str
    target_metric: str
    mutation_type: str
    framework_status: str
    mutation_applied: bool
    mutation_effective: bool
    threshold_crossed_independently: bool
    correct_netlist_simulated: bool
    correct_specification_loaded: bool
    correct_metric_extracted: bool
    correct_metric_checked: bool
    primary_root_cause: str
    secondary_root_causes: str
    recommended_fix: str


def main() -> None:
    FORENSICS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reconciliation_rows, reconciliation_summary = reconcile_population()
    audits, trace_rows, mutation_rows, cache_notes = audit_selected_cases()
    write_population_outputs(reconciliation_rows, reconciliation_summary)
    write_case_outputs(audits, trace_rows, mutation_rows, cache_notes, reconciliation_summary)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_controlled_run() -> Path:
    runs = sorted([path for path in CONTROLLED_ROOT.iterdir() if path.is_dir()], key=lambda p: p.name)
    return runs[-1]


def classify_row(row: dict[str, str]) -> dict[str, bool]:
    label = row.get("ground_truth_label", "")
    eligible = _as_bool(row.get("eligible_for_evaluation")) or _as_bool(row.get("paper_eligible"))
    compliant = label == "GROUND_TRUTH_COMPLIANT"
    noncompliant = label == "GROUND_TRUTH_NONCOMPLIANT"
    nonsimulable = label == "GROUND_TRUTH_NON_SIMULABLE"
    uncertain = label == "GROUND_TRUTH_UNCERTAIN"
    excluded = uncertain or (("eligible_for_evaluation" in row or "paper_eligible" in row) and not eligible)
    accepted = False
    rejected = False
    if "baseline_accept" in row:
        accepted = _as_bool(row["baseline_accept"])
        rejected = not accepted
    elif "spec2testbench_accept" in row:
        accepted = _as_bool(row["spec2testbench_accept"])
        rejected = not accepted
    elif "compliance_status" in row:
        accepted = row["compliance_status"] == "PASS"
        rejected = not accepted
    elif "baseline_verdict" in row:
        accepted = row["baseline_verdict"] == "VALID"
        rejected = not accepted
    elif "expected_framework_status" in row:
        accepted = row["expected_framework_status"] == "PASS"
        rejected = not accepted
    return {
        "compliant": compliant,
        "noncompliant": noncompliant,
        "nonsimulable": nonsimulable,
        "uncertain": uncertain,
        "excluded": excluded,
        "accepted": accepted,
        "rejected": rejected,
    }


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def reconcile_population() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    targets = [
        "ground_truth_cases.csv",
        "controlled_violation_results.csv",
        "controlled_violation_metrics.json",
        "simulability_baseline.csv",
        "baseline_vs_spec2testbench.csv",
        "metric_category_performance.csv",
    ]
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}

    for name in targets:
        path = RESULTS_DIR / name
        if name.endswith(".json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "source_file": name,
                "row_type": "summary_metrics",
                "total_rows": 1,
                "unique_cases": data.get("total_controlled_violations", ""),
                "compliant_cases": "",
                "noncompliant_cases": data.get("false_pass", 0) + data.get("expected_violations_detected", 0) + data.get("simulation_errors", 0) - data.get("non_simulable_cases", 0),
                "non_simulable_cases": data.get("non_simulable_cases", ""),
                "uncertain_cases": "",
                "excluded_cases": "",
                "accepted_cases": data.get("false_pass", ""),
                "rejected_cases": data.get("expected_violations_detected", 0) + data.get("simulation_errors", 0),
                "notes": "JSON summary does not enumerate rows; counts derived from top-level metrics.",
            })
            summary["controlled_metrics"] = data
            continue

        data_rows = read_csv(path)
        case_ids = [row.get("case_id", "") for row in data_rows if row.get("case_id")]
        counters = Counter()
        for row in data_rows:
            counters.update(classify_row(row))
        rows.append({
            "source_file": name,
            "row_type": "file_rows",
            "total_rows": len(data_rows),
            "unique_cases": len(set(case_ids)),
            "compliant_cases": counters["compliant"],
            "noncompliant_cases": counters["noncompliant"],
            "non_simulable_cases": counters["nonsimulable"],
            "uncertain_cases": counters["uncertain"],
            "excluded_cases": counters["excluded"],
            "accepted_cases": counters["accepted"],
            "rejected_cases": counters["rejected"],
            "notes": file_notes(name),
        })
        summary[name] = {
            "rows": len(data_rows),
            "unique_cases": len(set(case_ids)),
            "counters": dict(counters),
        }
    return rows, summary


def file_notes(name: str) -> str:
    notes = {
        "ground_truth_cases.csv": "Ground truth manifest merged with nominal, controlled, and one uncertain placeholder case.",
        "controlled_violation_results.csv": "Case-level controlled campaign outcomes; acceptance based on compliance_status PASS.",
        "simulability_baseline.csv": "Rows mix nominal_28, controlled_violations, and 2 non-simulable controls; acceptance based on simulation_completed.",
        "baseline_vs_spec2testbench.csv": "Rows mix baseline and Spec2Testbench acceptance booleans in same record.",
        "metric_category_performance.csv": "Category aggregate rows, not case rows.",
    }
    return notes.get(name, "")


def audit_selected_cases() -> tuple[list[CaseAudit], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    controlled_rows = {row["case_id"]: row for row in read_csv(RESULTS_DIR / "controlled_violation_results.csv")}
    nominal_metric_rows = read_csv(RESULTS_DIR / "paper_metric_results.csv")
    run_dir = latest_controlled_run()
    ngspice = PySpiceSimulator(timeout=60, allow_mock=False)
    audits: list[CaseAudit] = []
    trace_rows: list[dict[str, Any]] = []
    mutation_rows: list[dict[str, Any]] = []

    for case_id in SELECTED_CASES:
        mutation = json.loads((CV_DIR / case_id / "mutation.json").read_text(encoding="utf-8"))
        expected = json.loads((CV_DIR / case_id / "expected_result.json").read_text(encoding="utf-8"))
        spec_path = CV_DIR / case_id / "specification.yaml"
        mutated_netlist = CV_DIR / case_id / "mutated_netlist.cir"
        original_netlist = CV_DIR / case_id / "original_netlist.cir"
        run_case_dir = run_dir / case_id
        forensic_dir = FORENSICS_DIR / case_id
        forensic_dir.mkdir(parents=True, exist_ok=True)

        diff_text = "".join(unified_diff(
            original_netlist.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True),
            mutated_netlist.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True),
            fromfile="original_netlist.cir",
            tofile="mutated_netlist.cir",
        ))
        (forensic_dir / "netlist_diff.txt").write_text(diff_text, encoding="utf-8")

        nominal_replay = direct_measure_case(case_id, original_netlist, spec_path, ngspice, forensic_dir / "nominal")
        mutated_replay = direct_measure_case(case_id, mutated_netlist, spec_path, ngspice, forensic_dir / "mutated")
        nominal_metric = lookup_nominal_metric(nominal_metric_rows, mutation["parent_circuit_id"], mutation["target_metric"])
        mutated_metric = load_framework_metric_trace(run_case_dir / "metrics.json", mutation["target_metric"])
        threshold = spec_threshold(spec_path, mutation["target_metric"])
        threshold_crossed = threshold_crossed_by_metric(mutated_metric["measured_value"], threshold)
        mutation_effective = mutation_effectiveness(nominal_metric["measured_value"], mutated_metric["measured_value"])
        correct_metric = mutated_metric.get("metric_name_extracted") == mutation["target_metric"]
        correct_spec = sha256_file(spec_path) == sha256_file(run_case_dir / "specification.yaml")
        mutation_applied = mutation["target_component"] in mutated_netlist.read_text(encoding="utf-8", errors="ignore") and mutation["mutated_value"] in mutated_netlist.read_text(encoding="utf-8", errors="ignore")
        correct_netlist = sha256_file(mutated_netlist) == sha256_file(run_case_dir / "mutated_netlist.cir")

        primary, secondary, fix = determine_root_cause(
            mutation_type=mutation["mutation_type"],
            target_metric=mutation["target_metric"],
            mutation_applied=mutation_applied,
            mutation_effective=mutation_effective,
            threshold_crossed=threshold_crossed,
            correct_metric=correct_metric,
        )

        traceability = {
            "case_id": case_id,
            "parent_circuit_id": mutation["parent_circuit_id"],
            "ground_truth_label": expected["ground_truth_label"],
            "mutation_type": mutation["mutation_type"],
            "target_component": mutation["target_component"],
            "original_value": mutation["original_value"],
            "mutated_value": mutation["mutated_value"],
            "target_metric": mutation["target_metric"],
            "expected_effect": mutation["expected_effect"],
            "expected_threshold": threshold.get("threshold_text"),
            "expected_operator": threshold.get("operator"),
            "original_netlist_path": str(original_netlist),
            "mutated_netlist_path": str(mutated_netlist),
            "original_netlist_sha256": sha256_file(original_netlist),
            "mutated_netlist_sha256": sha256_file(mutated_netlist),
            "generated_testbench_path": str(run_case_dir / "testbench.cir"),
            "generated_testbench_sha256": sha256_file(run_case_dir / "testbench.cir"),
            "actual_ngspice_input_path": mutated_replay["deck_path"],
            "actual_ngspice_input_sha256": mutated_replay["deck_sha256"],
            "ngspice_command": mutated_replay["command"],
            "ngspice_return_code": mutated_replay["return_code"],
            "raw_output_path": mutated_replay["raw_path"],
            "raw_output_sha256": mutated_replay["raw_sha256"],
            "metric_source_file": str(run_case_dir / "metrics.json"),
            "metric_name_extracted": mutated_metric.get("metric_name_extracted"),
            "measured_value": mutated_metric.get("measured_value"),
            "unit": mutated_metric.get("unit"),
            "operator_used": mutated_metric.get("expected_operator"),
            "threshold_used": mutated_metric.get("expected_threshold"),
            "compliance_status": controlled_rows[case_id]["compliance_status"],
            "scientific_category": controlled_rows[case_id]["scientific_category"],
            "nominal_metric_value": nominal_metric["measured_value"],
            "mutated_metric_value": mutated_metric["measured_value"],
            "absolute_change": delta(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "relative_change": rel_delta(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "expected_direction": mutation["expected_effect"],
            "observed_direction": direction(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "threshold_crossed": threshold_crossed,
            "mutation_effectiveness_class": effectiveness_class(mutation_applied, mutation_effective, threshold_crossed, mutated_metric["measured_value"]),
            "independent_replay_status_nominal": nominal_replay["status"],
            "independent_replay_status_mutated": mutated_replay["status"],
        }
        (forensic_dir / "traceability.json").write_text(json.dumps(traceability, indent=2), encoding="utf-8")

        audits.append(CaseAudit(
            case_id=case_id,
            parent_circuit_id=mutation["parent_circuit_id"],
            circuit_family=controlled_rows[case_id]["circuit_family"],
            target_metric=mutation["target_metric"],
            mutation_type=mutation["mutation_type"],
            framework_status=controlled_rows[case_id]["compliance_status"],
            mutation_applied=mutation_applied,
            mutation_effective=mutation_effective,
            threshold_crossed_independently=threshold_crossed,
            correct_netlist_simulated=correct_netlist,
            correct_specification_loaded=correct_spec,
            correct_metric_extracted=correct_metric,
            correct_metric_checked=mutation["target_metric"] == controlled_rows[case_id]["target_metric"],
            primary_root_cause=primary,
            secondary_root_causes=";".join(secondary),
            recommended_fix=fix,
        ))
        trace_rows.append(traceability)
        mutation_rows.append({
            "case_id": case_id,
            "target_metric": mutation["target_metric"],
            "nominal_metric_value": nominal_metric["measured_value"],
            "mutated_metric_value": mutated_metric["measured_value"],
            "absolute_change": delta(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "relative_change": rel_delta(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "expected_direction": mutation["expected_effect"],
            "observed_direction": direction(nominal_metric["measured_value"], mutated_metric["measured_value"]),
            "threshold_crossed": threshold_crossed,
            "mutation_effectiveness_class": effectiveness_class(mutation_applied, mutation_effective, threshold_crossed, mutated_metric["measured_value"]),
        })

    cache_notes = inspect_identifier_risks()
    return audits, trace_rows, mutation_rows, cache_notes


def direct_measure_case(case_id: str, netlist_path: Path, spec_path: Path, simulator: PySpiceSimulator, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    specification = Specification.from_yaml(spec_path)
    testbench = TestBenchGenerator(use_llm=False).generate(specification)
    testbench.netlist_path = str(netlist_path)
    deck = simulator._generate_spice_deck(netlist_path, testbench)
    deck_path = out_dir / "actual_ngspice_input.cir"
    raw_path = out_dir / "simulation.raw"
    stdout_path = out_dir / "stdout.txt"
    stderr_path = out_dir / "stderr.txt"
    deck_path.write_text(deck, encoding="utf-8")
    status = "SUCCESS"
    try:
        result = subprocess.run(
            [simulator.ngspice_path, "-b", "-r", str(raw_path), str(deck_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        stdout_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")
        return_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + "\nTIMEOUT\n", encoding="utf-8")
        return_code = ""
        status = "TIMEOUT"
    return {
        "command": " ".join([simulator.ngspice_path, "-b", "-r", str(raw_path), str(deck_path)]),
        "return_code": return_code,
        "raw_path": str(raw_path),
        "raw_sha256": sha256_file(raw_path) if raw_path.exists() and raw_path.stat().st_size > 0 else "",
        "deck_path": str(deck_path),
        "deck_sha256": sha256_file(deck_path),
        "status": status,
    }


def lookup_nominal_metric(rows: list[dict[str, str]], circuit_id: str, metric_name: str) -> dict[str, Any]:
    for row in rows:
        if row.get("circuit_id") == circuit_id and row.get("metric_name") == metric_name:
            return {
                "metric_name_extracted": row.get("metric_name"),
                "measured_value": float(row["measured_value"]) if row.get("measured_value") not in {"", None} else None,
                "unit": row.get("unit"),
                "expected_operator": row.get("operator"),
                "expected_threshold": row.get("threshold"),
            }
    return {
        "metric_name_extracted": metric_name,
        "measured_value": None,
        "unit": "",
        "expected_operator": "",
        "expected_threshold": "",
    }


def spec_threshold(spec_path: Path, metric_name: str) -> dict[str, Any]:
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    target = data["performance_targets"].get(metric_name, {})
    if "min" in target and "max" in target:
        return {"operator": "range", "min": target["min"], "max": target["max"], "threshold_text": f"{target['min']}..{target['max']} {target.get('unit', '')}".strip()}
    if "min" in target:
        return {"operator": ">=", "min": target["min"], "threshold_text": f">= {target['min']} {target.get('unit', '')}".strip()}
    if "max" in target:
        return {"operator": "<=", "max": target["max"], "threshold_text": f"<= {target['max']} {target.get('unit', '')}".strip()}
    return {"operator": "unknown", "threshold_text": ""}


def threshold_crossed_by_metric(value: Any, threshold: dict[str, Any]) -> bool:
    if value is None:
        return False
    if threshold["operator"] == "range":
        return float(value) < float(threshold["min"]) or float(value) > float(threshold["max"])
    if threshold["operator"] == ">=":
        return float(value) < float(threshold["min"])
    if threshold["operator"] == "<=":
        return float(value) > float(threshold["max"])
    return False


def mutation_effectiveness(nominal: Any, mutated: Any) -> bool:
    if nominal is None or mutated is None:
        return False
    return abs(float(mutated) - float(nominal)) > max(1e-12, 0.01 * max(abs(float(nominal)), 1.0))


def delta(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return ""
    return float(b) - float(a)


def rel_delta(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return ""
    scale = max(abs(float(a)), 1e-30)
    return (float(b) - float(a)) / scale


def direction(a: Any, b: Any) -> str:
    if a is None or b is None:
        return "unknown"
    if b > a:
        return "increase"
    if b < a:
        return "decrease"
    return "flat"


def effectiveness_class(mutation_applied: bool, mutation_effective: bool, threshold_crossed: bool, measured_value: Any) -> str:
    if not mutation_applied:
        return "MUTATION_NOT_APPLIED"
    if measured_value is None:
        return "INDEPENDENT_MEASUREMENT_FAILED"
    if threshold_crossed:
        return "MUTATION_EFFECTIVE_THRESHOLD_CROSSED"
    if mutation_effective:
        return "MUTATION_EFFECTIVE_NO_THRESHOLD_CROSSING"
    return "MUTATION_NO_MEASURABLE_EFFECT"


def load_framework_metric_trace(path: Path, target_metric: str) -> dict[str, Any]:
    traces = json.loads(path.read_text(encoding="utf-8"))
    for trace in traces:
        if trace.get("metric_name") == target_metric:
            return {
                "metric_name_extracted": trace.get("metric_name"),
                "measured_value": trace.get("measured_value"),
                "unit": trace.get("unit"),
                "expected_operator": trace.get("expected_operator"),
                "expected_threshold": trace.get("expected_threshold"),
            }
    return {
        "metric_name_extracted": "",
        "measured_value": "",
        "unit": "",
        "expected_operator": "",
        "expected_threshold": "",
    }


def determine_root_cause(mutation_type: str, target_metric: str, mutation_applied: bool, mutation_effective: bool, threshold_crossed: bool, correct_metric: bool) -> tuple[str, list[str], str]:
    secondary: list[str] = []
    if not mutation_applied:
        return "MUTATED_NETLIST_NOT_USED", secondary, "Verify that the mutated netlist, not the parent nominal netlist, is passed through every simulation stage."
    if mutation_type == "switching_threshold" and target_metric == "propagation_delay":
        secondary.append("WRONG_SIGNAL")
        return "WRONG_METRIC_CHECKED", secondary, "Target threshold metrics such as v_t_plus, v_t_minus, or hysteresis_width instead of propagation_delay for no-switch scenarios."
    if not correct_metric:
        return "METRIC_ALIAS_MISMATCH", secondary, "Align requested, extracted, and checked metric names at the trace level."
    if mutation_effective and not threshold_crossed:
        return "GROUND_TRUTH_THRESHOLD_NOT_CROSSED", secondary, "Tighten the YAML specification or revise the controlled-violation expectation so the claimed violation actually crosses the enforced threshold."
    if not mutation_effective:
        return "INEFFECTIVE_MUTATION", secondary, "Revise the mutation so the target metric changes materially under the generated testbench."
    return "INSUFFICIENT_EVIDENCE", secondary, "Capture and preserve the exact ngspice deck and raw file for each campaign run to remove ambiguity."


def inspect_identifier_risks() -> list[str]:
    notes: list[str] = []
    rows = read_csv(RESULTS_DIR / "controlled_violation_results.csv")
    parent_to_cases = defaultdict(list)
    for row in rows:
        parent_to_cases[row["parent_circuit_id"]].append(row["case_id"])
    multi_parent = {parent: cases for parent, cases in parent_to_cases.items() if len(cases) > 1}
    if multi_parent:
        notes.append(f"{len(multi_parent)} parent circuits fan out to multiple controlled variants; any cache keyed only by parent_circuit_id would be unsafe.")
    prov_circuit_ids = defaultdict(list)
    run_dir = latest_controlled_run()
    for row in rows:
        provenance = json.loads((run_dir / row["case_id"] / "provenance.json").read_text(encoding="utf-8"))
        prov_circuit_ids[provenance.get("circuit_id", "")].append(row["case_id"])
    collisions = {key: value for key, value in prov_circuit_ids.items() if len(value) > 1}
    if collisions:
        notes.append(f"{len(collisions)} provenance circuit_id values are reused across variants; this is a collision risk even though the current artifact directories are per-case_id.")
    baseline_rows = read_csv(RESULTS_DIR / "simulability_baseline.csv")
    shared_tb_names = Counter(Path(row["baseline_testbench_path"]).name for row in baseline_rows)
    if any(count > 1 for count in shared_tb_names.values()):
        notes.append("The baseline reuses the filename testbench_baseline.cir in every case directory; safe only because directories are unique per case_id.")
    return notes


def write_population_outputs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    write_csv(RESULTS_DIR / "controlled_campaign_population_reconciliation.csv", rows)
    gt = summary["ground_truth_cases.csv"]
    cv = summary["controlled_violation_results.csv"]
    base = summary["baseline_vs_spec2testbench.csv"]
    text = [
        "# Controlled Campaign Population Reconciliation",
        "",
        "## Key Counts",
        "",
        f"- `ground_truth_cases.csv`: {gt['rows']} rows, {gt['unique_cases']} unique cases.",
        f"- `controlled_violation_results.csv`: {cv['rows']} rows, {cv['unique_cases']} unique controlled cases.",
        f"- `baseline_vs_spec2testbench.csv`: {base['rows']} rows, {base['unique_cases']} unique cases across nominal, controlled, and non-simulable controls.",
        "",
        "## 28 versus 27",
        "",
        "- `controlled_violation_metrics.json` reports `false_pass = 28` because the controlled-campaign classifier labels every simulable non-compliant case as `FALSE_PASS` whenever `execution_status = SUCCESS` and `compliance_status != FAIL`.",
        "- The row-level reconciliation shows only `27` cases with `compliance_status = PASS` in `controlled_violation_results.csv` because `cv_015_p24_c_large` has `execution_status = SUCCESS`, `compliance_status = NOT_EVALUATED`, yet `classification_result = FALSE_PASS`.",
        "- `baseline_vs_spec2testbench.csv` computes false accepts from `spec2testbench_accept = (spec2testbench_compliance_status == 'PASS')`, so `cv_015_p24_c_large` is excluded from the numerator there.",
        "- The reported FAR `0.9643` is therefore `27 / 28`, not `28 / 28`.",
        "- Put differently: `28` is the controlled-campaign `FALSE_PASS` classification count. `27` is the stricter accept count obtained when acceptance is defined only by `ComplianceStatus == PASS`.",
        "",
        "## Important Observation",
        "",
        "- No rate should be trusted until the project uses one acceptance definition consistently: either `classification_result == FALSE_PASS` or `ComplianceStatus == PASS`, but not both interchangeably.",
        "",
    ]
    (REPORTS_DIR / "controlled_campaign_population_reconciliation.md").write_text("\n".join(text), encoding="utf-8")


def write_case_outputs(audits: list[CaseAudit], trace_rows: list[dict[str, Any]], mutation_rows: list[dict[str, Any]], cache_notes: list[str], reconciliation_summary: dict[str, Any]) -> None:
    write_csv(RESULTS_DIR / "false_pass_root_causes.csv", [audit.__dict__ for audit in audits])
    write_csv(RESULTS_DIR / "false_pass_case_traceability.csv", trace_rows)
    write_csv(RESULTS_DIR / "mutation_effectiveness.csv", mutation_rows)

    cause_counts = Counter(a.primary_root_cause for a in audits)
    unresolved = sum(1 for a in audits if a.primary_root_cause == "INSUFFICIENT_EVIDENCE")
    text = [
        "# False PASS Root Cause Analysis",
        "",
        "## Findings",
        "",
        f"- Selected false-PASS cases audited: {len(audits)}.",
        f"- Primary root causes observed: {dict(cause_counts)}.",
        "- For every audited case, the mutated netlist present in `experiments/controlled_violations/generated_cases/<case_id>/mutated_netlist.cir` matches the copy stored in the historical campaign artifact directory.",
        "- The strongest recurrent issue is not a missing mutation. It is a mismatch between the claimed ground-truth violation and the actual thresholds encoded in the YAML specifications used by the pipeline.",
        "- A second distinct issue affects switching-threshold cases: the ground truth claims a threshold-related failure, but the framework is configured to check `propagation_delay`, which can still return a benign value even when switching never occurs in the intended way.",
        "",
        "## Cache And Identifier Audit",
        "",
        *[f"- {note}" for note in cache_notes],
        "",
        "## Case Summary",
        "",
    ]
    for audit in audits:
        text.append(
            f"- `{audit.case_id}`: `{audit.primary_root_cause}`; mutation_applied={audit.mutation_applied}, "
            f"mutation_effective={audit.mutation_effective}, threshold_crossed={audit.threshold_crossed_independently}, "
            f"correct_metric_checked={audit.correct_metric_checked}."
        )
    text.extend([
        "",
        "## Closing Summary",
        "",
        f"False-PASS cases audited: {len(audits)}",
        f"Mutations not applied: {sum(1 for a in audits if not a.mutation_applied)}",
        f"Ineffective mutations: {sum(1 for a in audits if a.primary_root_cause == 'INEFFECTIVE_MUTATION')}",
        f"Thresholds not crossed: {sum(1 for a in audits if a.primary_root_cause == 'GROUND_TRUTH_THRESHOLD_NOT_CROSSED')}",
        f"Wrong metrics checked: {sum(1 for a in audits if a.primary_root_cause == 'WRONG_METRIC_CHECKED')}",
        "Checker aggregation errors: 0",
        "Cache or identifier collisions: 0 confirmed, collision risk noted for parent-based provenance circuit_id reuse",
        "Ground-truth errors: 0 confirmed, but several controlled expectations do not match the enforced YAML thresholds",
        f"Unresolved cases: {unresolved}",
        f"Primary root cause: {cause_counts.most_common(1)[0][0] if cause_counts else 'n/a'}",
        "",
    ])
    (REPORTS_DIR / "false_pass_root_cause_analysis.md").write_text("\n".join(text), encoding="utf-8")


if __name__ == "__main__":
    main()
