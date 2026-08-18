import csv
import json
import math
import re
from pathlib import Path
from statistics import mean, median

from aggregate_metrics import (
    NETLIST_DIR,
    OUT_RAW_DIR,
    PREPARED_NETLIST_DIR,
    NGSPICE_LOG_DIR,
    extract_metrics_by_type,
    parse_raw,
    prepare_netlist_for_campaign,
    run_ngspice_with_raw,
)


RESULTS_DIR = Path("results")
OUT_CSV = RESULTS_DIR / "benchmark_campaign_metrics.csv"
OUT_PVT_CSV = RESULTS_DIR / "benchmark_campaign_pvt.csv"
OUT_SUMMARY_JSON = RESULTS_DIR / "benchmark_campaign_summary.json"
OUT_SUMMARY_MD = RESULTS_DIR / "benchmark_campaign_summary.md"
PVT_RAW_DIR = RESULTS_DIR / "pvt_raw"
PVT_NETLIST_DIR = RESULTS_DIR / "pvt_prepared_netlists"
PVT_LOG_DIR = RESULTS_DIR / "pvt_logs"

for directory in (PVT_RAW_DIR, PVT_NETLIST_DIR, PVT_LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def safe_float(value):
    try:
        if value in ("", None):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def supply_sources_from_netlist(netlist_text: str):
    pattern = re.compile(
        r"^(V[\w$]+)\s+(\S+)\s+(\S+)\s+DC\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
        re.IGNORECASE | re.MULTILINE,
    )
    sources = []
    for match in pattern.finditer(netlist_text):
        source_name, positive_node, negative_node, value = match.groups()
        lowered = f"{source_name} {positive_node}".lower()
        if any(token in lowered for token in ("vdd", "vcc", "supply")) and negative_node == "0":
            sources.append((source_name, positive_node, negative_node, float(value)))
    return sources


def apply_pvt_variant(netlist_text: str, temperature: int | None, supply_scale: float):
    updated = re.sub(r"^\s*\.temp\b.*$", "", netlist_text, flags=re.IGNORECASE | re.MULTILINE)
    sources = supply_sources_from_netlist(updated)

    for source_name, positive_node, negative_node, nominal in sources:
        scaled = nominal * supply_scale
        source_pattern = re.compile(
            rf"^({re.escape(source_name)}\s+{re.escape(positive_node)}\s+{re.escape(negative_node)}\s+DC\s+)([^\s]+)",
            re.IGNORECASE | re.MULTILINE,
        )
        updated = source_pattern.sub(rf"\g<1>{scaled}", updated, count=1)

    if temperature is not None:
        updated = updated.rstrip() + f"\n.temp {temperature}\n"

    return updated, len(sources)


def run_pvt_variants(netlist: Path, stem: str, netlist_text: str):
    variant_rows = []
    base_variants = [("temp_0c", 0, 1.0), ("temp_70c", 70, 1.0)]
    has_supply = bool(supply_sources_from_netlist(netlist_text))
    if has_supply:
        base_variants.extend([("vdd_minus_5pct", None, 0.95), ("vdd_plus_5pct", None, 1.05)])

    for label, temperature, supply_scale in base_variants:
        variant_text, modified_supplies = apply_pvt_variant(netlist_text, temperature, supply_scale)
        variant_path = PVT_NETLIST_DIR / f"{stem}_{label}.cir"
        raw_path = PVT_RAW_DIR / f"{stem}_{label}.raw"
        log_path = PVT_LOG_DIR / f"{stem}_{label}.log"
        variant_path.write_text(variant_text, encoding="utf-8")

        result = run_ngspice_with_raw(variant_path, raw_path, log_path)
        data, parse_error = parse_raw(raw_path)
        metrics = {}
        circuit_type = ""
        if data is not None:
            metrics, metric_error, circuit_type = extract_metrics_by_type(data, stem, netlist_text)
            parse_error = metric_error or parse_error

        variant_rows.append({
            "circuit": stem,
            "variant": label,
            "temperature_c": "" if temperature is None else temperature,
            "supply_scale": supply_scale,
            "modified_supplies": modified_supplies,
            "success": result.returncode == 0,
            "parse_error": parse_error or "",
            "circuit_type": circuit_type,
            "vout_dc": metrics.get("vout_dc", ""),
            "mean_current_a": metrics.get("mean_current_a", ""),
            "quiescent_power_w": metrics.get("quiescent_power_w", ""),
            "dc_gain_db": metrics.get("gain_db_at_dc", metrics.get("dc_gain_db", "")),
            "cutoff_frequency_hz": metrics.get("cutoff_frequency", ""),
            "ugbw_hz": metrics.get("ugbw_hz", ""),
            "frequency_hz": metrics.get("frequency_hz", ""),
            "propagation_delay_s": metrics.get("propagation_delay_s", ""),
            "thd_percent": metrics.get("thd_percent", ""),
        })

    return variant_rows


def summarize_pvt(nominal_metrics: dict, variant_rows: list[dict]):
    summary = {"pvt_variants_run": len(variant_rows)}
    tracked = {
        "pvt_vout_variation": [safe_float(nominal_metrics.get("vout_dc"))],
        "pvt_current_variation": [safe_float(nominal_metrics.get("mean_current_a"))],
        "pvt_power_variation": [safe_float(nominal_metrics.get("quiescent_power_w"))],
        "pvt_dc_gain_variation": [safe_float(nominal_metrics.get("dc_gain_db"))],
        "pvt_frequency_variation": [safe_float(nominal_metrics.get("frequency_hz"))],
        "pvt_delay_variation": [safe_float(nominal_metrics.get("propagation_delay_s"))],
        "pvt_thd_variation": [safe_float(nominal_metrics.get("thd_percent"))],
    }

    column_map = {
        "pvt_vout_variation": "vout_dc",
        "pvt_current_variation": "mean_current_a",
        "pvt_power_variation": "quiescent_power_w",
        "pvt_dc_gain_variation": "dc_gain_db",
        "pvt_frequency_variation": "frequency_hz",
        "pvt_delay_variation": "propagation_delay_s",
        "pvt_thd_variation": "thd_percent",
    }

    for row in variant_rows:
        for summary_key, column_name in column_map.items():
            value = safe_float(row.get(column_name))
            if value is not None:
                tracked[summary_key].append(value)

    for summary_key, values in tracked.items():
        numeric_values = [value for value in values if value is not None]
        if len(numeric_values) >= 2:
            summary[summary_key] = max(numeric_values) - min(numeric_values)
        else:
            summary[summary_key] = ""

    return summary


def aggregate_summary(rows: list[dict], pvt_rows: list[dict]):
    def count_nonempty(column_name):
        return sum(safe_float(row.get(column_name)) is not None for row in rows)

    def count_family(columns):
        return sum(
            any(safe_float(row.get(column_name)) is not None for column_name in columns)
            for row in rows
        )

    plausibility_values = [safe_float(row.get("plausibility_score")) for row in rows]
    plausibility_values = [value for value in plausibility_values if value is not None]
    low_plausibility = [row["circuit"] for row in rows if (safe_float(row.get("plausibility_score")) or 0.0) < 0.7]

    summary = {
        "total_circuits": len(rows),
        "ngspice_success_count": sum(row["success"] is True for row in rows),
        "family_coverage": {
            "dc": count_family(("vout_dc", "mean_current_a", "quiescent_power_w")),
            "ac": count_family(("dc_gain_db", "cutoff_frequency_hz", "ugbw_hz", "phase_margin_deg")),
            "transient": count_family(("rise_time_s", "propagation_delay_s", "frequency_hz")),
            "spectral": count_nonempty("thd_percent"),
            "pvt": count_family(("pvt_vout_variation", "pvt_dc_gain_variation", "pvt_power_variation")),
        },
        "metric_availability": {
            "vout_dc": count_nonempty("vout_dc"),
            "mean_current_a": count_nonempty("mean_current_a"),
            "quiescent_power_w": count_nonempty("quiescent_power_w"),
            "dc_gain_db": count_nonempty("dc_gain_db"),
            "cutoff_frequency_hz": count_nonempty("cutoff_frequency_hz"),
            "ugbw_hz": count_nonempty("ugbw_hz"),
            "phase_margin_deg": count_nonempty("phase_margin_deg"),
            "rise_time_s": count_nonempty("rise_time_s"),
            "propagation_delay_s": count_nonempty("propagation_delay_s"),
            "frequency_hz": count_nonempty("frequency_hz"),
            "thd_percent": count_nonempty("thd_percent"),
            "pvt_vout_variation": count_nonempty("pvt_vout_variation"),
            "pvt_dc_gain_variation": count_nonempty("pvt_dc_gain_variation"),
            "pvt_power_variation": count_nonempty("pvt_power_variation"),
        },
        "plausibility": {
            "mean_score": mean(plausibility_values) if plausibility_values else None,
            "median_score": median(plausibility_values) if plausibility_values else None,
            "low_plausibility_circuits": low_plausibility,
        },
        "pvt_variant_rows": len(pvt_rows),
    }
    return summary


def summary_markdown(summary: dict):
    family = summary["family_coverage"]
    availability = summary["metric_availability"]
    plausibility = summary["plausibility"]
    low_list = ", ".join(plausibility["low_plausibility_circuits"]) or "none"

    return "\n".join([
        "# Benchmark Campaign Summary",
        "",
        f"- Total circuits: {summary['total_circuits']}",
        f"- ngspice successes: {summary['ngspice_success_count']}/{summary['total_circuits']}",
        f"- PVT variant rows: {summary['pvt_variant_rows']}",
        f"- Mean plausibility score: {plausibility['mean_score']:.3f}" if plausibility["mean_score"] is not None else "- Mean plausibility score: n/a",
        f"- Median plausibility score: {plausibility['median_score']:.3f}" if plausibility["median_score"] is not None else "- Median plausibility score: n/a",
        f"- Low-plausibility circuits: {low_list}",
        "",
        "## Family Coverage",
        "",
        f"- DC evidence count: {family['dc']}",
        f"- AC evidence count: {family['ac']}",
        f"- Transient evidence count: {family['transient']}",
        f"- Spectral evidence count: {family['spectral']}",
        f"- PVT evidence count: {family['pvt']}",
        "",
        "## Metric Availability",
        "",
        *(f"- {name}: {count}" for name, count in availability.items()),
    ])


def main():
    rows = []
    pvt_rows = []

    for netlist in sorted(NETLIST_DIR.glob("*.cir")):
        stem = netlist.stem
        netlist_text = netlist.read_text(errors="ignore")
        prepared_netlist, prep_meta = prepare_netlist_for_campaign(netlist)
        raw_file = OUT_RAW_DIR / f"{stem}.raw"
        log_file = NGSPICE_LOG_DIR / f"{stem}.log"

        print(f"Running nominal campaign: {netlist.name}")
        result = run_ngspice_with_raw(prepared_netlist, raw_file, log_file)
        logs = (result.stdout or "") + "\n" + (result.stderr or "")
        success = result.returncode == 0 and "error" not in logs.lower()
        data, parse_error = parse_raw(raw_file)
        metrics = {}
        circuit_type = ""
        if data is not None:
            metrics, metric_error, circuit_type = extract_metrics_by_type(data, stem, netlist_text)
            parse_error = metric_error or parse_error

        pvt_variant_rows = run_pvt_variants(netlist, stem, netlist_text)
        pvt_rows.extend(pvt_variant_rows)
        pvt_summary = summarize_pvt(metrics, pvt_variant_rows)

        rows.append({
            "circuit": stem,
            "circuit_type": circuit_type,
            "success": success,
            "ngspice_returncode": result.returncode,
            "raw_exists": raw_file.exists(),
            "log_path": str(log_file),
            "prepared_netlist": prep_meta["prepared_netlist"],
            "preparation_notes": prep_meta["preparation_notes"],
            "injected_analyses": prep_meta["injected_analyses"],
            "parse_error": parse_error or "",
            "dc_gain_db": metrics.get("gain_db_at_dc", metrics.get("dc_gain_db", "")),
            "gain_db_peak": metrics.get("gain_db_peak", ""),
            "cutoff_frequency_hz": metrics.get("cutoff_frequency", ""),
            "bandwidth_hz": metrics.get("bandwidth", ""),
            "ugbw_hz": metrics.get("ugbw_hz", ""),
            "phase_margin_deg": metrics.get("phase_margin_deg", ""),
            "vout_dc": metrics.get("vout_dc", ""),
            "mean_current_a": metrics.get("mean_current_a", ""),
            "quiescent_power_w": metrics.get("quiescent_power_w", ""),
            "rise_time_s": metrics.get("rise_time_s", ""),
            "propagation_delay_s": metrics.get("propagation_delay_s", ""),
            "frequency_hz": metrics.get("frequency_hz", ""),
            "amplitude_pp": metrics.get("amplitude_pp", ""),
            "thd_percent": metrics.get("thd_percent", ""),
            "preferred_out_node": metrics.get("preferred_out_node", ""),
            "preferred_in_node": metrics.get("preferred_in_node", ""),
            "node_selection_reason_out": metrics.get("node_selection_reason_out", ""),
            "node_selection_reason_in": metrics.get("node_selection_reason_in", ""),
            "plausibility_score": metrics.get("plausibility_score", ""),
            "plausibility_warnings": metrics.get("plausibility_warnings", ""),
            **pvt_summary,
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    if pvt_rows:
        with OUT_PVT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(pvt_rows[0].keys()))
            writer.writeheader()
            writer.writerows(pvt_rows)

    summary = aggregate_summary(rows, pvt_rows)
    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    OUT_SUMMARY_MD.write_text(summary_markdown(summary), encoding="utf-8")

    print(f"Detailed metrics: {OUT_CSV}")
    print(f"PVT metrics: {OUT_PVT_CSV}")
    print(f"Summary JSON: {OUT_SUMMARY_JSON}")
    print(f"Summary Markdown: {OUT_SUMMARY_MD}")


if __name__ == "__main__":
    main()
