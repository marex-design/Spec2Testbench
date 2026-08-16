from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def flatten(summary: dict[str, Any], source: Path) -> list[dict[str, Any]]:
    rows = []
    for mode, payload in (summary.get("modes") or {}).items():
        quality = payload.get("llm_quality") or {}
        coverage = payload.get("coverage") or {}
        confusion = payload.get("confusion") or {}
        rows.append({
            "source": str(source),
            "provider": summary.get("provider"),
            "model": summary.get("model"),
            "model_release": summary.get("model_release"),
            "temperature": summary.get("temperature"),
            "mode": mode,
            "cov_circuits": coverage.get("cov_circuits"),
            "cov_metrics": coverage.get("cov_metrics"),
            "cov_analyses": coverage.get("cov_analyses"),
            "accuracy": confusion.get("accuracy"),
            "false_accept_rate": confusion.get("false_accept_rate"),
            "false_reject_rate": confusion.get("false_reject_rate"),
            "json_valid_rate": quality.get("json_valid_rate"),
            "plan_rejection_rate": quality.get("plan_rejection_rate"),
            "final_plan_rejection_rate": quality.get("final_plan_rejection_rate"),
            "feedback_recovery_rate": quality.get("feedback_recovery_rate"),
            "executable_plan_rate": quality.get("executable_plan_rate"),
            "mean_llm_calls": quality.get("mean_llm_calls"),
            "mean_tokens": quality.get("mean_tokens"),
            "mean_latency_seconds": quality.get("mean_latency_seconds"),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare frozen hybrid campaign summaries across exact LLM models")
    parser.add_argument("summaries", nargs="+", help="Paths to campaign summary.json files")
    parser.add_argument("--output", default="results/llm_model_comparison.csv")
    args = parser.parse_args()

    rows = []
    for raw in args.summaries:
        path = Path(raw)
        rows.extend(flatten(json.loads(path.read_text(encoding="utf-8")), path))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No campaign rows found")
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(output)


if __name__ == "__main__":
    main()
