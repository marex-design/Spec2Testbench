import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_CSV = ROOT / "results" / "acp28_campaign_matrix" / "robust_fail_audit.csv"
OUT_CSV = ROOT / "results" / "acp28_campaign_matrix" / "pvt_action_plan.csv"
OUT_MD = ROOT / "results" / "acp28_campaign_matrix" / "pvt_action_plan.md"


def parse_args():
    parser = argparse.ArgumentParser(description="Build an automatic PVT action plan from ACP28 robust fail audit.")
    parser.add_argument("--audit-csv", type=Path, default=AUDIT_CSV)
    parser.add_argument("--output-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--output-md", type=Path, default=OUT_MD)
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def split_metric_names(raw_value: str) -> list[str]:
    if not raw_value.strip():
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def metric_family(metric_name: str) -> str:
    if metric_name.startswith("pvt_"):
        return metric_name
    if "vout" in metric_name:
        return "pvt_vout_variation"
    if "delay" in metric_name:
        return "pvt_delay_variation"
    if "frequency" in metric_name:
        return "pvt_frequency_variation"
    if "gain" in metric_name:
        return "pvt_dc_gain_variation"
    if "power" in metric_name:
        return "pvt_power_variation"
    if "thd" in metric_name:
        return "pvt_thd_variation"
    return metric_name


def classify_priority(circuit_count: int, root_causes: set[str]) -> str:
    if "pvt_extraction_gap" in root_causes and circuit_count >= 3:
        return "P0"
    if circuit_count >= 2:
        return "P1"
    return "P2"


def family_fix(metric_name: str) -> str:
    fixes = {
        "pvt_vout_variation": "Compute output DC spread across PVT runs from the same observed output node and expose it as a summary metric.",
        "pvt_delay_variation": "Measure propagation-delay spread across PVT variants from transient waveforms and expose a single worst-case variation metric.",
        "pvt_frequency_variation": "Measure oscillation-frequency spread across PVT variants from transient or spectral outputs and export the max-minus-min summary.",
        "pvt_dc_gain_variation": "Compute gain spread across PVT variants from AC sweeps instead of reusing the nominal gain value.",
        "pvt_power_variation": "Compute quiescent-power spread across PVT variants from supply current and supply voltage.",
        "pvt_thd_variation": "Compute THD spread across PVT variants from Fourier analyses instead of checking the nominal THD directly.",
    }
    return fixes.get(metric_name, "Implement a dedicated PVT aggregation path for this metric family and expose a max-minus-min summary metric.")


def build_plan_rows(audit_rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in audit_rows:
        problem_metrics = split_metric_names(row.get("missing_metric_names", "")) or split_metric_names(row.get("failed_metric_names", ""))
        for metric_name in problem_metrics:
            grouped[metric_family(metric_name)].append(row)

    plan_rows = []
    for family_name, rows in sorted(grouped.items()):
        circuits = [row["circuit"] for row in rows]
        circuit_types = sorted({row["circuit_type"] for row in rows if row.get("circuit_type")})
        root_causes = {row["root_cause_guess"] for row in rows if row.get("root_cause_guess")}
        failure_kinds = Counter(row["failure_kind"] for row in rows if row.get("failure_kind"))
        plan_rows.append({
            "pvt_metric_family": family_name,
            "priority": classify_priority(len(rows), root_causes),
            "affected_circuits_count": len(rows),
            "affected_circuits": ", ".join(circuits),
            "affected_types": ", ".join(circuit_types),
            "dominant_failure_kind": failure_kinds.most_common(1)[0][0] if failure_kinds else "",
            "root_cause_guess": ", ".join(sorted(root_causes)),
            "implementation_action": family_fix(family_name),
            "validation_goal": f"Turn all current {family_name} audit misses into extracted terminal metrics in robust campaign reruns.",
        })
    return plan_rows


def build_markdown(plan_rows: list[dict]) -> str:
    lines = [
        "# ACP28 PVT Action Plan",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Source audit: `{AUDIT_CSV}`",
        "",
        "| PVT metric family | Priority | Circuits | Failure kind | Root cause | Action |",
        "|---|---|---:|---|---|---|",
    ]
    for row in plan_rows:
        lines.append(
            f"| {row['pvt_metric_family']} | {row['priority']} | {row['affected_circuits_count']} | "
            f"{row['dominant_failure_kind']} | {row['root_cause_guess']} | {row['implementation_action']} |"
        )

    lines.extend(["", "## Detailed Scope", ""])
    for row in plan_rows:
        lines.extend([
            f"### {row['pvt_metric_family']}",
            "",
            f"- Priority: {row['priority']}",
            f"- Affected circuits ({row['affected_circuits_count']}): {row['affected_circuits']}",
            f"- Affected types: {row['affected_types'] or 'n/a'}",
            f"- Dominant failure kind: {row['dominant_failure_kind']}",
            f"- Root cause guess: {row['root_cause_guess']}",
            f"- Implementation action: {row['implementation_action']}",
            f"- Validation goal: {row['validation_goal']}",
            "",
        ])
    return "\n".join(lines)


def main():
    args = parse_args()
    audit_rows = load_rows(args.audit_csv)
    plan_rows = build_plan_rows(audit_rows)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pvt_metric_family",
        "priority",
        "affected_circuits_count",
        "affected_circuits",
        "affected_types",
        "dominant_failure_kind",
        "root_cause_guess",
        "implementation_action",
        "validation_goal",
    ]
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(plan_rows)

    args.output_md.write_text(build_markdown(plan_rows), encoding="utf-8")
    print(f"PVT action plan CSV: {args.output_csv}")
    print(f"PVT action plan Markdown: {args.output_md}")
    print(f"Metric families: {len(plan_rows)}")


if __name__ == "__main__":
    main()
