import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


NETLIST_DIR = Path("benchmark_netlists")
METRICS_CSV = Path("results/benchmark_campaign_metrics.csv")
TOPOLOGY_CSV = Path("results/paper_topology_table.csv")
OUT_CSV = Path("results/benchmark_detailed_table.csv")
OUT_MD = Path("results/benchmark_detailed_table.md")


COMPONENT_PREFIXES = {
    "R", "C", "L", "V", "I", "D", "M", "Q", "J", "X",
    "E", "F", "G", "H", "B", "S", "T", "U", "W",
}


def parse_netlist(path: Path):
    counts: dict[str, int] = {}
    analyses: list[str] = []
    in_control_block = False

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("+"):
            continue

        lowered = stripped.lower()
        if lowered.startswith(".control"):
            in_control_block = True
            continue
        if lowered.startswith(".endc"):
            in_control_block = False
            continue
        if in_control_block:
            continue

        if lowered.startswith("."):
            if lowered.startswith(".op"):
                analyses.append("op")
            elif lowered.startswith(".dc"):
                analyses.append("dc")
            elif lowered.startswith(".ac"):
                analyses.append("ac")
            elif lowered.startswith(".tran"):
                analyses.append("tran")
            elif lowered.startswith(".four"):
                analyses.append("fourier")
            elif lowered.startswith(".fft"):
                analyses.append("fft")
            continue

        token = stripped.split()[0]
        prefix = token[0].upper()
        if prefix in COMPONENT_PREFIXES:
            counts[prefix] = counts.get(prefix, 0) + 1

    total_components = sum(counts.values())
    if total_components <= 4:
        complexity = "small"
    elif total_components <= 6:
        complexity = "medium"
    else:
        complexity = "large"

    return total_components, complexity, counts, analyses


def compact_breakdown(counts: dict[str, int]) -> str:
    ordered = []
    for key in ("M", "Q", "D", "R", "C", "L", "V", "I", "E", "G", "B", "S"):
        if counts.get(key):
            ordered.append(f"{counts[key]}{key}")
    for key in sorted(counts):
        if key not in {"M", "Q", "D", "R", "C", "L", "V", "I", "E", "G", "B", "S"}:
            ordered.append(f"{counts[key]}{key}")
    return ", ".join(ordered)


def infer_analyses(metric_row: dict[str, str], extracted_metrics: str) -> str:
    analyses = set()
    metrics_lower = extracted_metrics.lower()
    prep_notes = (metric_row.get("preparation_notes") or "").lower()

    if "vout_dc" in metrics_lower or "mean_current_a" in metrics_lower or "quiescent_power_w" in metrics_lower or "injected_op" in prep_notes:
        analyses.add("op")
    if any(token in metrics_lower for token in ("dc_gain", "cutoff_frequency", "ugbw", "phase_margin", "bandwidth")):
        analyses.add("ac")
    if any(token in metrics_lower for token in ("rise_time", "propagation_delay", "frequency_hz", "startup_amplitude")):
        analyses.add("tran")
    if "thd_percent" in metrics_lower:
        analyses.add("fourier")
    if "pvt_" in metrics_lower:
        analyses.add("pvt")

    order = ["op", "dc", "ac", "tran", "fourier", "fft", "pvt"]
    return ",".join(item for item in order if item in analyses)


def main():
    metrics_rows = {row["circuit"]: row for row in csv.DictReader(METRICS_CSV.open(encoding="utf-8"))}
    topology_rows = {row["topology"]: row for row in csv.DictReader(TOPOLOGY_CSV.open(encoding="utf-8"))}

    rows = []
    for netlist_path in sorted(NETLIST_DIR.glob("*.cir")):
        name = netlist_path.stem
        total_components, complexity, counts, analyses = parse_netlist(netlist_path)
        metric_row = metrics_rows.get(name, {})
        topo_row = topology_rows.get(name, {})

        extracted_metrics = topo_row.get("extracted_metrics", "")
        analyses_text = ",".join(analyses) if analyses else infer_analyses(metric_row, extracted_metrics)

        rows.append({
            "topology": name,
            "family": topo_row.get("type", metric_row.get("circuit_type", "")),
            "complexity_class": complexity,
            "component_count": total_components,
            "component_breakdown": compact_breakdown(counts),
            "analyses": analyses_text,
            "metrics": extracted_metrics,
            "success": topo_row.get("success", "PASS" if metric_row.get("success") == "True" else "FAIL"),
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Detailed Benchmark Table",
        "",
        "| Topology | Family | Complexity | Components | Analyses | Metrics | Success |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['topology']} | {row['family']} | {row['complexity_class']} ({row['component_breakdown']}) | "
            f"{row['component_count']} | {row['analyses']} | {row['metrics']} | {row['success']} |"
        )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Detailed benchmark CSV: {OUT_CSV}")
    print(f"Detailed benchmark Markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
