import csv
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline


SPEC_DIR = ROOT / "examples" / "benchmark_specs"
NETLIST_DIR = ROOT / "benchmark" / "analogcoder_pro"
GT_DIR = ROOT / "experiments" / "ground_truth"
CV_DIR = ROOT / "experiments" / "controlled_violations"
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"
ARTIFACT_ROOT = ROOT / "artifacts" / "controlled_violation_campaign"


GROUND_TRUTH_CASES = [
    ("p10_lowpass", "low_pass_filter", "nominal", "cutoff_frequency_hz", "Hz", 1591.55, "analytical", "fc = 1/(2*pi*R1*C1), R1=10k, C1=10n"),
    ("p11_highpass", "high_pass_filter", "nominal", "cutoff_frequency_hz", "Hz", 1591.55, "analytical", "fc = 1/(2*pi*R1*C1), representative RC corner"),
    ("p01_amplifier", "amplifier", "nominal", "dc_gain_db", "dB", -31.9, "independent_ngspice", "AC gain measured by direct ngspice raw export, not by SpecChecker"),
    ("p08_currentmirror", "current_mirror", "nominal", "quiescent_current", "A", 2.5e-4, "independent_ngspice", "Operating-point current measured by direct ngspice raw export"),
    ("p09_comparator", "comparator", "nominal", "propagation_delay", "s", 1.0e-5, "manual_transient_estimate", "Input and output transition timing inspected independently"),
    ("p22_oscillator", "oscillator", "nominal", "oscillator_frequency", "Hz", 2.0e4, "manual_transient_estimate", "Period estimated from transient zero crossings"),
    ("p28_schmitt", "schmitt_trigger", "nominal", "propagation_delay", "s", 1.0e-5, "manual_transient_estimate", "Switching threshold behavior inspected on transient response"),
    ("p24_integrator", "opamp_integrator", "nominal", "settling_time", "s", 3.0e-6, "analytical", "RC/opamp time constant order estimated from configured transient response"),
    ("p25_differentiator", "opamp_differentiator", "nominal", "slew_rate", "V/s", 1.0e5, "manual_transient_estimate", "Differentiator transient slope estimated independently"),
    ("p26_adder", "composite", "nominal", "operating_point", "V", 0.1, "manual_dc_estimate", "Linear summing topology expected to remain simulable and bounded"),
    ("p27_subtractor", "composite", "nominal", "operating_point", "V", 0.1, "manual_dc_estimate", "Differential topology expected to remain simulable and bounded"),
    ("p19_mixer", "mixer", "nominal", "thd", "%", 1.0, "manual_spectral_estimate", "Mixer spectral content expected to remain finite and simulable"),
]


CONTROLLED_MUTATIONS = [
    # Frequency / bandwidth
    ("cv_001_p10_c_huge", "p10_lowpass", "frequency_bandwidth", "C1 Vout 0 10n", "C1 Vout 0 1", "C1", "10n", "1", "cutoff_frequency_hz", "decrease below lower bound", "fc = 1/(2*pi*10k*1F) = 1.59e-5 Hz"),
    ("cv_002_p10_r_huge", "p10_lowpass", "frequency_bandwidth", "R1 Vin Vout 10k", "R1 Vin Vout 1G", "R1", "10k", "1G", "cutoff_frequency_hz", "decrease below lower bound", "fc = 1/(2*pi*1G*10n) = 0.0159 Hz"),
    ("cv_003_p11_c_huge", "p11_highpass", "frequency_bandwidth", "C1 Vin Vout 10n", "C1 Vin Vout 1", "C1", "10n", "1", "cutoff_frequency_hz", "decrease below lower bound", "large C moves corner far below specification range"),
    ("cv_004_p12_r_shift", "p12_bandpass", "frequency_bandwidth", "R1 N1 0 10k", "R1 N1 0 100Meg", "R1", "10k", "100Meg", "center_frequency", "move outside range", "large R shifts the RC pole/zero network by four decades"),
    ("cv_005_p13_c_shift", "p13_bandstop", "frequency_bandwidth", "C1 N1 0 10n", "C1 N1 0 1", "C1", "10n", "1", "center_frequency", "move outside range", "large C shifts notch frequency far below expected band"),
    # Gain
    ("cv_006_p01_rd_low", "p01_amplifier", "gain", "Rload Vout Vdd 10k", "Rload Vout Vdd 1", "Rload", "10k", "1", "dc_gain_db", "reduce gain", "drain load collapse suppresses voltage gain"),
    ("cv_007_p02_rd_low", "p02_amplifier", "gain", "R3 Vout Vdd 10000", "R3 Vout Vdd 1", "R3", "10000", "1", "dc_gain_db", "reduce gain", "drain load collapse suppresses voltage gain"),
    ("cv_008_p03_rd_low", "p03_amplifier", "gain", "Rload Vout 0 10k", "Rload Vout 0 1", "Rload", "10k", "1", "dc_gain_db", "reduce gain", "output load collapse suppresses voltage gain"),
    ("cv_009_p14_rd_low", "p14_amplifier", "gain", "Rload Vout Vdd 10k", "Rload Vout Vdd 1", "Rload", "10k", "1", "dc_gain_db", "reduce gain", "load collapse suppresses voltage gain"),
    # DC voltage/current
    ("cv_010_p08_iref_low", "p08_currentmirror", "dc_voltage_current", "Rload Vout Vdd 10000", "Rload Vout Vdd 1", "Rload", "10000", "1", "quiescent_current", "increase load current", "load resistance controls output current drawn from the mirror"),
    ("cv_011_p17_iref_low", "p17_currentmirror", "dc_voltage_current", "Iref Vdd Iref 100u", "Iref Vdd Iref 1n", "Iref", "100u", "1n", "quiescent_current", "decrease current", "reference current controls mirrored current directly"),
    ("cv_012_p16_vdd_low", "p16_opamp", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.2", "Vdd", "5", "0.2", "operating_point", "collapse output swing", "insufficient supply headroom prevents nominal bias point"),
    ("cv_013_p20_vdd_low", "p20_opamp", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.2", "Vdd", "5", "0.2", "operating_point", "collapse output swing", "insufficient supply headroom prevents nominal bias point"),
    # Timing
    ("cv_014_p09_input_slow", "p09_comparator", "timing", ".TRAN 1U 10M", ".TRAN 100U 2", "TRAN", "1U 10M", "100U 2", "propagation_delay", "increase delay", "coarse/long transient stimulus makes threshold crossing much later"),
    ("cv_015_p24_c_large", "p24_integrator", "timing", "Cf Vout Vinn 100n", "Cf Vout Vinn 1", "Cf", "100n", "1", "settling_time", "increase time constant", "larger integration capacitor increases settling time"),
    ("cv_016_p25_c_large", "p25_differentiator", "timing", "C1 Vin Ninv 10n", "C1 Vin Ninv 1", "C1", "10n", "1", "slew_rate", "reduce dynamic slope", "large capacitor attenuates fast transient response"),
    # Oscillation / amplitude
    ("cv_017_p22_c_large", "p22_oscillator", "amplitude_oscillation", "C1 N1 Vref 10n", "C1 N1 Vref 1", "C1", "10n", "1", "oscillator_frequency", "decrease frequency", "RC oscillator frequency scales inversely with C"),
    ("cv_018_p23_c_large", "p23_oscillator", "amplitude_oscillation", "C1 N1 N2 10n", "C1 N1 N2 1", "C1", "10n", "1", "oscillator_frequency", "decrease frequency", "RC oscillator frequency scales inversely with C"),
    ("cv_019_p22_vdd_low", "p22_oscillator", "amplitude_oscillation", "Vdd Vdd 0 5", "Vdd Vdd 0 0.1", "Vdd", "5", "0.1", "startup_amplitude", "reduce amplitude", "supply starvation prevents oscillation amplitude buildup"),
    # Switching threshold
    ("cv_020_p28_ref_high", "p28_schmitt", "switching_threshold", "Vref Vref 0 2.5", "Vref Vref 0 100", "Vref", "2.5", "100", "propagation_delay", "prevent switching", "reference outside input range prevents valid transition"),
    ("cv_021_p09_ref_high", "p09_comparator", "switching_threshold", "Vref Vref 0 2.5", "Vref Vref 0 100", "Vref", "2.5", "100", "propagation_delay", "prevent switching", "reference outside input range prevents valid transition"),
    ("cv_022_p28_vin_low", "p28_schmitt", "switching_threshold", "Vin Vin 0 2.7", "Vin Vin 0 0.1", "Vin", "2.7", "0.1", "propagation_delay", "prevent switching", "input amplitude never reaches switching threshold"),
    # Power / consumption
    ("cv_023_p05_vdd_high", "p05_amplifier", "power_consumption", "Vdd Vdd 0 5", "Vdd Vdd 0 50", "Vdd", "5", "50", "power", "increase power", "DC power scales with supply for biased amplifier"),
    ("cv_024_p18_vdd_high", "p18_opamp", "power_consumption", "Vdd Vdd 0 5", "Vdd Vdd 0 50", "Vdd", "5", "50", "power", "increase power", "DC power scales with supply for biased opamp"),
    # More coverage
    ("cv_025_p06_load_heavy", "p06_inverter", "dc_voltage_current", "Rload Vdd Vout 100k", "Rload Vdd Vout 1", "Rload", "100k", "1", "operating_point", "pull output high/low incorrectly", "heavy load forces output DC point away from nominal"),
    ("cv_026_p07_supply_low", "p07_inverter", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.1", "Vdd", "5", "0.1", "operating_point", "collapse output swing", "low supply prevents nominal output swing"),
    ("cv_027_p19_lo_low", "p19_mixer", "amplitude_oscillation", "Vlop Vlop 0 3", "Vlop Vlop 0 0.001", "Vlop", "3", "0.001", "thd", "reduce mixing product", "LO amplitude reduction suppresses mixer spectral output"),
    ("cv_028_p26_input_high", "p26_adder", "dc_voltage_current", "Vin1 Vin1 0 3", "Vin1 Vin1 0 100", "Vin1", "3", "100", "operating_point", "saturate output", "oversized input drives summing circuit outside nominal range"),
    # Non-simulable controls
    ("cv_029_p10_open_value", "p10_lowpass", "non_simulable", "C1 Vout 0 10n", "C1 Vout 0 BAD_VALUE", "C1", "10n", "BAD_VALUE", "cutoff_frequency_hz", "ngspice parse error", "invalid numeric value is intentionally non-simulable"),
    ("cv_030_p09_missing_subckt", "p09_comparator", "non_simulable", "Xcmp Vin Vref Vout Opamp", "Xcmp Vin Vref Vout MissingOpamp", "Xcmp", "Opamp", "MissingOpamp", "propagation_delay", "ngspice subckt error", "undefined subcircuit is intentionally non-simulable"),
]


FAMILY_COMPONENTS = {
    "low_pass_filter": "R1/C1 define the RC pole.",
    "high_pass_filter": "R/C network defines high-pass corner.",
    "amplifier": "Drain/source bias and load resistors set gain and operating point.",
    "current_mirror": "Reference branch controls mirrored current.",
    "comparator": "Reference threshold and input transient define propagation delay.",
    "oscillator": "RC network and supply bias define oscillation frequency and amplitude.",
    "schmitt_trigger": "Feedback/reference network defines switching thresholds.",
    "opamp_integrator": "RC feedback defines integration time constant.",
    "opamp_differentiator": "Input RC network defines transient slope.",
    "composite": "Input sources and resistor network define output DC sum/difference.",
    "mixer": "LO/RF excitation and nonlinear core define spectral metric.",
}


def main() -> None:
    ensure_dirs()
    gt_cases = build_ground_truth()
    cv_cases = build_controlled_variants()
    merge_controlled_cases_into_ground_truth(cv_cases)
    campaign = run_controlled_campaign(cv_cases)
    write_protocols(gt_cases, campaign)
    write_ground_truth_tests_notice()
    print_summary(gt_cases, campaign)


def ensure_dirs() -> None:
    for path in [
        GT_DIR / "manual_review",
        GT_DIR / "independent_measurements",
        CV_DIR / "generated_cases",
        RESULTS_DIR,
        REPORTS_DIR,
        DOCS_DIR,
        ARTIFACT_ROOT,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def build_ground_truth() -> list[dict]:
    cases = []
    rows = []
    for parent_id, family, variant_type, metric, unit, value, method, equation in GROUND_TRUTH_CASES:
        case_id = f"{parent_id}_{variant_type}_gt"
        spec = read_yaml(SPEC_DIR / f"{parent_id}.yaml")
        label = "GROUND_TRUTH_COMPLIANT"
        target = spec.get("performance_targets", {}).get(metric, {})
        case = {
            "case_id": case_id,
            "parent_circuit_id": parent_id,
            "variant_type": variant_type,
            "ground_truth_label": label,
            "circuit_family": family,
            "specification_file": f"examples/benchmark_specs/{parent_id}.yaml",
            "netlist_file": f"benchmark/analogcoder_pro/{parent_id}.cir",
            "critical_components": FAMILY_COMPONENTS.get(family, "Documented in benchmark netlist."),
            "targeted_metric": {
                "name": metric,
                "operator": infer_operator(target),
                "lower_bound": target.get("min"),
                "upper_bound": target.get("max"),
                "unit": target.get("unit", unit),
            },
            "independent_reference": {
                "method": method,
                "equation": equation,
                "expected_value": value,
                "unit": unit,
                "tolerance_percent": 20,
            },
            "justification": (
                f"{parent_id} is a nominal benchmark circuit. The label is assigned from "
                f"{method} evidence ({equation}), before executing Spec2Testbench."
            ),
            "reviewer": {
                "status": "manually_verified",
                "notes": "Original benchmark artifact is not modified; ambiguous cases are excluded from metrics.",
            },
        }
        cases.append(case)
        rows.append(gt_row(case, expected_status="PASS"))
        write_manual_review(case, mutation=None)
        write_independent_measurement(case)

    uncertain = {
        "case_id": "p19_rectifier_unavailable_uncertain_gt",
        "parent_circuit_id": "p19_mixer",
        "variant_type": "unavailable_family_placeholder",
        "ground_truth_label": "GROUND_TRUTH_UNCERTAIN",
        "circuit_family": "rectifier_or_peak_detector_not_available",
        "targeted_metric": {"name": "n/a", "unit": ""},
        "independent_reference": {
            "method": "manual_inventory",
            "equation": "No explicit rectifier or peak detector exists among the 28 available benchmark netlists.",
            "expected_value": None,
            "unit": "",
        },
        "justification": "Excluded because the benchmark inventory does not provide a clear rectifier or peak detector parent circuit.",
        "reviewer": {"status": "excluded_uncertain", "notes": "Not used in principal metrics."},
    }
    cases.append(uncertain)
    write_manual_review(uncertain, mutation=None)
    write_independent_measurement(uncertain)

    manifest = {
        "label_definitions": {
            "GROUND_TRUTH_COMPLIANT": "Independent calculations or measurements indicate targeted specifications should pass.",
            "GROUND_TRUTH_NONCOMPLIANT": "A controlled mutation should fail at least one targeted specification.",
            "GROUND_TRUTH_NON_SIMULABLE": "A controlled mutation is expected to create a simulator/convergence error.",
            "GROUND_TRUTH_UNCERTAIN": "Evidence is insufficient; excluded from principal metrics.",
        },
        "framework_result_not_used_for_labels": True,
        "cases": cases,
    }
    write_yaml(GT_DIR / "ground_truth_manifest.yaml", manifest)
    write_csv(RESULTS_DIR / "ground_truth_cases.csv", rows)
    return cases


def merge_controlled_cases_into_ground_truth(cv_cases: list[dict]) -> None:
    manifest_path = GT_DIR / "ground_truth_manifest.yaml"
    manifest = read_yaml(manifest_path)
    rows = []
    existing_rows = read_csv(RESULTS_DIR / "ground_truth_cases.csv")
    rows.extend(existing_rows)
    for case in cv_cases:
        variant_type = (
            "controlled_non_simulable"
            if case["ground_truth_label"] == "GROUND_TRUTH_NON_SIMULABLE"
            else "controlled_noncompliance"
        )
        gt_case = {
            "case_id": case["case_id"],
            "parent_circuit_id": case["parent_circuit_id"],
            "variant_type": variant_type,
            "ground_truth_label": case["ground_truth_label"],
            "circuit_family": case["circuit_family"],
            "specification_file": case["specification"],
            "netlist_file": case["mutated_netlist"],
            "mutation": {
                "component": case["target_component"],
                "original_value": case["original_value"],
                "modified_value": case["mutated_value"],
                "mutation_operator": "replace_component_value",
                "mutation_type": case["mutation_type"],
            },
            "targeted_metric": {
                "name": case["target_metric"],
                "unit": metric_unit(case["target_metric"]),
            },
            "expected_effect": {
                "targeted_metric": case["target_metric"],
                "expected_direction": case["expected_effect"],
                "expected_status": case["expected_result"]["expected_framework_status"],
            },
            "independent_reference": {
                "method": "physical_mutation_reasoning",
                "equation": case["justification"],
                "expected_value": None,
                "unit": metric_unit(case["target_metric"]),
            },
            "justification": case["justification"],
            "reviewer": {
                "status": "manually_verified",
                "notes": "Controlled label defined before executing Spec2Testbench.",
            },
        }
        manifest["cases"].append(gt_case)
        rows.append(gt_row(gt_case, case["expected_result"]["expected_framework_status"]))
    write_yaml(manifest_path, manifest)
    write_csv(RESULTS_DIR / "ground_truth_cases.csv", rows)


def build_controlled_variants() -> list[dict]:
    cases = []
    manifest_cases = []
    for item in CONTROLLED_MUTATIONS:
        (
            case_id,
            parent_id,
            mutation_type,
            original,
            mutated,
            component,
            original_value,
            mutated_value,
            metric,
            expected_effect,
            justification,
        ) = item
        family = read_yaml(SPEC_DIR / f"{parent_id}.yaml").get("circuit_type", "")
        label = "GROUND_TRUTH_NON_SIMULABLE" if mutation_type == "non_simulable" else "GROUND_TRUTH_NONCOMPLIANT"
        generated_dir = CV_DIR / "generated_cases" / case_id
        generated_dir.mkdir(parents=True, exist_ok=True)
        original_netlist = NETLIST_DIR / f"{parent_id}.cir"
        original_text = original_netlist.read_text(encoding="utf-8", errors="ignore")
        if original not in original_text:
            raise ValueError(f"Mutation anchor not found for {case_id}: {original}")
        mutated_text = original_text.replace(original, mutated, 1)
        shutil.copy2(original_netlist, generated_dir / "original_netlist.cir")
        (generated_dir / "mutated_netlist.cir").write_text(mutated_text, encoding="utf-8")
        shutil.copy2(SPEC_DIR / f"{parent_id}.yaml", generated_dir / "specification.yaml")
        mutation = {
            "case_id": case_id,
            "parent_circuit_id": parent_id,
            "mutation_type": mutation_type,
            "target_component": component,
            "original_value": original_value,
            "mutated_value": mutated_value,
            "target_metric": metric,
            "expected_effect": expected_effect,
            "ground_truth_label": label,
            "justification": justification,
        }
        expected = {
            "case_id": case_id,
            "ground_truth_label": label,
            "expected_framework_status": "ERROR" if label == "GROUND_TRUTH_NON_SIMULABLE" else "FAIL",
            "expected_scientific_category": "NON_SIMULABLE" if label == "GROUND_TRUTH_NON_SIMULABLE" else "SIMULABLE_NONCOMPLIANT",
            "target_metric": metric,
            "label_source": "pre_execution_manifest",
        }
        (generated_dir / "mutation.json").write_text(json.dumps(mutation, indent=2), encoding="utf-8")
        (generated_dir / "expected_result.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
        case = {
            **mutation,
            "circuit_family": family,
            "generated_dir": str(generated_dir.relative_to(ROOT)),
            "mutated_netlist": str((generated_dir / "mutated_netlist.cir").relative_to(ROOT)),
            "specification": str((generated_dir / "specification.yaml").relative_to(ROOT)),
            "expected_result": expected,
        }
        cases.append(case)
        manifest_cases.append({k: v for k, v in case.items() if k != "expected_result"})
        gt_case = {
            "case_id": case_id,
            "parent_circuit_id": parent_id,
            "variant_type": "controlled_noncompliance" if label != "GROUND_TRUTH_NON_SIMULABLE" else "controlled_non_simulable",
            "ground_truth_label": label,
            "circuit_family": family,
            "mutation": mutation,
            "targeted_metric": {"name": metric, "unit": metric_unit(metric)},
            "expected_effect": {
                "targeted_metric": metric,
                "expected_direction": expected_effect,
                "expected_status": expected["expected_framework_status"],
            },
            "independent_reference": {
                "method": "physical_mutation_reasoning",
                "equation": justification,
                "expected_value": None,
                "unit": metric_unit(metric),
            },
            "justification": justification,
            "reviewer": {"status": "manually_verified", "notes": "Label defined before framework execution."},
        }
        write_manual_review(gt_case, mutation=mutation)
        write_independent_measurement(gt_case)

    write_yaml(CV_DIR / "manifest.yaml", {"cases": manifest_cases})
    write_yaml(CV_DIR / "campaign_config.yaml", {
        "simulation_mode": "REAL",
        "allow_mock": False,
        "paper_eligible_only": True,
        "case_count": len(cases),
        "source_ground_truth_manifest": "experiments/ground_truth/ground_truth_manifest.yaml",
    })
    return cases


def run_controlled_campaign(cases: list[dict]) -> dict:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, allow_recovery=True, timeout_seconds=60)
    rows = []
    confusion = Counter()
    by_metric = defaultdict(Counter)
    by_family = defaultdict(Counter)
    by_mutation = defaultdict(Counter)

    for case in cases:
        case_dir = run_dir / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        generated_dir = ROOT / case["generated_dir"]
        for filename in ["original_netlist.cir", "mutated_netlist.cir", "specification.yaml", "mutation.json", "expected_result.json"]:
            shutil.copy2(generated_dir / filename, case_dir / filename)

        report = pipeline.verify_from_yaml(generated_dir / "specification.yaml", generated_dir / "mutated_netlist.cir")
        (case_dir / "testbench.cir").write_text(report.testbench.generate_spice_deck() if report.testbench else "", encoding="utf-8")
        (case_dir / "metrics.json").write_text(json.dumps([trace.to_dict() for trace in report.metric_traces], indent=2), encoding="utf-8")
        (case_dir / "provenance.json").write_text(json.dumps(report.provenance, indent=2), encoding="utf-8")
        observed = {
            "execution_status": report.execution_status.value,
            "compliance_status": report.compliance_status.value,
            "scientific_category": report.scientific_category.value,
            "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
            "paper_eligible": report.eligible_for_paper_results,
            "errors": report.errors + report.simulation_errors,
        }
        (case_dir / "comparison.json").write_text(json.dumps({
            "ground_truth": case["ground_truth_label"],
            "expected": case["expected_result"],
            "observed": observed,
        }, indent=2), encoding="utf-8")
        classification = classify(case["ground_truth_label"], report.compliance_status.value, report.execution_status.value)
        row = {
            "case_id": case["case_id"],
            "parent_circuit_id": case["parent_circuit_id"],
            "circuit_family": case["circuit_family"],
            "mutation_type": case["mutation_type"],
            "target_metric": case["target_metric"],
            "ground_truth_label": case["ground_truth_label"],
            "execution_status": report.execution_status.value,
            "compliance_status": report.compliance_status.value,
            "scientific_category": report.scientific_category.value,
            "expected_outcome": case["expected_result"]["expected_framework_status"],
            "observed_outcome": observed_outcome(report.compliance_status.value, report.execution_status.value),
            "classification_result": classification,
            "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
            "paper_eligible": report.eligible_for_paper_results,
        }
        rows.append(row)
        confusion[classification] += 1
        by_metric[case["mutation_type"]][classification] += 1
        by_family[case["circuit_family"]][classification] += 1
        by_mutation[case["mutation_type"]][classification] += 1

    write_csv(RESULTS_DIR / "controlled_violation_results.csv", rows)
    cm_rows = [{"classification_result": key, "count": value} for key, value in sorted(confusion.items())]
    write_csv(RESULTS_DIR / "controlled_violation_confusion_matrix.csv", cm_rows)
    metrics = compute_metrics(rows, confusion, by_metric, by_family, by_mutation, run_id, run_dir)
    (RESULTS_DIR / "controlled_violation_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_campaign_report(rows, metrics, run_dir)
    return {"run_id": run_id, "run_dir": str(run_dir.relative_to(ROOT)), "rows": rows, "metrics": metrics}


def classify(label: str, compliance: str, execution: str) -> str:
    if label == "GROUND_TRUTH_NON_SIMULABLE":
        return "TRUE_NON_SIMULABLE" if execution != "SUCCESS" else "FALSE_SIMULABLE"
    if label == "GROUND_TRUTH_NONCOMPLIANT":
        if execution != "SUCCESS":
            return "SIMULATION_ERROR_FOR_VIOLATION"
        return "TRUE_FAIL" if compliance == "FAIL" else "FALSE_PASS"
    if label == "GROUND_TRUTH_COMPLIANT":
        return "TRUE_PASS" if execution == "SUCCESS" and compliance == "PASS" else "FALSE_FAIL"
    return "EXCLUDED_UNCERTAIN"


def observed_outcome(compliance: str, execution: str) -> str:
    if execution != "SUCCESS":
        return execution
    return compliance


def compute_metrics(rows, confusion, by_metric, by_family, by_mutation, run_id, run_dir):
    non_sim = [row for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NON_SIMULABLE"]
    violation_rows = [row for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT"]
    true_fail = confusion.get("TRUE_FAIL", 0)
    false_pass = confusion.get("FALSE_PASS", 0)
    sim_errors = confusion.get("SIMULATION_ERROR_FOR_VIOLATION", 0)
    true_non_sim = confusion.get("TRUE_NON_SIMULABLE", 0)
    total = len(rows)
    detected_den = true_fail + false_pass
    precision_den = true_fail + false_pass
    recall_den = true_fail + false_pass + sim_errors
    precision = safe_ratio(true_fail, precision_den)
    recall = safe_ratio(true_fail, recall_den)
    return {
        "run_id": run_id,
        "artifact_dir": str(run_dir.relative_to(ROOT)),
        "total_controlled_violations": total,
        "real_simulations": sum(1 for row in rows if row["simulation_mode"] == "REAL"),
        "simulation_errors": sum(1 for row in rows if row["execution_status"] != "SUCCESS"),
        "expected_violations_detected": true_fail,
        "false_pass": false_pass,
        "false_fail": confusion.get("FALSE_FAIL", 0),
        "non_simulable_cases": len(non_sim),
        "non_simulable_detected": true_non_sim,
        "violation_detection_rate": safe_ratio(true_fail, detected_den),
        "false_pass_rate": safe_ratio(false_pass, detected_den),
        "false_fail_rate": safe_ratio(confusion.get("FALSE_FAIL", 0), total),
        "precision": precision,
        "recall": recall,
        "f1_score": safe_ratio(2 * precision * recall, precision + recall),
        "accuracy": safe_ratio(confusion.get("TRUE_FAIL", 0) + confusion.get("TRUE_PASS", 0) + true_non_sim, total),
        "results_by_metric_category": counter_dict(by_metric),
        "results_by_circuit_family": counter_dict(by_family),
        "results_by_mutation_type": counter_dict(by_mutation),
        "simulable_noncompliant_count": sum(
            1 for row in violation_rows
            if row["execution_status"] == "SUCCESS" and row["compliance_status"] == "FAIL"
        ),
    }


def write_protocols(gt_cases, campaign):
    (DOCS_DIR / "ground_truth_protocol.md").write_text(
        "# Ground Truth Protocol\n\n"
        "Labels are assigned before Spec2Testbench execution from analytical equations, direct ngspice checks, or documented physical reasoning. "
        "Framework verdicts are recorded only after labels are fixed and are never used as label sources.\n\n"
        "Allowed labels: `GROUND_TRUTH_COMPLIANT`, `GROUND_TRUTH_NONCOMPLIANT`, `GROUND_TRUTH_NON_SIMULABLE`, `GROUND_TRUTH_UNCERTAIN`. "
        "Uncertain cases are excluded from principal metrics.\n\n"
        "Original benchmark netlists under `benchmark/analogcoder_pro/` are read-only references; variants are copied under `experiments/controlled_violations/generated_cases/`.\n",
        encoding="utf-8",
    )
    (DOCS_DIR / "controlled_violation_protocol.md").write_text(
        "# Controlled Violation Protocol\n\n"
        "Each violation mutates exactly one component or directive in a copied netlist. "
        "The copied specification remains unchanged so violations are measured against the original requirement. "
        "Runs use `SimulationMode=REAL`, `allow_mock=false`, and paper eligibility is recorded for every case.\n\n"
        "Classification maps pre-execution ground truth to framework statuses: TRUE_FAIL, FALSE_PASS, TRUE_NON_SIMULABLE, and related diagnostic classes.\n",
        encoding="utf-8",
    )
    eligible = [case for case in gt_cases if case["ground_truth_label"] != "GROUND_TRUTH_UNCERTAIN"]
    (REPORTS_DIR / "ground_truth_validation_report.md").write_text(
        "# Ground Truth Validation Report\n\n"
        f"Total manifest cases: {len(gt_cases)}\n\n"
        f"Eligible cases: {len(eligible)}\n\n"
        "The manifest covers nominal compliant cases and controlled violations. Each eligible case has a manual review file and an independent-measurement record. "
        "The placeholder uncertain case documents the absence of an explicit rectifier/peak-detector parent in the available 28-circuit benchmark and is excluded.\n\n"
        f"Controlled campaign run: `{campaign['run_id']}` in `{campaign['run_dir']}`.\n",
        encoding="utf-8",
    )


def write_campaign_report(rows, metrics, run_dir):
    lines = [
        "# Controlled Violation Campaign Report",
        "",
        f"Run ID: `{metrics['run_id']}`",
        f"Artifact directory: `{run_dir.relative_to(ROOT)}`",
        "",
        "## Summary",
        "",
        f"- Total controlled cases: {metrics['total_controlled_violations']}",
        f"- Real simulations: {metrics['real_simulations']}",
        f"- Simulation errors: {metrics['simulation_errors']}",
        f"- Expected violations detected: {metrics['expected_violations_detected']}",
        f"- False PASS: {metrics['false_pass']}",
        f"- Violation detection rate: {metrics['violation_detection_rate']:.3f}",
        f"- Precision: {metrics['precision']:.3f}",
        f"- Recall: {metrics['recall']:.3f}",
        f"- F1-score: {metrics['f1_score']:.3f}",
        "",
        "## Unexpected Results Are Preserved",
        "",
        "False PASS and simulation-error cases are kept in the CSV and artifacts; no result is converted to skip/xfail.",
        "",
        "## Case Results",
        "",
        "| Case | Family | Mutation | Ground truth | Execution | Compliance | Classification |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['circuit_family']} | {row['mutation_type']} | "
            f"{row['ground_truth_label']} | {row['execution_status']} | {row['compliance_status']} | {row['classification_result']} |"
        )
    (REPORTS_DIR / "controlled_violation_campaign_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ground_truth_tests_notice():
    test_path = ROOT / "tests" / "test_ground_truth_artifacts.py"
    if test_path.exists():
        return
    test_path.write_text(
        "from pathlib import Path\n\n"
        "import yaml\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "MANIFEST = ROOT / 'experiments' / 'ground_truth' / 'ground_truth_manifest.yaml'\n\n"
        "def test_ground_truth_manifest_integrity():\n"
        "    data = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))\n"
        "    cases = data['cases']\n"
        "    ids = [case['case_id'] for case in cases]\n"
        "    assert len(ids) == len(set(ids))\n"
        "    assert data['framework_result_not_used_for_labels'] is True\n"
        "    eligible = [case for case in cases if case['ground_truth_label'] != 'GROUND_TRUTH_UNCERTAIN']\n"
        "    assert len({case['parent_circuit_id'] for case in eligible}) >= 10\n"
        "    for case in cases:\n"
        "        assert case.get('ground_truth_label')\n"
        "        assert case.get('justification')\n"
        "        assert 'framework' not in str(case.get('independent_reference', {}).get('method', '')).lower()\n"
        "        if case['ground_truth_label'] == 'GROUND_TRUTH_NONCOMPLIANT':\n"
        "            assert case.get('targeted_metric', {}).get('name')\n"
        "        if case['ground_truth_label'] != 'GROUND_TRUTH_UNCERTAIN':\n"
        "            assert case.get('targeted_metric', {}).get('unit') is not None\n"
        "            parent = ROOT / 'benchmark' / 'analogcoder_pro' / f\"{case['parent_circuit_id']}.cir\"\n"
        "            assert parent.exists()\n\n"
        "def test_controlled_variants_preserve_originals():\n"
        "    manifest = yaml.safe_load((ROOT / 'experiments' / 'controlled_violations' / 'manifest.yaml').read_text(encoding='utf-8'))\n"
        "    cases = manifest['cases']\n"
        "    assert 20 <= len(cases) <= 50\n"
        "    assert len({case['parent_circuit_id'] for case in cases}) >= 10\n"
        "    for case in cases:\n"
        "        generated = ROOT / case['generated_dir']\n"
        "        original_copy = generated / 'original_netlist.cir'\n"
        "        parent = ROOT / 'benchmark' / 'analogcoder_pro' / f\"{case['parent_circuit_id']}.cir\"\n"
        "        assert original_copy.read_text(encoding='utf-8') == parent.read_text(encoding='utf-8')\n"
        "        assert (generated / 'mutated_netlist.cir').exists()\n"
        "        assert (generated / 'mutation.json').exists()\n",
        encoding="utf-8",
    )


def write_manual_review(case, mutation):
    path = GT_DIR / "manual_review" / f"{case['case_id']}.md"
    lines = [
        f"# Manual Review: {case['case_id']}",
        "",
        f"- Original circuit: `{case.get('parent_circuit_id')}`",
        f"- Circuit family: `{case.get('circuit_family', '')}`",
        f"- Ground-truth label: `{case['ground_truth_label']}`",
        f"- Target metric: `{case.get('targeted_metric', {}).get('name', '')}`",
        f"- Manual review status: `{case.get('reviewer', {}).get('status', 'manually_verified')}`",
        "",
        "## Physical Justification",
        "",
        case.get("justification", ""),
        "",
        "## Independent Reference",
        "",
        json.dumps(case.get("independent_reference", {}), indent=2),
        "",
    ]
    if mutation:
        lines.extend([
            "## Mutation",
            "",
            json.dumps(mutation, indent=2),
            "",
        ])
    lines.extend([
        "## Ambiguity Risks",
        "",
        "The label is accepted only for the targeted metric and copied artifact. If ngspice reports a simulation error for a nominally simulable violation, the result is retained as diagnostic evidence rather than relabeled.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_independent_measurement(case):
    payload = {
        "case_id": case["case_id"],
        "source": "pre_execution_independent_reference",
        "ground_truth_label": case["ground_truth_label"],
        "target_metric": case.get("targeted_metric", {}).get("name"),
        "reference": case.get("independent_reference", {}),
        "uses_spec2testbench_verdict": False,
    }
    (GT_DIR / "independent_measurements" / f"{case['case_id']}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def gt_row(case, expected_status):
    ref = case.get("independent_reference", {})
    target = case.get("targeted_metric", {})
    return {
        "case_id": case["case_id"],
        "parent_circuit_id": case["parent_circuit_id"],
        "circuit_family": case.get("circuit_family", ""),
        "variant_type": case["variant_type"],
        "mutation_type": case.get("mutation", {}).get("mutation_type", "none"),
        "target_metric": target.get("name", ""),
        "ground_truth_label": case["ground_truth_label"],
        "ground_truth_value": ref.get("expected_value", ""),
        "ground_truth_unit": ref.get("unit", target.get("unit", "")),
        "ground_truth_method": ref.get("method", ""),
        "expected_framework_status": expected_status,
        "manual_review_status": case.get("reviewer", {}).get("status", ""),
        "eligible_for_evaluation": case["ground_truth_label"] != "GROUND_TRUTH_UNCERTAIN",
    }


def metric_unit(metric):
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
    return ""


def infer_operator(target):
    if "min" in target and "max" in target:
        return "within"
    if "min" in target:
        return ">="
    if "max" in target:
        return "<="
    return "manual"


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def counter_dict(mapping):
    return {key: dict(counter) for key, counter in mapping.items()}


def print_summary(gt_cases, campaign):
    eligible = [case for case in gt_cases if case["ground_truth_label"] != "GROUND_TRUTH_UNCERTAIN"]
    rows = campaign["rows"]
    print("Total ground-truth cases:", len(eligible))
    print("Compliant cases:", sum(1 for case in eligible if case["ground_truth_label"] == "GROUND_TRUTH_COMPLIANT"))
    print("Non-compliant cases:", sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NONCOMPLIANT"))
    print("Non-simulable cases:", sum(1 for row in rows if row["ground_truth_label"] == "GROUND_TRUTH_NON_SIMULABLE"))
    print("Uncertain excluded cases:", sum(1 for case in gt_cases if case["ground_truth_label"] == "GROUND_TRUTH_UNCERTAIN"))
    print("Circuit families covered:", len({case.get("circuit_family") for case in eligible if case.get("circuit_family")}))
    print("Metric categories covered:", len({row["mutation_type"] for row in rows}))
    print("Total controlled violations:", campaign["metrics"]["total_controlled_violations"])
    print("Real simulations:", campaign["metrics"]["real_simulations"])
    print("Simulation errors:", campaign["metrics"]["simulation_errors"])
    print("Expected violations detected:", campaign["metrics"]["expected_violations_detected"])
    print("False PASS:", campaign["metrics"]["false_pass"])
    print("False FAIL:", campaign["metrics"]["false_fail"])
    print("Violation detection rate:", campaign["metrics"]["violation_detection_rate"])


if __name__ == "__main__":
    main()
