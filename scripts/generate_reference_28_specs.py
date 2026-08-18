import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aggregate_metrics import (
    prepare_netlist_for_campaign,
    run_ngspice_with_raw,
    parse_raw,
    extract_metrics_by_type,
)


BENCH_DIR = Path("benchmark_reference_28")
SPEC_DIR = Path("examples/reference_28_specs")
RAW_DIR = Path("results/reference_28_spec_raw")
LOG_DIR = Path("results/reference_28_spec_logs")
SPEC_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


CASE_CONFIG = {
    "common_source_resistive_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "three_stage_common_source_resistive_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "common_drain_resistive_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "common_gate_resistive_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "cascode_resistive_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "nmos_resistive_load_inverter": {
        "circuit_type": "amplifier",
        "categories": ["transient"],
        "metrics": ["frequency_hz"],
    },
    "cmos_logical_inverter": {
        "circuit_type": "amplifier",
        "categories": ["transient"],
        "metrics": ["frequency_hz"],
    },
    "nmos_constant_current_source_resistive_load": {
        "circuit_type": "current_mirror",
        "categories": ["dc"],
        "metrics": ["vout_dc", "idd"],
    },
    "opamp_comparator": {
        "circuit_type": "comparator",
        "categories": ["transient"],
        "metrics": ["propagation_delay_s"],
    },
    "passive_lowpass_filter": {
        "circuit_type": "low_pass_filter",
        "categories": ["ac", "spectral"],
        "metrics": ["cutoff_frequency_hz", "thd_percent"],
    },
    "passive_highpass_filter": {
        "circuit_type": "high_pass_filter",
        "categories": ["ac", "spectral"],
        "metrics": ["cutoff_frequency_hz", "thd_percent"],
    },
    "passive_bandpass_filter": {
        "circuit_type": "band_pass_filter",
        "categories": ["ac"],
        "metrics": ["bandwidth", "dc_gain"],
    },
    "passive_bandstop_filter": {
        "circuit_type": "notch_filter",
        "categories": ["ac"],
        "metrics": ["cutoff_frequency_hz", "dc_gain"],
    },
    "common_source_diode_connected_load_amplifier": {
        "circuit_type": "amplifier",
        "categories": ["dc", "ac"],
        "metrics": ["vout_dc", "dc_gain"],
    },
    "two_stage_miller_compensated_amplifier": {
        "circuit_type": "opamp",
        "categories": ["ac", "transient"],
        "metrics": ["dc_gain", "cutoff_frequency_hz"],
    },
    "cascode_current_mirror": {
        "circuit_type": "current_mirror",
        "categories": ["dc"],
        "metrics": ["vout_dc", "idd"],
    },
    "opamp_active_current_mirror_loads": {
        "circuit_type": "opamp",
        "categories": ["ac"],
        "metrics": ["dc_gain", "cutoff_frequency_hz"],
    },
    "common_source_resistive_load_opamp": {
        "circuit_type": "opamp",
        "categories": ["ac"],
        "metrics": ["dc_gain", "cutoff_frequency_hz"],
    },
    "gilbert_cell_mixer": {
        "circuit_type": "mixer",
        "categories": ["transient", "spectral"],
        "metrics": ["frequency_hz", "thd_percent"],
    },
    "cascode_opamp_cascode_loads": {
        "circuit_type": "opamp",
        "categories": ["ac"],
        "metrics": ["dc_gain", "cutoff_frequency_hz"],
    },
    "two_stage_opamp_active_loads": {
        "circuit_type": "opamp",
        "categories": ["ac", "transient"],
        "metrics": ["dc_gain", "cutoff_frequency_hz"],
    },
    "wien_bridge_oscillator": {
        "circuit_type": "oscillator",
        "categories": ["transient", "spectral"],
        "metrics": ["frequency_hz", "thd_percent"],
    },
    "rc_shift_oscillator": {
        "circuit_type": "rc_phase_shift_oscillator",
        "categories": ["transient", "spectral"],
        "metrics": ["frequency_hz", "thd_percent"],
    },
    "opamp_integrator": {
        "circuit_type": "integrator",
        "categories": ["transient", "ac"],
        "metrics": ["frequency_hz"],
    },
    "opamp_differentiator": {
        "circuit_type": "differentiator",
        "categories": ["transient", "ac"],
        "metrics": ["frequency_hz"],
    },
    "opamp_adder": {
        "circuit_type": "composite",
        "categories": ["ac", "transient"],
        "metrics": ["frequency_hz"],
    },
    "opamp_subtractor": {
        "circuit_type": "composite",
        "categories": ["ac", "transient"],
        "metrics": ["frequency_hz"],
    },
    "non_inverting_schmitt_trigger": {
        "circuit_type": "schmitt_trigger",
        "categories": ["transient"],
        "metrics": ["frequency_hz"],
    },
}


SOURCE_KEYS = {
    "vout_dc": ("vout_dc", "V", "range"),
    "idd": ("mean_current_a", "A", "max_only"),
    "power": ("quiescent_power_w", "W", "max_only"),
    "dc_gain": ("gain_db_at_dc", "dB", "range_db"),
    "bandwidth": ("bandwidth", "Hz", "range_freq"),
    "cutoff_frequency_hz": ("cutoff_frequency", "Hz", "range_freq"),
    "unity_gain_frequency": ("ugbw_hz", "Hz", "range_freq"),
    "phase_margin": ("phase_margin_deg", "deg", "range_deg"),
    "propagation_delay_s": ("propagation_delay_s", "s", "max_only"),
    "frequency_hz": ("frequency_hz", "Hz", "range_freq"),
    "thd_percent": ("thd_percent", "%", "max_only_relaxed"),
}


def finite_number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def build_target(spec_metric: str, observed_value):
    if spec_metric not in SOURCE_KEYS or not finite_number(observed_value):
        return None

    _, unit, mode = SOURCE_KEYS[spec_metric]
    magnitude = abs(float(observed_value))

    if mode == "range":
        delta = max(0.1, 0.25 * max(magnitude, 1e-3))
        return {"min": observed_value - delta, "max": observed_value + delta, "unit": unit}
    if mode == "range_db":
        return {"min": observed_value - 12.0, "max": observed_value + 12.0, "unit": unit}
    if mode == "range_freq":
        return {"min": max(1e-3, observed_value * 0.25), "max": observed_value * 2.0, "unit": unit}
    if mode == "range_deg":
        return {"min": max(0.0, observed_value - 20.0), "max": min(180.0, observed_value + 20.0), "unit": unit}
    if mode == "max_only":
        return {"max": max(magnitude * 1.5, 1e-12), "unit": unit}
    if mode == "max_only_relaxed":
        return {"max": max(magnitude * 2.0, 5.0), "unit": unit}

    return None


def extract_nominal_metrics(netlist: Path):
    prepared_netlist, _ = prepare_netlist_for_campaign(netlist)
    raw_path = RAW_DIR / f"{netlist.stem}.raw"
    log_path = LOG_DIR / f"{netlist.stem}.log"
    result = run_ngspice_with_raw(prepared_netlist, raw_path, log_path)
    if result.returncode != 0:
        return {}
    data, parse_error = parse_raw(raw_path)
    if data is None or parse_error:
        return {}
    metrics, _, _ = extract_metrics_by_type(data, netlist.stem, netlist.read_text(encoding="utf-8", errors="ignore"))
    return metrics


def main():
    generated = 0
    for netlist in sorted(BENCH_DIR.glob("*.cir")):
        config = CASE_CONFIG.get(netlist.stem)
        if not config:
            continue

        metrics = extract_nominal_metrics(netlist)
        performance_targets = {}

        for spec_metric in config["metrics"]:
            source_key = SOURCE_KEYS[spec_metric][0]
            observed_value = metrics.get(source_key)
            target = build_target(spec_metric, observed_value)
            if target is not None:
                performance_targets[spec_metric] = target

        if not performance_targets:
            # Keep the spec valid even if extraction was sparse.
            performance_targets["vout_dc"] = {"min": 0.0, "max": 10.0, "unit": "V"}

        spec = {
            "name": netlist.stem,
            "circuit_type": config["circuit_type"],
            "technology": "reference_28_behavioral",
            "description": netlist.stem.replace("_", " "),
            "performance_targets": performance_targets,
            "test_categories": config["categories"],
        }

        spec_path = SPEC_DIR / f"{netlist.stem}.yaml"
        spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        generated += 1

    print(f"Generated {generated} YAML specs in {SPEC_DIR}")


if __name__ == "__main__":
    main()
