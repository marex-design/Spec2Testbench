import csv
from pathlib import Path


MANIFEST = Path("benchmark_reference_28/manifest.csv")
CAMPAIGN = Path("results/reference_28_framework_campaign.csv")
OUT_CSV = Path("results/reference_28_paper_table.csv")
OUT_MD = Path("results/reference_28_paper_table.md")


def main():
    manifest_rows = {Path(row["filename"]).stem: row for row in csv.DictReader(MANIFEST.open(encoding="utf-8"))}
    campaign_rows = {row["topology"]: row for row in csv.DictReader(CAMPAIGN.open(encoding="utf-8"))}

    rows = []
    for topology, meta in sorted(manifest_rows.items(), key=lambda item: int(item[1]["id"])):
        result = campaign_rows.get(topology, {})
        rows.append({
            "id": meta["id"],
            "topology": topology,
            "family": meta["family"],
            "description": meta["description"],
            "analyses": result.get("analyses", ""),
            "metrics": result.get("metrics", ""),
            "verdict": result.get("overall_verdict", ""),
            "compliance": result.get("compliance_score", ""),
            "success_rate": result.get("success_rate", ""),
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Reference-28 Paper-Ready Table",
        "",
        "| ID | Topology | Family | Description | Analyses | Metrics | Verdict | Compliance |",
        "|---:|---|---|---|---|---|---|---:|",
    ]
    for row in rows:
        compliance = row["compliance"]
        if compliance not in ("", None):
            try:
                compliance = f"{float(compliance):.2f}"
            except Exception:
                pass
        lines.append(
            f"| {row['id']} | {row['topology']} | {row['family']} | {row['description']} | "
            f"{row['analyses']} | {row['metrics']} | {row['verdict']} | {compliance} |"
        )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {OUT_CSV}")
    print(f"Markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
