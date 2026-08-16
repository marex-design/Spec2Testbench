from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DUT_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "benchmark" / "analogcoder_pro" / "specs"
OUT_ROOT = ROOT / "experiments" / "controlled_violations"

# Only mutations whose anchor is an ACTIVE DUT line in the canonical ACP-28 deck.
# Source/protocol mutations that only matched provenance comments in v0.4.0 were removed.
CONTROLLED_MUTATIONS = [
    # case_id, parent, type, active line before, active line after, component, metric, expected class, rationale
    ("cv_001_p10_c_huge", "p10_lowpass", "frequency_bandwidth", "C1 Vout 0 10n", "C1 Vout 0 1", "C1", "cutoff_frequency_hz", "GROUND_TRUTH_NONCOMPLIANT", "First-order RC cutoff moves far below the accepted band."),
    ("cv_002_p10_r_huge", "p10_lowpass", "frequency_bandwidth", "R1 Vin Vout 10k", "R1 Vin Vout 1G", "R1", "cutoff_frequency_hz", "GROUND_TRUTH_NONCOMPLIANT", "First-order RC cutoff moves far below the accepted band."),
    ("cv_003_p11_c_huge", "p11_highpass", "frequency_bandwidth", "C1 Vin Vout 10n", "C1 Vin Vout 1", "C1", "cutoff_frequency_hz", "GROUND_TRUTH_NONCOMPLIANT", "High-pass corner moves far below the accepted band."),
    ("cv_004_p12_r_shift", "p12_bandpass", "frequency_bandwidth", "R1 N1 0 10k", "R1 N1 0 100Meg", "R1", "center_frequency", "GROUND_TRUTH_NONCOMPLIANT", "Large resistance shifts the pole/zero network by orders of magnitude."),
    ("cv_005_p13_c_shift", "p13_bandstop", "frequency_bandwidth", "C1 N1 0 10n", "C1 N1 0 1", "C1", "center_frequency", "GROUND_TRUTH_NONCOMPLIANT", "Large capacitance shifts the notch frequency by orders of magnitude."),
    ("cv_006_p01_rd_low", "p01_amplifier", "gain", "Rload Vout Vdd 10k", "Rload Vout Vdd 1", "Rload", "dc_gain_db", "GROUND_TRUTH_NONCOMPLIANT", "Drain load collapse suppresses voltage gain."),
    ("cv_007_p02_rd_low", "p02_amplifier", "gain", "R3 Vout Vdd 10000", "R3 Vout Vdd 1", "R3", "dc_gain_db", "GROUND_TRUTH_NONCOMPLIANT", "Drain load collapse suppresses voltage gain."),
    ("cv_008_p03_rd_low", "p03_amplifier", "gain", "Rload Vout 0 10k", "Rload Vout 0 1", "Rload", "dc_gain_db", "GROUND_TRUTH_NONCOMPLIANT", "Output load collapse suppresses voltage gain."),
    ("cv_009_p14_rd_low", "p14_amplifier", "gain", "Rload Vout Vdd 10k", "Rload Vout Vdd 1", "Rload", "dc_gain_db", "GROUND_TRUTH_NONCOMPLIANT", "Load collapse suppresses voltage gain."),
    ("cv_010_p08_iref_low", "p08_currentmirror", "dc_voltage_current", "Rload Vout Vdd 10000", "Rload Vout Vdd 1", "Rload", "quiescent_current", "GROUND_TRUTH_NONCOMPLIANT", "Severe output load mutation moves the mirror outside its intended load regime."),
    ("cv_011_p17_iref_low", "p17_currentmirror", "dc_voltage_current", "Iref Vdd Iref 100u", "Iref Vdd Iref 1n", "Iref", "quiescent_current", "GROUND_TRUTH_NONCOMPLIANT", "Reference current is reduced by five orders of magnitude."),
    ("cv_012_p16_vdd_low", "p16_opamp", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.2", "Vdd", "operating_point", "GROUND_TRUTH_NONCOMPLIANT", "Insufficient supply headroom prevents nominal bias and swing."),
    ("cv_013_p20_vdd_low", "p20_opamp", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.2", "Vdd", "operating_point", "GROUND_TRUTH_NONCOMPLIANT", "Insufficient supply headroom prevents nominal bias and swing."),
    ("cv_015_p24_c_large", "p24_integrator", "timing", "Cf Vout Vinn 100n", "Cf Vout Vinn 1", "Cf", "settling_time", "GROUND_TRUTH_NONCOMPLIANT", "Integration time constant is increased by seven orders of magnitude."),
    ("cv_016_p25_c_large", "p25_differentiator", "timing", "C1 Vin Ninv 10n", "C1 Vin Ninv 1", "C1", "slew_rate", "GROUND_TRUTH_NONCOMPLIANT", "Input time constant is increased by eight orders of magnitude."),
    ("cv_017_p22_c_large", "p22_oscillator", "amplitude_oscillation", "C1 N1 Vref 10n", "C1 N1 Vref 1", "C1", "oscillator_frequency", "GROUND_TRUTH_NONCOMPLIANT", "RC oscillator frequency scales inversely with capacitance."),
    ("cv_018_p23_c_large", "p23_oscillator", "amplitude_oscillation", "C1 N1 N2 10n", "C1 N1 N2 1", "C1", "oscillator_frequency", "GROUND_TRUTH_NONCOMPLIANT", "Ring/RC timing is shifted by orders of magnitude."),
    ("cv_019_p22_vdd_low", "p22_oscillator", "amplitude_oscillation", "Vdd Vdd 0 5", "Vdd Vdd 0 0.1", "Vdd", "startup_amplitude", "GROUND_TRUTH_NONCOMPLIANT", "Op-amp supply starvation prevents normal oscillation amplitude buildup."),
    ("cv_020_p28_ref_high", "p28_schmitt", "switching_threshold", "Vref Vref 0 2.5", "Vref Vref 0 100", "Vref", "hysteresis_width", "GROUND_TRUTH_NONCOMPLIANT", "Reference is placed far outside the usable input/output range."),
    ("cv_021_p09_ref_high", "p09_comparator", "switching_threshold", "Vref Vref 0 2.5", "Vref Vref 0 100", "Vref", "comparator_output_separation_v", "GROUND_TRUTH_NONCOMPLIANT", "Reference is placed far outside the usable input range."),
    ("cv_023_p05_vdd_high", "p05_amplifier", "power_consumption", "Vdd Vdd 0 5", "Vdd Vdd 0 50", "Vdd", "power", "GROUND_TRUTH_NONCOMPLIANT", "Supply is increased tenfold, invalidating the intended power/operating regime."),
    ("cv_024_p18_vdd_high", "p18_opamp", "power_consumption", "Vdd Vdd 0 5", "Vdd Vdd 0 50", "Vdd", "power", "GROUND_TRUTH_NONCOMPLIANT", "Supply is increased tenfold, invalidating the intended power/operating regime."),
    ("cv_025_p06_load_heavy", "p06_inverter", "dc_voltage_current", "Rload Vdd Vout 100k", "Rload Vdd Vout 1", "Rload", "inverter_output_swing_v", "GROUND_TRUTH_NONCOMPLIANT", "A one-ohm load prevents normal inverter output swing."),
    ("cv_026_p07_supply_low", "p07_inverter", "dc_voltage_current", "Vdd Vdd 0 5", "Vdd Vdd 0 0.1", "Vdd", "inverter_output_swing_v", "GROUND_TRUTH_NONCOMPLIANT", "Supply starvation prevents nominal output swing."),
    ("cv_029_p10_bad_value", "p10_lowpass", "non_simulable", "C1 Vout 0 10n", "C1 Vout 0 BAD_VALUE", "C1", "cutoff_frequency_hz", "GROUND_TRUTH_NON_SIMULABLE", "An invalid numeric value must cause a simulator/parser error."),
    ("cv_030_p09_missing_subckt", "p09_comparator", "non_simulable", "Xcmp Vin Vref Vout Opamp", "Xcmp Vin Vref Vout MissingOpamp", "Xcmp", "comparator_output_separation_v", "GROUND_TRUTH_NON_SIMULABLE", "An undefined subcircuit must cause a simulator error."),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutate_active_line(text: str, before: str, after: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    active_matches = [i for i, line in enumerate(lines) if line.strip() == before and not line.lstrip().startswith("*")]
    if not active_matches:
        raise ValueError(f"Active mutation anchor not found: {before}")
    idx = active_matches[0]
    ending = "\n" if lines[idx].endswith("\n") else ""
    lines[idx] = after + ending
    return "".join(lines), len(active_matches)


def materialize(*, clean: bool = True) -> dict[str, Any]:
    cases_root = OUT_ROOT / "cases"
    if clean and cases_root.exists():
        shutil.rmtree(cases_root)
    cases_root.mkdir(parents=True, exist_ok=True)
    manifest_cases = []
    for case_id, parent, mutation_type, before, after, component, metric, label, rationale in CONTROLLED_MUTATIONS:
        source = DUT_DIR / f"{parent}.cir"
        if not source.exists():
            raise FileNotFoundError(source)
        source_text = source.read_text(encoding="utf-8", errors="strict")
        mutated_text, active_match_count = mutate_active_line(source_text, before, after)
        case_dir = cases_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        original_copy = case_dir / "original_netlist.cir"
        mutated = case_dir / "mutated_netlist.cir"
        spec_copy = case_dir / "specification.yaml"
        shutil.copy2(source, original_copy)
        mutated.write_text(mutated_text, encoding="utf-8")
        original_hash = sha256(original_copy)
        mutated_hash = sha256(mutated)
        canonical_spec = SPEC_DIR / f"{parent}.yaml"
        if canonical_spec.exists():
            spec_data = yaml.safe_load(canonical_spec.read_text(encoding="utf-8-sig"))
            if isinstance(spec_data, dict):
                provenance = spec_data.get("provenance")
                if isinstance(provenance, dict) and isinstance(provenance.get("dut"), dict):
                    provenance["dut"]["path"] = mutated.relative_to(ROOT).as_posix()
                    provenance["dut"]["sha256"] = mutated_hash
                    provenance["dut"]["canonicalization"] = (
                        str(provenance["dut"].get("canonicalization", ""))
                        + "; controlled active-line mutation for ground-truth stress testing."
                    ).strip("; ")
                spec_data["case_id"] = case_id
                # parent_circuit_id is a runtime compatibility field, not part of strict v2 schema.
                spec_copy.write_text(yaml.safe_dump(spec_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        if original_hash == mutated_hash:
            raise RuntimeError(f"Mutation did not change bytes for {case_id}")
        metadata = {
            "case_id": case_id,
            "parent_circuit_id": parent,
            "mutation_type": mutation_type,
            "target_component": component,
            "target_metric": metric,
            "ground_truth_label": label,
            "line_before": before,
            "line_after": after,
            "rationale": rationale,
            "active_anchor_match_count": active_match_count,
            "original_sha256": original_hash,
            "mutated_sha256": mutated_hash,
            "effective_mutation": True,
            "original_dut": source.relative_to(ROOT).as_posix(),
            "mutated_netlist": mutated.relative_to(ROOT).as_posix(),
            "specification": spec_copy.relative_to(ROOT).as_posix() if spec_copy.exists() else None,
            "label_status": "PRE_EXECUTION_CONTROLLED_LABEL",
            "live_simulator_confirmation_required": True,
        }
        (case_dir / "mutation.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        manifest_cases.append(metadata)
    manifest = {
        "schema_version": "1.0",
        "purpose": "Extended controlled-violation stress set; the independent primary oracle is experiments/ground_truth/ground_truth_manifest.yaml.",
        "policy": {
            "mutations_modify_active_dut_lines_only": True,
            "provenance_comments_are_never_mutation_targets": True,
            "hash_difference_required": True,
            "labels_are_defined_before_framework_execution": True,
            "live_ngspice_confirmation_required_before_reporting_detection_rates": True,
        },
        "case_count": len(manifest_cases),
        "cases": manifest_cases,
    }
    (OUT_ROOT / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize effective controlled mutations on active ACP-28 DUT lines")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()
    manifest = materialize(clean=not args.no_clean)
    print(json.dumps({"case_count": manifest["case_count"], "manifest": str((OUT_ROOT / 'manifest.yaml').relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
