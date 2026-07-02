import csv
import json
import subprocess
import sys
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_acp28_stepwise_extraction.py"
RESULTS_DIR = ROOT / "results" / "acp28_campaign_matrix"
SUMMARY_CSV = RESULTS_DIR / "campaign_summary.csv"
SUMMARY_JSON = RESULTS_DIR / "campaign_summary.json"
SUMMARY_MD = RESULTS_DIR / "campaign_summary.md"
PER_CIRCUIT_CSV = RESULTS_DIR / "campaign_per_circuit.csv"

CAMPAIGNS = [
    ("extraction", ROOT / "examples" / "benchmark_extraction_specs"),
    ("nominal", ROOT / "examples" / "benchmark_nominal_specs"),
    ("strict", ROOT / "examples" / "benchmark_strict_specs"),
    ("robust", ROOT / "examples" / "benchmark_robust_specs"),
]


def parse_args():
    parser = argparse.ArgumentParser(description="Run the ACP28 verification matrix across spec campaigns.")
    parser.add_argument(
        "--campaigns",
        nargs="+",
        choices=[name for name, _ in CAMPAIGNS],
        help="Subset of campaigns to execute.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip campaigns whose per-campaign CSV already exists.",
    )
    return parser.parse_args()


def run_campaign(name: str, spec_dir: Path) -> tuple[dict, list[dict]]:
    out_dir = RESULTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(RUNNER),
        "--spec-dir", str(spec_dir),
        "--results-dir", str(out_dir),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)

    csv_path = out_dir / "acp28_stepwise_extraction.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8"))) if csv_path.exists() else []
    verdict_counts = Counter(row.get("terminal_status", row.get("overall_verdict", "")) for row in rows)

    summary_row = {
        "campaign": name,
        "spec_dir": str(spec_dir),
        "results_dir": str(out_dir),
        "exit_code": completed.returncode,
        "circuits": len(rows),
        "pass_count": verdict_counts.get("PASS", 0),
        "fail_count": verdict_counts.get("FAIL", 0),
        "robust_pass_count": verdict_counts.get("ROBUST PASS", 0),
        "run_count": verdict_counts.get("RUN", 0),
        "other_count": sum(count for verdict, count in verdict_counts.items() if verdict not in {"PASS", "FAIL", "ROBUST PASS", "RUN"}),
    }

    for row in rows:
        row["campaign"] = name
    return summary_row, rows


def build_markdown(summary_rows: list[dict], per_circuit_rows: list[dict]) -> str:
    lines = [
        "# ACP28 Campaign Matrix",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Campaign | Circuits | PASS | FAIL | ROBUST PASS | RUN | Exit |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['campaign']} | {row['circuits']} | {row['pass_count']} | {row['fail_count']} | "
            f"{row['robust_pass_count']} | {row['run_count']} | {row['exit_code']} |"
        )

    lines.extend([
        "",
        "## Per Circuit",
        "",
        "| Campaign | Circuit | Type | Verdict | Failure kind | Metrics | Count |",
        "|---|---|---|---|---|---|---:|",
    ])
    for row in per_circuit_rows:
        lines.append(
            f"| {row['campaign']} | {row['circuit']} | {row['circuit_type']} | {row.get('terminal_status', row.get('overall_verdict', ''))} | "
            f"{row.get('failure_kind', '') or '-'} | "
            f"{row['extracted_metrics'] or '-'} | {row['metric_count']} |"
        )
    return "\n".join(lines)


def write_outputs(summary_rows: list[dict], per_circuit_rows: list[dict]) -> None:
    if not summary_rows:
        return

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    if per_circuit_rows:
        with PER_CIRCUIT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(per_circuit_rows[0].keys()))
            writer.writeheader()
            writer.writerows(per_circuit_rows)

    payload = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "root": str(ROOT),
        },
        "campaigns": summary_rows,
        "per_circuit": per_circuit_rows,
    }
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    SUMMARY_MD.write_text(build_markdown(summary_rows, per_circuit_rows), encoding="utf-8")


def main():
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    per_circuit_rows = []

    selected = args.campaigns or [name for name, _ in CAMPAIGNS]
    selected_campaigns = [(name, spec_dir) for name, spec_dir in CAMPAIGNS if name in selected]

    for name, spec_dir in selected_campaigns:
        existing_csv = RESULTS_DIR / name / "acp28_stepwise_extraction.csv"
        if args.resume and existing_csv.exists():
            rows = list(csv.DictReader(existing_csv.open(encoding="utf-8")))
            verdict_counts = Counter(row.get("terminal_status", row.get("overall_verdict", "")) for row in rows)
            summary_row = {
                "campaign": name,
                "spec_dir": str(spec_dir),
                "results_dir": str(RESULTS_DIR / name),
                "exit_code": 0,
                "circuits": len(rows),
                "pass_count": verdict_counts.get("PASS", 0),
                "fail_count": verdict_counts.get("FAIL", 0),
                "robust_pass_count": verdict_counts.get("ROBUST PASS", 0),
                "run_count": verdict_counts.get("RUN", 0),
                "other_count": sum(count for verdict, count in verdict_counts.items() if verdict not in {"PASS", "FAIL", "ROBUST PASS", "RUN"}),
            }
            for row in rows:
                row["campaign"] = name
        else:
            summary_row, rows = run_campaign(name, spec_dir)
        summary_rows.append(summary_row)
        per_circuit_rows.extend(rows)
        write_outputs(summary_rows, per_circuit_rows)

    print(f"Summary CSV: {SUMMARY_CSV}")
    print(f"Per-circuit CSV: {PER_CIRCUIT_CSV}")
    print(f"Summary JSON: {SUMMARY_JSON}")
    print(f"Summary Markdown: {SUMMARY_MD}")


if __name__ == "__main__":
    main()
