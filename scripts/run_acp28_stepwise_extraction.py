import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmark" / "analogcoder_pro"
DEFAULT_SPEC_DIR = ROOT / "examples" / "benchmark_specs"
DEFAULT_RESULTS_DIR = ROOT / "results" / "acp28_stepwise_extraction"
MANIFEST_PATH = BENCH_DIR / "manifest.csv"
CLI_COMMAND = [
    str(ROOT / ".venv" / "Scripts" / "python.exe"),
    "-m",
    "spec2testbench.presentation.cli.main",
    "verify",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Run ACP28 stepwise extraction checks via the framework CLI.")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N circuits (0 = all).")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N circuits before running.")
    parser.add_argument("--spec-dir", type=Path, default=DEFAULT_SPEC_DIR, help="Directory containing ACP28 YAML specs.")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="Directory where run artifacts are written.")
    return parser.parse_args()


def load_manifest():
    rows = []
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    return rows


def latest_json_report(report_dir: Path):
    candidates = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def parse_report(report_path: Path | None):
    if not report_path or not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


def summarize_rows(rows: list[dict]) -> dict:
    return {
        "total_circuits": len(rows),
        "command_ok": sum(1 for row in rows if row["command_ok"]),
        "report_exists": sum(1 for row in rows if row["report_exists"]),
        "testbench_generation_success": sum(1 for row in rows if row["testbench_generation_success"]),
        "simulation_success": sum(1 for row in rows if row["simulation_success"]),
        "metrics_extracted_ok": sum(1 for row in rows if row["metrics_extracted_ok"]),
        "zero_metric_circuits": [row["circuit"] for row in rows if row["metric_count"] == 0],
    }


def build_markdown(rows: list[dict], summary: dict) -> str:
    lines = [
        "# ACP28 Stepwise Extraction",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Total circuits: {summary['total_circuits']}",
        f"- CLI command ok: {summary['command_ok']}",
        f"- JSON report exists: {summary['report_exists']}",
        f"- Testbench generation success: {summary['testbench_generation_success']}",
        f"- Simulation success: {summary['simulation_success']}",
        f"- Metrics extracted ok: {summary['metrics_extracted_ok']}",
        f"- Zero-metric circuits: {', '.join(summary['zero_metric_circuits']) or 'none'}",
        "",
        "| Circuit | Type | CLI | Report | TB gen | Sim | Metrics | Count | Extracted metrics | Errors |",
        "|---|---|---|---|---|---|---|---:|---|---|",
    ]

    for row in rows:
        lines.append(
            f"| {row['circuit']} | {row['circuit_type']} | {row['command_ok']} | "
            f"{row['report_exists']} | {row['testbench_generation_success']} | "
            f"{row['simulation_success']} | {row['metrics_extracted_ok']} | {row['metric_count']} | "
            f"{row['extracted_metrics'] or '-'} | {row['errors'] or '-'} |"
        )

    return "\n".join(lines)


def write_outputs(rows: list[dict], results_dir: Path, spec_dir: Path) -> None:
    if not rows:
        return

    summary = summarize_rows(rows)
    out_csv = results_dir / "acp28_stepwise_extraction.csv"
    out_json = results_dir / "acp28_stepwise_extraction.json"
    out_md = results_dir / "acp28_stepwise_extraction.md"

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "root": str(ROOT),
            "bench_dir": str(BENCH_DIR),
            "spec_dir": str(spec_dir),
            "results_dir": str(results_dir),
            "command_prefix": " ".join(CLI_COMMAND),
        },
        "summary": summary,
        "circuits": rows,
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(build_markdown(rows, summary), encoding="utf-8")


def main():
    args = parse_args()
    spec_dir = args.spec_dir.resolve()
    results_dir = args.results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_manifest()

    if args.offset:
        manifest_rows = manifest_rows[args.offset:]
    if args.limit:
        manifest_rows = manifest_rows[:args.limit]

    rows = []

    for manifest_row in manifest_rows:
        netlist_name = manifest_row["netlist"]
        spec_name = manifest_row["spec"]
        stem = Path(netlist_name).stem
        case_dir = results_dir / stem
        case_dir.mkdir(parents=True, exist_ok=True)

        spec_path = spec_dir / spec_name
        netlist_path = BENCH_DIR / netlist_name
        command = CLI_COMMAND + [
            "--specs", str(spec_path),
            "--netlist", str(netlist_path),
            "--no-llm",
            "--format", "json",
            "--output", str(case_dir),
        ]

        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        (case_dir / "stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
        (case_dir / "stderr.txt").write_text(completed.stderr or "", encoding="utf-8")

        report_path = latest_json_report(case_dir / "reports")
        report_data = parse_report(report_path)
        metrics = report_data.get("metrics", []) if report_data else []
        metric_names = [metric.get("name", "") for metric in metrics if metric.get("name")]
        errors = report_data.get("errors", []) if report_data else []
        error_text = " | ".join(errors)

        rows.append({
            "circuit": stem,
            "circuit_type": manifest_row["circuit_type"],
            "command_ok": completed.returncode in (0, 1),
            "exit_code": completed.returncode,
            "report_exists": bool(report_path and report_path.exists()),
            "testbench_generation_success": bool(report_data.get("testbench_generation_success")) if report_data else False,
            "simulation_success": bool(report_data.get("simulation_success")) if report_data else False,
            "metrics_extracted_ok": len(metric_names) > 0,
            "metric_count": len(metric_names),
            "extracted_metrics": ", ".join(metric_names),
            "overall_verdict": report_data.get("overall_verdict", "") if report_data else "",
            "compliance_score": report_data.get("compliance_score", "") if report_data else "",
            "errors": error_text,
            "json_report_path": str(report_path.relative_to(ROOT)) if report_path else "",
        })
        write_outputs(rows, results_dir, spec_dir)

    summary = summarize_rows(rows)
    print(f"CSV: {results_dir / 'acp28_stepwise_extraction.csv'}")
    print(f"JSON: {results_dir / 'acp28_stepwise_extraction.json'}")
    print(f"Markdown: {results_dir / 'acp28_stepwise_extraction.md'}")
    print(f"Processed circuits: {summary['total_circuits']}")


if __name__ == "__main__":
    main()
