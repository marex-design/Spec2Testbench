import csv
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmark" / "analogcoder_pro" / "manifest.csv"
SOURCE_SPEC_DIR = ROOT / "examples" / "benchmark_specs"
OUT_SPEC_DIR = ROOT / "examples" / "benchmark_extraction_specs"
STEPWISE_CSV = ROOT / "results" / "acp28_stepwise_extraction" / "acp28_stepwise_extraction.csv"


METRIC_TARGETS = {
    "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
    "dc_gain_db": {"min": -1000.0, "max": 1000.0, "unit": "dB"},
    "quiescent_current": {"min": 0.0, "max": 1.0, "unit": "A"},
    "propagation_delay": {"min": 0.0, "max": 1.0, "unit": "s"},
    "cutoff_frequency_hz": {"min": 1.0, "max": 1.0e12, "unit": "Hz"},
    "phase_margin": {"min": 0.0, "max": 180.0, "unit": "deg"},
    "fundamental_frequency": {"min": 1.0, "max": 1.0e12, "unit": "Hz"},
    "oscillator_frequency": {"min": 1.0, "max": 1.0e12, "unit": "Hz"},
    "startup_amplitude": {"min": 0.0, "max": 1.0e3, "unit": "V"},
    "slew_rate": {"min": 1.0e-12, "max": 1.0e12, "unit": "V/s"},
    "settling_time": {"min": 0.0, "max": 1.0, "unit": "s"},
    "thd_percent": {"min": 0.0, "max": 100.0, "unit": "%"},
}


METRIC_CATEGORIES = {
    "operating_point": "dc",
    "quiescent_current": "dc",
    "dc_gain_db": "ac",
    "phase_margin": "ac",
    "cutoff_frequency_hz": "ac",
    "propagation_delay": "transient",
    "fundamental_frequency": "spectral",
    "thd_percent": "spectral",
    "oscillator_frequency": "transient",
    "startup_amplitude": "transient",
    "slew_rate": "transient",
    "settling_time": "transient",
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


def build_spec(source_data: dict, manifest_row: dict, metrics: list[str]) -> dict:
    performance_targets = {metric: dict(METRIC_TARGETS[metric]) for metric in metrics}
    categories = []
    for metric in metrics:
        category = METRIC_CATEGORIES.get(metric)
        if category and category not in categories:
            categories.append(category)

    spec = {
        "name": source_data.get("name", f"analogcoder_pro_{Path(manifest_row['netlist']).stem}"),
        "circuit_type": source_data["circuit_type"],
        "technology": source_data.get("technology", "AnalogCoder-Pro/PySpice generic Level-1 models"),
        "description": source_data.get("description", manifest_row.get("description", "")),
        "source": source_data.get("source", {}),
        "performance_targets": performance_targets,
        "input_conditions": source_data.get("input_conditions", {}),
        "test_categories": categories,
    }
    return spec


def main():
    OUT_SPEC_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_manifest()
    stepwise_rows = load_stepwise_rows()

    generated = 0
    for manifest_row in manifest_rows:
        spec_name = manifest_row["spec"]
        stem = Path(manifest_row["netlist"]).stem
        source_spec_path = SOURCE_SPEC_DIR / spec_name
        source_data = yaml.safe_load(source_spec_path.read_text(encoding="utf-8"))
        metrics = metric_list_from_row(stepwise_rows[stem])
        new_spec = build_spec(source_data, manifest_row, metrics)
        out_path = OUT_SPEC_DIR / spec_name
        out_path.write_text(yaml.dump(new_spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
        generated += 1

    print(f"Generated {generated} extraction specs in {OUT_SPEC_DIR}")


if __name__ == "__main__":
    main()
