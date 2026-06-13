import csv
import subprocess
from pathlib import Path
from statistics import mean


BENCH_DIR = Path("benchmark_reference_28")
RESULTS_DIR = Path("results")
LOG_DIR = RESULTS_DIR / "reference_28_logs"
RAW_DIR = RESULTS_DIR / "reference_28_raw"
OUT_CSV = RESULTS_DIR / "reference_28_campaign.csv"
OUT_MD = RESULTS_DIR / "reference_28_campaign.md"

LOG_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


def component_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith(".") or stripped.startswith("+"):
            continue
        if stripped.split()[0][0].isalpha():
            count += 1
    return count


def analyses_present(text: str) -> str:
    lowered = text.lower()
    analyses = []
    for key in ("op", "dc", "ac", "tran", "four", "fft"):
        if f".{key}" in lowered:
            analyses.append("fourier" if key == "four" else key)
    return ",".join(analyses)


def run_case(netlist: Path) -> dict:
    text = netlist.read_text(encoding="utf-8", errors="ignore")
    raw_path = RAW_DIR / f"{netlist.stem}.raw"
    log_path = LOG_DIR / f"{netlist.stem}.log"
    result = subprocess.run(
        ["ngspice", "-b", "-r", str(raw_path), str(netlist)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    success = result.returncode == 0
    return {
        "circuit": netlist.stem,
        "component_count": component_count(text),
        "analyses": analyses_present(text),
        "success": success,
        "returncode": result.returncode,
        "raw_exists": raw_path.exists(),
        "log_path": str(log_path),
    }


def main():
    netlists = sorted(BENCH_DIR.glob("*.cir"))
    if not netlists:
        raise SystemExit("No .cir files found in benchmark_reference_28. Run create_reference_28_netlists.py first.")

    rows = []
    for netlist in netlists:
        print(f"Running {netlist.name}")
        rows.append(run_case(netlist))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    successes = sum(1 for row in rows if row["success"])
    mean_components = mean(row["component_count"] for row in rows)

    lines = [
        "# Reference-28 Campaign Summary",
        "",
        f"- Total circuits: {len(rows)}",
        f"- ngspice successes: {successes}/{len(rows)}",
        f"- Mean component count: {mean_components:.2f}",
        "",
        "| Circuit | Components | Analyses | Success | Return Code |",
        "|---|---:|---|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['circuit']} | {row['component_count']} | {row['analyses']} | {row['success']} | {row['returncode']} |"
        )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {OUT_CSV}")
    print(f"Markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
