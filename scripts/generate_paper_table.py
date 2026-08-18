import csv
from pathlib import Path


METRICS_CSV = Path("results/benchmark_campaign_metrics.csv")
OUT_TABLE_CSV = Path("results/paper_topology_table.csv")
OUT_TABLE_MD = Path("results/paper_topology_table.md")

DISPLAY_METRICS = [
    "vout_dc",
    "mean_current_a",
    "quiescent_power_w",
    "dc_gain_db",
    "cutoff_frequency_hz",
    "ugbw_hz",
    "phase_margin_deg",
    "propagation_delay_s",
    "frequency_hz",
    "thd_percent",
    "pvt_vout_variation",
    "pvt_dc_gain_variation",
    "pvt_power_variation",
]


def nonempty(value):
    return value not in ("", None)


def main():
    rows = list(csv.DictReader(METRICS_CSV.open(encoding="utf-8")))
    table_rows = []
    markdown_lines = [
        "# Paper-Ready Benchmark Table",
        "",
        "| Topology | Type | Extracted Metrics | Success | Plausibility |",
        "|---|---|---|---|---|",
    ]

    for row in rows:
        extracted = [metric for metric in DISPLAY_METRICS if nonempty(row.get(metric))]
        extracted_text = ", ".join(extracted)
        success_text = "PASS" if row.get("success") == "True" else "FAIL"
        plausibility = row.get("plausibility_score", "")
        warnings = row.get("plausibility_warnings", "")
        if warnings:
            plausibility_text = f"{plausibility} ({warnings})"
        else:
            plausibility_text = plausibility

        table_rows.append({
            "topology": row["circuit"],
            "type": row["circuit_type"],
            "extracted_metrics": extracted_text,
            "success": success_text,
            "plausibility": plausibility_text,
        })
        markdown_lines.append(
            f"| {row['circuit']} | {row['circuit_type']} | {extracted_text} | {success_text} | {plausibility_text} |"
        )

    with OUT_TABLE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(table_rows)

    OUT_TABLE_MD.write_text("\n".join(markdown_lines), encoding="utf-8")
    print(f"Paper table CSV: {OUT_TABLE_CSV}")
    print(f"Paper table Markdown: {OUT_TABLE_MD}")


if __name__ == "__main__":
    main()
