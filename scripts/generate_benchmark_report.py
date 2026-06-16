from pathlib import Path
import csv
import math


ROOT = Path(__file__).resolve().parents[1]
METRICS_CSV = ROOT / "results" / "metrics.csv"
REPORT_MD = ROOT / "results" / "benchmark_summary.md"


def read_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def safe_float(value):
    try:
        if value in ("", None):
            return math.nan
        return float(value)
    except Exception:
        return math.nan


def count_non_empty(rows, key):
    return sum(row.get(key, "") not in ("", None) for row in rows)


def count_finite_numeric(rows, key):
    count = 0
    for row in rows:
        value = safe_float(row.get(key))
        if not math.isnan(value):
            count += 1
    return count


def main():
    rows = read_rows(METRICS_CSV)
    total = len(rows)
    success = sum(str(row.get("success", "")).lower() == "true" for row in rows)
    raw_exists = sum(str(row.get("raw_exists", "")).lower() == "true" for row in rows)
    parse_ok = sum((row.get("parse_error", "") or "").strip() == "" for row in rows)
    injected = sum(int(row.get("injected_analyses", "0") or 0) > 0 for row in rows)

    plausibility = [safe_float(row.get("plausibility_score")) for row in rows]
    plausibility = [value for value in plausibility if not math.isnan(value)]
    plausibility_mean = sum(plausibility) / len(plausibility) if plausibility else math.nan

    low_plausibility = [
        row["circuit"]
        for row in rows
        if not math.isnan(safe_float(row.get("plausibility_score")))
        and safe_float(row.get("plausibility_score")) < 0.5
    ]

    coverage_keys = [
        "amplitude_pp",
        "frequency_hz",
        "rise_time_s",
        "gain_db_at_dc",
        "cutoff_frequency",
        "mean_current_a",
        "vout_dc",
        "propagation_delay_s",
    ]

    lines = [
        "# Benchmark Campaign Summary",
        "",
        "## Execution",
        "",
        f"- Total benchmark netlists: {total}",
        f"- ngspice batch success: {success}/{total}",
        f"- Raw files generated: {raw_exists}/{total}",
        f"- Parsed without error: {parse_ok}/{total}",
        f"- Netlists auto-prepared before run: {injected}/{total}",
        f"- Mean plausibility score: {plausibility_mean:.3f}" if not math.isnan(plausibility_mean) else "- Mean plausibility score: N/A",
        "",
        "## Metric Coverage",
        "",
    ]

    for key in coverage_keys:
        lines.append(f"- `{key}` finite for {count_finite_numeric(rows, key)}/{total} circuits")

    lines.extend([
        "",
        "## Low-Plausibility Cases",
        "",
    ])

    if low_plausibility:
        for circuit in low_plausibility:
            lines.append(f"- `{circuit}`")
    else:
        lines.append("- None")

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Benchmark summary: {REPORT_MD}")


if __name__ == "__main__":
    main()
