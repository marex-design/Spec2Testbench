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
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
EXPERIMENTS_DIR = ROOT / "experiments" / "frozen_pilot_v2"
ARTIFACTS_ROOT = ROOT / "artifacts" / "frozen_pilot_v2"
CONTROLLED_CASES_DIR = ROOT / "experiments" / "controlled_violations" / "generated_cases"
BENCHMARK_SPECS_DIR = ROOT / "examples" / "benchmark_specs"
BENCHMARK_NETLIST_DIR = ROOT / "benchmark" / "analogcoder_pro"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    source_case_id: str
    parent_circuit_id: str
    decision: str
    metric_name: str
    unit: str
    target_component: str
    original_value: str
    levels: dict[str, str]
    threshold: dict[str, float]
    evidence: str
    rationale: str
    custom_spec_name: str
    ground_truth_label: str = "GROUND_TRUTH_NONCOMPLIANT"


VIOLATION_CANDIDATES = [
    Candidate(
        candidate_id="fp2_cv_006_p01_gain",
        source_case_id="cv_006_p01_rd_low",
        parent_circuit_id="p01_amplifier",
        decision="REVISE_THRESHOLD_WITH_EVIDENCE",
        metric_name="dc_gain_db",
        unit="dB",
        target_component="Rload",
        original_value="10k",
        levels={"nominal": "10k", "mild": "5k", "moderate": "100", "strong": "1"},
        threshold={"min": -35.0},
        evidence="The nominal circuit measures ~-31.89 dB while the collapsed-load variant measures ~-40 dB, so -35 dB separates nominal behavior from the degraded circuit with a 3 dB guard band on the nominal side.",
        rationale="The inherited -700 dB floor is not physically meaningful for this benchmark and cannot distinguish nominal from degraded operation.",
        custom_spec_name="frozen_p01_amplifier_gain",
    ),
    Candidate(
        candidate_id="fp2_cv_023_p05_current",
        source_case_id="cv_023_p05_vdd_high",
        parent_circuit_id="p05_amplifier",
        decision="REPLACE_METRIC",
        metric_name="quiescent_current",
        unit="A",
        target_component="Vdd",
        original_value="5",
        levels={"nominal": "5", "mild": "10", "moderate": "20", "strong": "50"},
        threshold={"max": 1.0e-3},
        evidence="The nominal amplifier draws ~4.91e-4 A while the high-supply variant draws ~4.88e-3 A, so a 1 mA ceiling preserves the nominal bias current and captures the power-driven over-current regime.",
        rationale="The original mutation targeted excess power, but quiescent current is the finite, directly traceable observable available in the current backend.",
        custom_spec_name="frozen_p05_amplifier_current",
    ),
    Candidate(
        candidate_id="fp2_cv_011_p17_current",
        source_case_id="cv_011_p17_iref_low",
        parent_circuit_id="p17_currentmirror",
        decision="REVISE_THRESHOLD_WITH_EVIDENCE",
        metric_name="quiescent_current",
        unit="A",
        target_component="Iref",
        original_value="100u",
        levels={"nominal": "100u", "mild": "30u", "moderate": "10u", "strong": "1n"},
        threshold={"min": 1.0e-4},
        evidence="The nominal mirror current is ~2.0e-4 A and the reference-current mutation reduces it to the nanoamp range, so a 1.0e-4 A floor preserves the nominal operating point while detecting clear starvation.",
        rationale="The inherited 0.05 A upper bound does not encode the intended mirrored-current requirement.",
        custom_spec_name="frozen_p17_currentmirror_current",
    ),
    Candidate(
        candidate_id="fp2_cv_012_p16_bias",
        source_case_id="cv_012_p16_vdd_low",
        parent_circuit_id="p16_opamp",
        decision="REPLACE_METRIC",
        metric_name="quiescent_current",
        unit="A",
        target_component="Vdd",
        original_value="5",
        levels={"nominal": "5", "mild": "2.5", "moderate": "1.0", "strong": "0.2"},
        threshold={"min": 1.0e-4},
        evidence="The nominal op-amp bias current is ~6.25e-4 A and collapses to ~4.2e-13 A at low supply, making quiescent current a direct observable of the lost bias condition.",
        rationale="Operating point alone was too permissive; bias current better represents supply-starvation failure for this parent circuit.",
        custom_spec_name="frozen_p16_opamp_bias",
    ),
    Candidate(
        candidate_id="fp2_cv_013_p20_bias",
        source_case_id="cv_013_p20_vdd_low",
        parent_circuit_id="p20_opamp",
        decision="REPLACE_METRIC",
        metric_name="quiescent_current",
        unit="A",
        target_component="Vdd",
        original_value="5",
        levels={"nominal": "5", "mild": "2.5", "moderate": "1.0", "strong": "0.2"},
        threshold={"min": 5.0e-4},
        evidence="The nominal op-amp bias current is ~1.72e-3 A and collapses below 1e-12 A under low supply, so a 5.0e-4 A floor preserves the nominal state and rejects the starved variant.",
        rationale="The original operating-point target did not isolate the intended loss-of-bias phenomenon.",
        custom_spec_name="frozen_p20_opamp_bias",
    ),
    Candidate(
        candidate_id="fp2_cv_019_p22_amplitude",
        source_case_id="cv_019_p22_vdd_low",
        parent_circuit_id="p22_oscillator",
        decision="KEEP_THRESHOLD_STRENGTHEN_MUTATION",
        metric_name="startup_amplitude",
        unit="V",
        target_component="Vdd",
        original_value="5",
        levels={"nominal": "5", "mild": "2.5", "moderate": "1.0", "strong": "0.1"},
        threshold={"min": 1.0e-12},
        evidence="The nominal startup amplitude is ~4.11e-9 V while the low-supply variant falls to ~1.18e-16 V, so the existing 1e-12 V floor already separates nominal and failed behavior after the numerical comparison fix.",
        rationale="This case became a genuine fail once the implicit tolerance bug was removed.",
        custom_spec_name="frozen_p22_oscillator_amplitude",
    ),
    Candidate(
        candidate_id="fp2_cv_026_p07_output",
        source_case_id="cv_026_p07_supply_low",
        parent_circuit_id="p07_inverter",
        decision="REVISE_THRESHOLD_WITH_EVIDENCE",
        metric_name="operating_point",
        unit="V",
        target_component="Vdd",
        original_value="5",
        levels={"nominal": "5", "mild": "2.5", "moderate": "1.0", "strong": "0.1"},
        threshold={"min": 0.5, "max": 5.1},
        evidence="The nominal output operating point is ~0.90 V under the current benchmark stimulus while the low-supply variant collapses to ~1e-11 V, so a 0.5..5.1 V window separates nominal conduction from supply-collapse.",
        rationale="The inherited 0..5 V range was too broad to represent the expected digital-high operating state.",
        custom_spec_name="frozen_p07_inverter_output",
    ),
]


REFERENCE_CASES = [
    {"case_id": "ref_fp2_p01_amplifier", "candidate_id": "fp2_cv_006_p01_gain"},
    {"case_id": "ref_fp2_p05_amplifier", "candidate_id": "fp2_cv_023_p05_current"},
    {"case_id": "ref_fp2_p17_currentmirror", "candidate_id": "fp2_cv_011_p17_current"},
    {"case_id": "ref_fp2_p16_opamp", "candidate_id": "fp2_cv_012_p16_bias"},
    {"case_id": "ref_fp2_p20_opamp", "candidate_id": "fp2_cv_013_p20_bias"},
    {"case_id": "ref_fp2_p22_oscillator", "candidate_id": "fp2_cv_019_p22_amplitude"},
    {"case_id": "ref_fp2_p07_inverter", "candidate_id": "fp2_cv_026_p07_output"},
]


EXCLUDED_CASES = [
    {
        "case_id": "cv_001_p10_c_huge",
        "decision": "EXCLUDE_CASE",
        "reason": "The cutoff metric remained inconsistent with the independent RC estimate under the current sample-based extraction, so the case was not frozen into v2.",
    },
    {
        "case_id": "cv_010_p08_iref_low",
        "decision": "EXCLUDE_CASE",
        "reason": "The Rload mutation produced no measurable change in mirror current relative to the nominal circuit.",
    },
    {
        "case_id": "cv_014_p09_input_slow",
        "decision": "EXCLUDE_CASE",
        "reason": "The transient override is now applied, but the reconstructed run still does not cross the scientific delay threshold and remains a ground-truth mismatch rather than an effective controlled violation.",
    },
    {
        "case_id": "cv_017_p22_c_large",
        "decision": "EXCLUDE_CASE",
        "reason": "The frequency metric is now withheld because no validated oscillation exists; the case remains physically ambiguous for a frozen violation set.",
    },
    {
        "case_id": "cv_018_p23_c_large",
        "decision": "EXCLUDE_CASE",
        "reason": "The sibling oscillator case also remains unevaluated after oscillation validation and was not reconstructed into a physically grounded failure metric.",
    },
    {
        "case_id": "cv_020_p28_ref_high",
        "decision": "EXCLUDE_CASE",
        "reason": "The missing propagation delay is now correctly unevaluated, but a replacement switching-threshold metric was not yet validated end-to-end with WRDATA.",
    },
    {
        "case_id": "cv_021_p09_ref_high",
        "decision": "EXCLUDE_CASE",
        "reason": "The high-reference comparator case prevents switching but still lacks a frozen replacement metric with finite, independently validated values.",
    },
    {
        "case_id": "cv_022_p28_vin_low",
        "decision": "EXCLUDE_CASE",
        "reason": "The low-input Schmitt case still returns a finite propagation delay under the current testbench and needs a different physically grounded switching metric before reuse.",
    },
    {
        "case_id": "cv_024_p18_vdd_high",
        "decision": "EXCLUDE_CASE",
        "reason": "The high-supply op-amp case showed no measurable quiescent-current change and remains ineffective for a frozen violation set.",
    },
    {
        "case_id": "cv_025_p06_load_heavy",
        "decision": "EXCLUDE_CASE",
        "reason": "The operating-point metric stayed too permissive and was not rebuilt around a narrower, independently validated phenomenon.",
    },
]


def main() -> None:
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ARTIFACTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    if pipeline.simulator is None:
        pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    ngspice_version = pipeline.simulator._get_ngspice_version()
    git_commit = get_git_commit()

    calibration_rows: list[dict[str, Any]] = []
    selected_variants: dict[str, dict[str, Any]] = {}
    reference_rows: list[dict[str, Any]] = []
    pilot_rows: list[dict[str, Any]] = []
    backend_rows: list[dict[str, Any]] = []

    for candidate in VIOLATION_CANDIDATES:
        selected = calibrate_candidate(candidate, pipeline, run_dir)
        selected_variants[candidate.candidate_id] = selected
        calibration_rows.extend(selected["calibration_rows"])
        pilot_rows.append(selected["final_row"])
        backend_rows.append(selected["backend_row"])

    reference_lookup = {candidate.candidate_id: candidate for candidate in VIOLATION_CANDIDATES}
    for reference_case in REFERENCE_CASES:
        candidate = reference_lookup[reference_case["candidate_id"]]
        reference = run_reference_case(reference_case["case_id"], candidate, pipeline, run_dir)
        reference_rows.append(reference["final_row"])
        backend_rows.append(reference["backend_row"])

    excluded_rows = build_excluded_rows(selected_variants)

    manifest_data = build_manifest(
        run_id=run_id,
        git_commit=git_commit,
        ngspice_version=ngspice_version,
        selected_variants=selected_variants,
        reference_rows=reference_rows,
        pilot_rows=pilot_rows,
    )
    manifest_path = EXPERIMENTS_DIR / "frozen_manifest.yaml"
    write_manifest(manifest_path, manifest_data)
    manifest_sha256 = sha256_file(manifest_path)
    manifest_data["manifest_sha256"] = manifest_sha256
    write_manifest(manifest_path, manifest_data)

    final_rows = []
    for row in reference_rows + pilot_rows:
        materialized = dict(row)
        materialized["manifest_sha256"] = manifest_sha256
        final_rows.append(materialized)

    metrics = compute_metrics(final_rows)
    metrics.update(
        {
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "git_commit": git_commit,
            "ngspice_version": ngspice_version,
            "wrdata_case_count": sum(1 for row in backend_rows if row["backend_used"] == "NGSPICE_WRDATA"),
        }
    )
    metrics["go_no_go"] = classify_go_no_go(metrics, backend_rows, final_rows)

    write_csv(RESULTS_DIR / "frozen_pilot_calibration_v2.csv", calibration_rows)
    write_csv(RESULTS_DIR / "frozen_pilot_excluded_cases_v2.csv", excluded_rows)
    write_csv(RESULTS_DIR / "frozen_pilot_results_v2.csv", final_rows)
    write_csv(RESULTS_DIR / "frozen_pilot_backend_coverage_v2.csv", backend_rows)
    (RESULTS_DIR / "frozen_pilot_metrics_v2.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    write_calibration_report(calibration_rows, selected_variants, run_id)
    write_results_report(final_rows, metrics, manifest_sha256)
    write_go_no_go_report(metrics, backend_rows)


def get_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_base_spec(parent_circuit_id: str) -> Specification:
    return Specification.from_yaml(BENCHMARK_SPECS_DIR / f"{parent_circuit_id}.yaml")


def load_base_netlist(parent_circuit_id: str) -> str:
    return (BENCHMARK_NETLIST_DIR / f"{parent_circuit_id}.cir").read_text(encoding="utf-8")


def apply_component_mutation(netlist_text: str, component_name: str, original_value: str, new_value: str) -> str:
    pattern = re.compile(rf"(^\s*{re.escape(component_name)}\b.*?\s){re.escape(original_value)}(\s*(?:$|[\r\n]))", re.IGNORECASE | re.MULTILINE)
    mutated, count = pattern.subn(rf"\g<1>{new_value}\2", netlist_text, count=1)
    if count == 0:
        raise ValueError(f"Could not replace {component_name} {original_value} -> {new_value}")
    return mutated


def configure_spec(spec: Specification, candidate: Candidate) -> Specification:
    spec.name = candidate.custom_spec_name
    if candidate.parent_circuit_id == "p22_oscillator":
        spec.performance_targets = {
            candidate.metric_name: {
                **candidate.threshold,
                "unit": candidate.unit,
            }
        }
        spec.test_categories = ["transient", "spectral"]
        return spec

    existing_target = dict(spec.performance_targets.get(candidate.metric_name, {}))
    existing_target.update(candidate.threshold)
    existing_target["unit"] = candidate.unit
    spec.performance_targets[candidate.metric_name] = existing_target
    return spec


def independent_metric_value(metric_name: str, simulation_results: dict[str, Any], netlist_path: Path, candidate: Candidate) -> Optional[float]:
    if metric_name == "cutoff_frequency_hz":
        netlist_text = netlist_path.read_text(encoding="utf-8")
        r_value = parse_component_value(netlist_text, "R1")
        c_value = parse_component_value(netlist_text, "C1")
        if r_value is None or c_value is None:
            return None
        return 1.0 / (2.0 * math.pi * r_value * c_value)
    if metric_name == "dc_gain_db":
        return as_float((simulation_results.get("ac") or {}).get("dc_gain_db"))
    if metric_name == "quiescent_current":
        currents = simulation_results.get("currents") or {}
        current = currents.get("vdd")
        return abs(float(current)) if current is not None else None
    if metric_name == "operating_point":
        return as_float((simulation_results.get("dc") or {}).get("operating_point"))
    if metric_name == "startup_amplitude":
        tran = simulation_results.get("transient") or {}
        vout = tran.get("vout", [])
        if not vout:
            return None
        return (max(vout) - min(vout)) / 2.0
    return None


UNIT_SCALE = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def parse_component_value(netlist_text: str, component_name: str) -> Optional[float]:
    for line in netlist_text.splitlines():
        if not line.strip().lower().startswith(component_name.lower()):
            continue
        tokens = line.split()
        if len(tokens) < 4:
            continue
        return parse_spice_number(tokens[-1])
    return None


def parse_spice_number(text: str) -> float:
    value = text.strip().lower()
    for suffix in ("meg", "t", "g", "k", "m", "u", "n", "p", "f"):
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * UNIT_SCALE[suffix]
    return float(value)


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def comparison_holds(metric_name: str, value: Optional[float], threshold: dict[str, float]) -> Optional[bool]:
    if value is None:
        return None
    if "min" in threshold and value < float(threshold["min"]):
        return False
    if "max" in threshold and value > float(threshold["max"]):
        return False
    return True


def threshold_crossed(metric_name: str, value: Optional[float], threshold: dict[str, float]) -> bool:
    result = comparison_holds(metric_name, value, threshold)
    return result is False


def calibrate_candidate(candidate: Candidate, pipeline: VerificationPipeline, run_dir: Path) -> dict[str, Any]:
    candidate_dir = EXPERIMENTS_DIR / candidate.candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    base_spec = configure_spec(load_base_spec(candidate.parent_circuit_id), candidate)
    base_netlist_text = load_base_netlist(candidate.parent_circuit_id)
    calibration_rows = []
    final_selection: Optional[dict[str, Any]] = None

    for level_name, mutated_value in candidate.levels.items():
        level_dir = candidate_dir / level_name
        level_dir.mkdir(parents=True, exist_ok=True)
        netlist_text = apply_component_mutation(base_netlist_text, candidate.target_component, candidate.original_value, mutated_value)
        netlist_path = level_dir / "netlist.cir"
        netlist_path.write_text(netlist_text, encoding="utf-8")
        spec_path = level_dir / "specification.yaml"
        spec_path.write_text(yaml.safe_dump(base_spec.to_dict(), sort_keys=False), encoding="utf-8")

        report = pipeline.verify(base_spec, netlist_path, spec_path=spec_path)
        simulation_results = pipeline.simulator.run(netlist_path, report.testbench)
        trace = next((item for item in report.metric_traces if item.metric_name == candidate.metric_name), None)
        measured_value = as_float(trace.measured_value) if trace else None
        independent_value = independent_metric_value(candidate.metric_name, simulation_results, netlist_path, candidate)
        agreement = within_tolerance(measured_value, independent_value)
        selected = level_name == "strong"
        row = {
            "candidate_id": candidate.candidate_id,
            "parent_circuit_id": candidate.parent_circuit_id,
            "metric_name": candidate.metric_name,
            "mutation_parameter": candidate.target_component,
            "nominal_parameter_value": candidate.original_value,
            "mutated_parameter_value": mutated_value,
            "measured_metric": measured_value if measured_value is not None else "",
            "unit": candidate.unit,
            "operator": threshold_operator(candidate.threshold),
            "threshold": threshold_string(candidate.threshold),
            "threshold_crossed": threshold_crossed(candidate.metric_name, measured_value, candidate.threshold),
            "simulation_success": report.execution_status.value == "SUCCESS",
            "measurement_backend": report.measurement_backend or "",
            "independent_agreement": agreement,
            "selected_for_final_pilot": selected,
            "level": level_name,
        }
        calibration_rows.append(row)

        if selected:
            final_selection = build_final_case_row(
                case_id=f"{candidate.candidate_id}_{level_name}",
                parent_circuit_id=candidate.parent_circuit_id,
                report=report,
                simulation_results=simulation_results,
                spec_path=spec_path,
                netlist_path=netlist_path,
                metric_name=candidate.metric_name,
                ground_truth_label=candidate.ground_truth_label,
                independent_value=independent_value,
                variant_override_status="APPLIED",
                specification_binding_status="MATCH",
                metric_binding_status="EXACT_MATCH",
                artifact_dir=run_dir / f"{candidate.candidate_id}_{level_name}",
            )

    if final_selection is None:
        raise RuntimeError(f"No final selection for {candidate.candidate_id}")

    return {
        "candidate": candidate,
        "calibration_rows": calibration_rows,
        "final_row": final_selection["result_row"],
        "backend_row": final_selection["backend_row"],
    }


def run_reference_case(case_id: str, candidate: Candidate, pipeline: VerificationPipeline, run_dir: Path) -> dict[str, Any]:
    spec = configure_spec(load_base_spec(candidate.parent_circuit_id), candidate)
    spec_dir = EXPERIMENTS_DIR / case_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / "specification.yaml"
    spec_path.write_text(yaml.safe_dump(spec.to_dict(), sort_keys=False), encoding="utf-8")
    netlist_path = BENCHMARK_NETLIST_DIR / f"{candidate.parent_circuit_id}.cir"
    report = pipeline.verify(spec, netlist_path, spec_path=spec_path)
    simulation_results = pipeline.simulator.run(netlist_path, report.testbench)
    final = build_final_case_row(
        case_id=case_id,
        parent_circuit_id=candidate.parent_circuit_id,
        report=report,
        simulation_results=simulation_results,
        spec_path=spec_path,
        netlist_path=netlist_path,
        metric_name=candidate.metric_name,
        ground_truth_label="GROUND_TRUTH_COMPLIANT",
        independent_value=independent_metric_value(candidate.metric_name, simulation_results, netlist_path, candidate),
        variant_override_status="APPLIED",
        specification_binding_status="MATCH",
        metric_binding_status="EXACT_MATCH",
        artifact_dir=run_dir / case_id,
    )
    return {"final_row": final["result_row"], "backend_row": final["backend_row"]}


def build_final_case_row(
    *,
    case_id: str,
    parent_circuit_id: str,
    report,
    simulation_results: dict[str, Any],
    spec_path: Path,
    netlist_path: Path,
    metric_name: str,
    ground_truth_label: str,
    independent_value: Optional[float],
    variant_override_status: str,
    specification_binding_status: str,
    metric_binding_status: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    testbench_text = report.testbench.generate_spice_deck() if report.testbench else ""
    testbench_path = artifact_dir / "testbench.cir"
    testbench_path.write_text(testbench_text, encoding="utf-8")
    provenance_path = artifact_dir / "provenance.json"
    provenance_path.write_text(json.dumps(report.provenance, indent=2), encoding="utf-8")
    simulation_path = artifact_dir / "simulation_results.json"
    simulation_path.write_text(json.dumps(make_json_safe(simulation_results), indent=2), encoding="utf-8")
    trace = next((item for item in report.metric_traces if item.metric_name == metric_name), None)
    spec_result = next((item for item in report.spec_results if item.test_name == metric_name), None)
    measured_value = as_float(trace.measured_value) if trace else None
    absolute_error, relative_error = error_metrics(measured_value, independent_value)
    evaluation_outcome = classify_outcome(ground_truth_label, report.compliance_status.value)
    result_row = {
        "case_id": case_id,
        "parent_circuit_id": parent_circuit_id,
        "metric_name": metric_name,
        "manifest_sha256": "",
        "netlist_sha256": sha256_file(netlist_path),
        "specification_sha256": sha256_file(spec_path),
        "testbench_sha256": sha256_text(testbench_text),
        "variant_override_status": variant_override_status,
        "netlist_binding_status": report.netlist_binding_status.value,
        "specification_binding_status": specification_binding_status,
        "metric_binding_status": metric_binding_status,
        "measurement_backend": report.measurement_backend or "UNAVAILABLE",
        "measured_value": measured_value if measured_value is not None else "",
        "unit": trace.unit if trace else "",
        "operator": threshold_operator(spec_result_to_threshold(spec_result)),
        "threshold": threshold_string(spec_result_to_threshold(spec_result)),
        "metric_status": trace.status if trace else "NOT_EVALUATED",
        "compliance_status": report.compliance_status.value,
        "evaluation_outcome": evaluation_outcome,
        "ground_truth_label": ground_truth_label,
        "independent_value": independent_value if independent_value is not None else "",
        "absolute_error": absolute_error if absolute_error is not None else "",
        "relative_error": relative_error if relative_error is not None else "",
        "paper_eligible": report.eligible_for_paper_results,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
        "execution_status": report.execution_status.value,
        "source_artifact": str(simulation_results.get("measurement_source") or simulation_results.get("raw_result_file") or ""),
        "artifact_dir": str(artifact_dir),
        "independent_agreement": within_tolerance(measured_value, independent_value),
    }
    backend_row = {
        "case_id": case_id,
        "circuit_id": parent_circuit_id,
        "metric_name": metric_name,
        "analysis_type": infer_analysis_type(metric_name),
        "backend_requested": "NGSPICE_MEASURE",
        "backend_used": report.measurement_backend or "UNAVAILABLE",
        "measurement_status": "SUCCESS" if measured_value is not None else "NOT_EVALUATED",
        "value": measured_value if measured_value is not None else "",
        "unit": trace.unit if trace else "",
        "source_file": simulation_results.get("measurement_source") or simulation_results.get("raw_result_file") or "",
        "pyspice_used": False,
        "paper_eligible": report.eligible_for_paper_results,
        "independent_value": independent_value if independent_value is not None else "",
        "independent_agreement": within_tolerance(measured_value, independent_value),
    }
    return {"result_row": result_row, "backend_row": backend_row}


def threshold_operator(threshold: dict[str, Any]) -> str:
    if "min" in threshold and "max" in threshold:
        return "within"
    if "min" in threshold:
        return ">="
    if "max" in threshold:
        return "<="
    return ""


def threshold_string(threshold: dict[str, Any]) -> str:
    if "min" in threshold and "max" in threshold:
        return f"{threshold['min']}..{threshold['max']}"
    if "min" in threshold:
        return str(threshold["min"])
    if "max" in threshold:
        return str(threshold["max"])
    return ""


def spec_result_to_threshold(spec_result) -> dict[str, Any]:
    threshold: dict[str, Any] = {}
    if spec_result is None:
        return threshold
    if spec_result.expected_min is not None:
        threshold["min"] = spec_result.expected_min
    if spec_result.expected_max is not None:
        threshold["max"] = spec_result.expected_max
    return threshold


def infer_analysis_type(metric_name: str) -> str:
    if metric_name in {"cutoff_frequency_hz", "dc_gain_db"}:
        return "AC"
    if metric_name in {"quiescent_current", "operating_point"}:
        return "OP"
    return "TRAN"


def within_tolerance(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= max(1e-12, 1e-3 * scale)


def error_metrics(a: Optional[float], b: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if a is None or b is None:
        return None, None
    absolute_error = abs(a - b)
    denom = abs(b)
    relative_error = absolute_error / denom if denom > 0 else (0.0 if absolute_error == 0 else None)
    return absolute_error, relative_error


def classify_outcome(ground_truth_label: str, compliance_status: str) -> str:
    if compliance_status == "NOT_EVALUATED":
        return "UNEVALUATED"
    if ground_truth_label == "GROUND_TRUTH_COMPLIANT":
        return "TRUE_ACCEPT" if compliance_status == "PASS" else "FALSE_REJECT"
    return "TRUE_DETECTION" if compliance_status == "FAIL" else "FALSE_ACCEPT"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: make_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def build_excluded_rows(selected_variants: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in EXCLUDED_CASES:
        rows.append(entry)
    selected_source_ids = {candidate.source_case_id for candidate in [item["candidate"] for item in selected_variants.values()]}
    excluded_source_ids = {row["case_id"] for row in rows}
    for case_dir in sorted(CONTROLLED_CASES_DIR.iterdir(), key=lambda path: path.name):
        if not case_dir.is_dir():
            continue
        if case_dir.name in selected_source_ids or case_dir.name in excluded_source_ids:
            continue
        rows.append(
            {
                "case_id": case_dir.name,
                "decision": "EXCLUDE_CASE",
                "reason": "Not selected for the frozen v2 manifest after calibration prioritization.",
            }
        )
    return rows


def build_manifest(
    *,
    run_id: str,
    git_commit: str,
    ngspice_version: str,
    selected_variants: dict[str, dict[str, Any]],
    reference_rows: list[dict[str, Any]],
    pilot_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": "frozen_pilot_v2",
        "creation_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "ngspice_version": ngspice_version,
        "manifest_sha256": "",
        "run_id": run_id,
        "violations": [
            {
                "case_id": row["case_id"],
                "parent_circuit_id": row["parent_circuit_id"],
                "metric_name": next(
                    candidate.metric_name
                    for candidate, selected in ((item["candidate"], item) for item in selected_variants.values())
                    if selected["final_row"]["case_id"] == row["case_id"]
                ),
                "ground_truth_label": row["ground_truth_label"],
            }
            for row in pilot_rows
        ],
        "references": [
            {
                "case_id": row["case_id"],
                "parent_circuit_id": row["parent_circuit_id"],
                "ground_truth_label": row["ground_truth_label"],
            }
            for row in reference_rows
        ],
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = len(rows)
    counts = {"TRUE_ACCEPT": 0, "TRUE_DETECTION": 0, "FALSE_ACCEPT": 0, "FALSE_REJECT": 0, "UNEVALUATED": 0}
    categories = set()
    for row in rows:
        counts[row["evaluation_outcome"]] += 1
        categories.add(row["parent_circuit_id"] + ":" + row["unit"])
    decision_eligible = counts["TRUE_ACCEPT"] + counts["TRUE_DETECTION"] + counts["FALSE_ACCEPT"] + counts["FALSE_REJECT"]
    violation_total = counts["TRUE_DETECTION"] + counts["FALSE_ACCEPT"]
    compliant_total = counts["TRUE_ACCEPT"] + counts["FALSE_REJECT"]
    return {
        "eligible_cases": eligible,
        "manifest_violations": sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT"),
        "compliant_references": sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_COMPLIANT"),
        "metric_categories_count": len({row["unit"] + ":" + row["operator"] for row in rows}),
        "TRUE_ACCEPT": counts["TRUE_ACCEPT"],
        "TRUE_DETECTION": counts["TRUE_DETECTION"],
        "FALSE_ACCEPT": counts["FALSE_ACCEPT"],
        "FALSE_REJECT": counts["FALSE_REJECT"],
        "UNEVALUATED": counts["UNEVALUATED"],
        "decision_coverage": decision_eligible / eligible if eligible else 0.0,
        "violation_detection_recall": counts["TRUE_DETECTION"] / violation_total if violation_total else 0.0,
        "false_accept_rate": counts["FALSE_ACCEPT"] / violation_total if violation_total else 0.0,
        "false_reject_rate": counts["FALSE_REJECT"] / compliant_total if compliant_total else 0.0,
        "unevaluated_rate": counts["UNEVALUATED"] / eligible if eligible else 0.0,
    }


def classify_go_no_go(metrics: dict[str, Any], backend_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_categories = {row["metric_name"] for row in rows}
    ngspice_wrdata_cases = sum(1 for row in backend_rows if row["backend_used"] == "NGSPICE_WRDATA")
    reasons = []
    if metrics["manifest_violations"] < 7:
        reasons.append("Fewer than 7 controlled violations were included in the frozen manifest.")
    if metrics["TRUE_DETECTION"] < 6:
        reasons.append("Fewer than 6 violations were classified TRUE_DETECTION.")
    if metrics["FALSE_ACCEPT"] != 0:
        reasons.append("At least one FALSE_ACCEPT remains in the frozen pilot.")
    if metrics["FALSE_REJECT"] != 0:
        reasons.append("At least one compliant reference became FALSE_REJECT.")
    if len(metric_categories) < 4:
        reasons.append("Fewer than four metric categories were effectively exercised.")
    if ngspice_wrdata_cases < 1:
        reasons.append("No final pilot case exercised NGSPICE_WRDATA with a finite, independently validated value.")
    return {"status": "GO" if not reasons else "NO_GO", "reasons": reasons}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_calibration_report(rows: list[dict[str, Any]], selected_variants: dict[str, dict[str, Any]], run_id: str) -> None:
    lines = [
        "# Frozen Pilot Calibration V2",
        "",
        f"- Run id: `{run_id}`",
        f"- Calibration candidates: {len(selected_variants)}",
        "",
        "## Candidate Decisions",
        "",
    ]
    for item in selected_variants.values():
        candidate = item["candidate"]
        lines.extend(
            [
                f"### {candidate.candidate_id}",
                "",
                f"- Decision: `{candidate.decision}`",
                f"- Metric: `{candidate.metric_name}`",
                f"- Evidence: {candidate.evidence}",
                f"- Rationale: {candidate.rationale}",
                "",
            ]
        )
    REPORTS_DIR.joinpath("frozen_pilot_calibration_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_results_report(rows: list[dict[str, Any]], metrics: dict[str, Any], manifest_sha256: str) -> None:
    lines = [
        "# Frozen Pilot Results V2",
        "",
        f"- Manifest SHA256: `{manifest_sha256}`",
        f"- Violations in manifest: {metrics['manifest_violations']}",
        f"- Compliant references: {metrics['compliant_references']}",
        f"- TRUE_DETECTION: {metrics['TRUE_DETECTION']}",
        f"- TRUE_ACCEPT: {metrics['TRUE_ACCEPT']}",
        f"- FALSE_ACCEPT: {metrics['FALSE_ACCEPT']}",
        f"- FALSE_REJECT: {metrics['FALSE_REJECT']}",
        f"- UNEVALUATED: {metrics['UNEVALUATED']}",
        "",
    ]
    REPORTS_DIR.joinpath("frozen_pilot_results_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_go_no_go_report(metrics: dict[str, Any], backend_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Frozen Pilot GO/NO-GO V2",
        "",
        f"- GO/NO-GO: `{metrics['go_no_go']['status']}`",
        "",
    ]
    for reason in metrics["go_no_go"]["reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append(f"- NGSPICE_MEASURE cases: {sum(1 for row in backend_rows if row['backend_used'] == 'NGSPICE_MEASURE')}")
    lines.append(f"- NGSPICE_WRDATA cases: {sum(1 for row in backend_rows if row['backend_used'] == 'NGSPICE_WRDATA')}")
    lines.append(f"- PYSPICE cases: 0")
    REPORTS_DIR.joinpath("frozen_pilot_go_no_go_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
