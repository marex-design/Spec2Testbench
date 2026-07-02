import csv
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmark" / "analogcoder_pro" / "manifest.csv"
SOURCE_SPEC_DIR = ROOT / "examples" / "benchmark_specs"
EXTRACTION_SPEC_DIR = ROOT / "examples" / "benchmark_extraction_specs"
NOMINAL_SPEC_DIR = ROOT / "examples" / "benchmark_nominal_specs"
STRICT_SPEC_DIR = ROOT / "examples" / "benchmark_strict_specs"
ROBUST_SPEC_DIR = ROOT / "examples" / "benchmark_robust_specs"
STEPWISE_CSV = ROOT / "results" / "acp28_stepwise_extraction" / "acp28_stepwise_extraction.csv"


PVT_TARGETS = {
    "operating_point": ("pvt_vout_variation", {"max": 0.5, "unit": "V"}),
    "dc_gain_db": ("pvt_dc_gain_variation", {"max": 20.0, "unit": "dB"}),
    "quiescent_current": ("pvt_power_variation", {"max": 0.05, "unit": "W"}),
    "oscillator_frequency": ("pvt_frequency_variation", {"max": 1.0e9, "unit": "Hz"}),
    "propagation_delay": ("pvt_delay_variation", {"max": 1.0e-3, "unit": "s"}),
    "thd_percent": ("pvt_thd_variation", {"max": 20.0, "unit": "%"}),
}


def load_manifest():
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_stepwise_rows():
    with STEPWISE_CSV.open("r", encoding="utf-8", newline="") as handle:
        return {row["circuit"]: row for row in csv.DictReader(handle)}


def metric_list_from_row(row: dict) -> list[str]:
    raw = row.get("extracted_metrics", "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def ensure_test_categories(spec: dict[str, Any]) -> None:
    categories = spec.get("test_categories", []) or []
    unique = []
    for category in categories:
        if category not in unique:
            unique.append(category)
    spec["test_categories"] = unique


def build_nominal_spec(source_spec: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(source_spec)
    ensure_test_categories(spec)
    return spec


def tighten_target(metric_name: str, target: dict[str, Any]) -> dict[str, Any]:
    tightened = deepcopy(target)
    min_value = tightened.get("min")
    max_value = tightened.get("max")
    typ_value = tightened.get("typ")

    if isinstance(min_value, (int, float)) and isinstance(max_value, (int, float)):
        span = max_value - min_value
        if span > 0:
            tightened["min"] = min_value + 0.1 * span
            tightened["max"] = max_value - 0.1 * span
    elif isinstance(min_value, (int, float)):
        if min_value >= 0:
            tightened["min"] = min_value * 1.25 if min_value != 0 else 0.1
        else:
            tightened["min"] = min_value * 0.75
    elif isinstance(max_value, (int, float)):
        if max_value > 0:
            tightened["max"] = max_value * 0.75
    elif isinstance(typ_value, (int, float)):
        tightened["min"] = typ_value * 0.9
        tightened["max"] = typ_value * 1.1

    tightened["weight"] = max(float(tightened.get("weight", 1.0)), 1.25)
    return tightened


def build_strict_spec(source_spec: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(source_spec)
    strict_targets = {}
    for metric_name, target in (spec.get("performance_targets") or {}).items():
        if isinstance(target, dict):
            strict_targets[metric_name] = tighten_target(metric_name, target)
        else:
            strict_targets[metric_name] = target
    spec["performance_targets"] = strict_targets
    spec["name"] = f"{spec['name']}_strict"
    spec["description"] = f"Strict campaign for {spec.get('description', spec['name'])}"
    ensure_test_categories(spec)
    return spec


def build_robust_spec(source_spec: dict[str, Any], extracted_metrics: list[str]) -> dict[str, Any]:
    spec = deepcopy(source_spec)
    robust_targets = deepcopy(spec.get("performance_targets") or {})

    for metric_name in extracted_metrics:
        mapped = PVT_TARGETS.get(metric_name)
        if not mapped:
            continue
        robust_metric, robust_target = mapped
        robust_targets.setdefault(robust_metric, deepcopy(robust_target))

    spec["performance_targets"] = robust_targets
    spec["name"] = f"{spec['name']}_robust"
    spec["description"] = f"Robust campaign for {spec.get('description', spec['name'])}"

    categories = spec.get("test_categories", []) or []
    if "pvt" not in categories:
        categories.append("pvt")
    spec["test_categories"] = categories
    spec["pvt_config"] = {
        "corners": ["tt", "ff", "ss"],
        "temperature_range": "commercial",
        "supply_variation": 0.1,
    }
    ensure_test_categories(spec)
    return spec


def main():
    manifest_rows = load_manifest()
    stepwise_rows = load_stepwise_rows()

    generated = {
        "extraction": 0,
        "nominal": 0,
        "strict": 0,
        "robust": 0,
    }

    for manifest_row in manifest_rows:
        spec_name = manifest_row["spec"]
        stem = Path(manifest_row["netlist"]).stem
        source_spec = load_yaml(SOURCE_SPEC_DIR / spec_name)
        extraction_spec = load_yaml(EXTRACTION_SPEC_DIR / spec_name)
        extracted_metrics = metric_list_from_row(stepwise_rows[stem])

        dump_yaml(EXTRACTION_SPEC_DIR / spec_name, extraction_spec)
        generated["extraction"] += 1

        nominal_spec = build_nominal_spec(source_spec)
        dump_yaml(NOMINAL_SPEC_DIR / spec_name, nominal_spec)
        generated["nominal"] += 1

        strict_spec = build_strict_spec(source_spec)
        dump_yaml(STRICT_SPEC_DIR / spec_name, strict_spec)
        generated["strict"] += 1

        robust_spec = build_robust_spec(source_spec, extracted_metrics)
        dump_yaml(ROBUST_SPEC_DIR / spec_name, robust_spec)
        generated["robust"] += 1

    for mode, count in generated.items():
        print(f"{mode}: {count}")


if __name__ == "__main__":
    main()
