import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"


SUPPORTED_MEASURE = [
    "operating_point",
    "vout_dc",
    "quiescent_current",
    "idd",
    "power",
    "dc_gain_db",
    "cutoff_frequency_hz",
    "bandwidth",
    "startup_amplitude",
    "propagation_delay",
    "propagation_delay_s",
]

SUPPORTED_WRDATA = [
    "dc_gain_db",
    "cutoff_frequency_hz",
    "bandwidth",
    "amplitude_pp",
    "frequency_hz",
    "oscillator_frequency",
    "switching_threshold_rising_v",
    "switching_threshold_falling_v",
    "hysteresis_width_v",
]


def main() -> None:
    validation_rows = read_csv(RESULTS / "ngspice_native_extraction_validation.csv")
    campaign_rows = read_csv(RESULTS / "controlled_violation_results_v2.csv") if (RESULTS / "controlled_violation_results_v2.csv").exists() else []
    coverage = Counter(row.get("measurement_backend", "UNRECORDED") for row in campaign_rows)
    coverage_rows = [{"backend": key, "case_count": value} for key, value in sorted(coverage.items())]
    write_csv(RESULTS / "measurement_backend_coverage.csv", coverage_rows)

    agreements = sum(1 for row in validation_rows if str(row.get("agreement", "")).lower() == "true")
    lines = [
        "# Ngspice Native Extraction Validation",
        "",
        f"- Supported via `.measure`: {', '.join(SUPPORTED_MEASURE)}",
        f"- Supported via `wrdata`: {', '.join(SUPPORTED_WRDATA)}",
        f"- Validation rows: {len(validation_rows)}",
        f"- Comparisons within tolerance: {agreements}",
        f"- Remaining explicit PySpice dependency: optional raw parsing fallback only",
        "",
        "## Backend Coverage",
        "",
    ]
    for row in coverage_rows:
        lines.append(f"- {row['backend']}: {row['case_count']}")
    (REPORTS / "ngspice_native_extraction_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
