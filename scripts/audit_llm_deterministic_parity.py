from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_deepseek_testbench_campaign import (
    classification_from_ground_truth,
    load_frozen_v3_reference_rows,
    resolve_manifest_cases,
    run_deterministic_case,
)


CURRENT_DATE = "2026-07-21"
MANIFEST = ROOT / "experiments/llm_deepseek/frozen_manifest.yaml"
RESULTS = ROOT / "results/llm_deepseek"
REPORTS = ROOT / "reports/llm_deepseek"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def as_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def values_match(left: Any, right: Any) -> bool:
    return str(left or "").strip() == str(right or "").strip()


def numeric_equivalent(left: Any, right: Any) -> bool:
    left_value = as_float(left)
    right_value = as_float(right)
    if left_value is None or right_value is None:
        return False
    return math.isclose(left_value, right_value, rel_tol=1e-9, abs_tol=1e-18)


def parity_status(historical: dict[str, str], current: dict[str, str]) -> str:
    if not values_match(historical.get("ground_truth_label"), current.get("ground_truth_label")):
        return "GROUND_TRUTH_MISMATCH"
    if str(current.get("cache_used", "")).strip().lower() == "true":
        return "CACHE_CONTAMINATION"
    if not values_match(historical.get("measurement_backend"), current.get("measurement_backend")):
        return "BACKEND_MISMATCH"
    if not values_match(historical.get("metric_name"), current.get("metric_name")):
        return "METRIC_MISMATCH"
    if not values_match(historical.get("operator"), current.get("metric_operator")):
        return "THRESHOLD_MISMATCH"
    if not values_match(historical.get("threshold"), current.get("metric_threshold")):
        return "THRESHOLD_MISMATCH"
    historical_hash = historical.get("testbench_sha256", "")
    current_hash = current.get("testbench_sha256", "")
    if historical_hash and current_hash and historical_hash != current_hash:
        return "TESTBENCH_MISMATCH"
    if (
        values_match(historical.get("execution_status"), current.get("execution_status"))
        and values_match(historical.get("compliance_status"), current.get("compliance_status"))
        and values_match(historical.get("evaluation_outcome"), current.get("evaluation_outcome"))
        and values_match(historical.get("measured_value"), current.get("metric_value"))
    ):
        return "EXACT_MATCH"
    if (
        values_match(historical.get("execution_status"), current.get("execution_status"))
        and values_match(historical.get("compliance_status"), current.get("compliance_status"))
        and values_match(historical.get("evaluation_outcome"), current.get("evaluation_outcome"))
        and numeric_equivalent(historical.get("measured_value"), current.get("metric_value"))
    ):
        return "NUMERICALLY_EQUIVALENT"
    return "UNKNOWN"


def legacy_root_cause(historical: dict[str, str], legacy: dict[str, Any]) -> str:
    if not values_match(historical.get("metric_name"), legacy.get("metric_name")):
        return "WRONG_METRIC"
    if not values_match(historical.get("operator"), legacy.get("metric_operator")):
        return "WRONG_OPERATOR"
    if not values_match(historical.get("threshold"), legacy.get("metric_threshold")):
        return "WRONG_THRESHOLD"
    if not values_match(historical.get("measurement_backend"), legacy.get("measurement_backend")):
        return "WRONG_BACKEND"
    if historical.get("testbench_sha256") and legacy.get("testbench_sha256") and historical["testbench_sha256"] != legacy["testbench_sha256"]:
        return "WRONG_TESTBENCH"
    if numeric_equivalent(historical.get("measured_value"), legacy.get("metric_value")):
        return "NUMERICAL_TOLERANCE"
    return "UNKNOWN"


def render_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def build_legacy_row(case, report) -> dict[str, Any]:
    target_result = next((item for item in report.spec_results if item.test_name == case.targeted_metric), None)
    target_trace = next((item for item in report.metric_traces if item.metric_name == case.targeted_metric), None)
    compliance_status = report.compliance_status.value
    return {
        "case_id": case.case_id,
        "metric_name": case.targeted_metric,
        "measurement_backend": report.measurement_backend or "",
        "metric_value": target_result.measured_value if target_result else "",
        "metric_operator": target_trace.expected_operator if target_trace else "",
        "metric_threshold": target_trace.expected_threshold if target_trace else "",
        "metric_status": target_trace.status if target_trace else "",
        "compliance_status": compliance_status,
        "evaluation_outcome": classification_from_ground_truth(case.ground_truth_label, compliance_status),
        "execution_status": report.execution_status.value,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
        "testbench_sha256": report.provenance.get("testbench_hash", ""),
        "ngspice_command": report.ngspice_command,
        "stdout": "\n".join(report.simulation_logs or []),
        "stderr": "\n".join(report.simulation_errors or []),
        "native_measurement_source": report.measurement_source or "",
        "scientific_category": report.scientific_category.value,
        "aggregation": report.compliance_status.value,
        "normalized_metric": target_trace.normalized_value if target_trace else "",
        "checker_decision": target_trace.status if target_trace else "",
    }


def write_divergence_report(case, historical: dict[str, str], legacy: dict[str, Any], report) -> None:
    root_cause = legacy_root_cause(historical, legacy)
    testbench_text = report.testbench.generate_spice_deck() if report.testbench else ""
    write_text(
        REPORTS / f"deterministic_divergence_{case.case_id}.md",
        f"""
# Deterministic Divergence {case.case_id}

Date: {CURRENT_DATE}

- Root cause: `{root_cause}`
- Historical evaluation outcome: `{historical.get("evaluation_outcome", "")}`
- Replay evaluation outcome: `{legacy.get("evaluation_outcome", "")}`
- Historical backend: `{historical.get("measurement_backend", "")}`
- Replay backend: `{legacy.get("measurement_backend", "")}`
- Historical value: `{historical.get("measured_value", "")}`
- Replay value: `{legacy.get("metric_value", "")}`
- Threshold / operator: `{legacy.get("metric_operator", "")} {legacy.get("metric_threshold", "")}`

Trace:

- Manifest: `{MANIFEST.relative_to(ROOT)}`
- Specification: `{case.specification_file.relative_to(ROOT)}`
- Netlist: `{case.netlist_file.relative_to(ROOT)}`
- Native measurement source: `{legacy.get("native_measurement_source", "")}`
- Checker decision: `{legacy.get("checker_decision", "")}`
- Ground-truth mapping: `{case.ground_truth_label} -> {legacy.get("evaluation_outcome", "")}`
- Aggregation: `{legacy.get("aggregation", "")}`

Generated testbench:

```spice
{testbench_text}
```

ngspice command:

```text
{" ".join(legacy.get("ngspice_command", []))}
```

stdout:

```text
{legacy.get("stdout", "").strip()}
```

stderr:

```text
{legacy.get("stderr", "").strip()}
```
""",
    )


def main() -> None:
    historical_rows = load_frozen_v3_reference_rows()
    current_rows = {
        row["case_id"]: row
        for row in read_csv(RESULTS / "use_case_results.csv")
        if row.get("generation_mode") == "deterministic"
    }
    cases = resolve_manifest_cases(MANIFEST)

    case_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    hash_rows: list[dict[str, object]] = []
    legacy_divergences: list[tuple[str, str]] = []

    for case in cases:
        historical = historical_rows[case.case_id]
        current = current_rows[case.case_id]
        status = parity_status(historical, current)
        case_rows.append(
            {
                "case_id": case.case_id,
                "ground_truth_label": historical.get("ground_truth_label", ""),
                "historical_execution_status": historical.get("execution_status", ""),
                "new_execution_status": current.get("execution_status", ""),
                "historical_backend": historical.get("measurement_backend", ""),
                "new_backend": current.get("measurement_backend", ""),
                "historical_metric_name": historical.get("metric_name", ""),
                "new_metric_name": current.get("metric_name", ""),
                "historical_metric_value": historical.get("measured_value", ""),
                "new_metric_value": current.get("metric_value", ""),
                "historical_operator": historical.get("operator", ""),
                "new_operator": current.get("metric_operator", ""),
                "historical_threshold": historical.get("threshold", ""),
                "new_threshold": current.get("metric_threshold", ""),
                "historical_compliance_status": historical.get("compliance_status", ""),
                "new_compliance_status": current.get("compliance_status", ""),
                "historical_evaluation_outcome": historical.get("evaluation_outcome", ""),
                "new_evaluation_outcome": current.get("evaluation_outcome", ""),
                "netlist_sha256": current.get("netlist_sha256", historical.get("netlist_sha256", "")),
                "specification_sha256": current.get("specification_sha256", historical.get("specification_sha256", "")),
                "testbench_sha256": current.get("testbench_sha256", historical.get("testbench_sha256", "")),
                "manifest_source": current.get("manifest_source", ""),
                "cache_used": current.get("cache_used", False),
                "parity_status": status,
            }
        )
        historical_value = as_float(historical.get("measured_value"))
        current_value = as_float(current.get("metric_value"))
        absolute_delta = None if historical_value is None or current_value is None else abs(historical_value - current_value)
        relative_delta = None
        if absolute_delta is not None and historical_value not in {None, 0.0}:
            relative_delta = absolute_delta / abs(historical_value)
        metric_rows.append(
            {
                "case_id": case.case_id,
                "metric_name": historical.get("metric_name", ""),
                "historical_metric_value": historical.get("measured_value", ""),
                "new_metric_value": current.get("metric_value", ""),
                "absolute_delta": absolute_delta,
                "relative_delta": relative_delta,
                "operator_match": values_match(historical.get("operator"), current.get("metric_operator")),
                "threshold_match": values_match(historical.get("threshold"), current.get("metric_threshold")),
                "parity_status": status,
            }
        )
        hash_rows.append(
            {
                "case_id": case.case_id,
                "historical_netlist_sha256": historical.get("netlist_sha256", ""),
                "new_netlist_sha256": current.get("netlist_sha256", ""),
                "historical_specification_sha256": historical.get("specification_sha256", ""),
                "new_specification_sha256": current.get("specification_sha256", ""),
                "historical_testbench_sha256": historical.get("testbench_sha256", ""),
                "new_testbench_sha256": current.get("testbench_sha256", ""),
                "artifact_hash_parity_status": "EXACT_MATCH"
                if values_match(historical.get("netlist_sha256"), current.get("netlist_sha256"))
                and values_match(historical.get("specification_sha256"), current.get("specification_sha256"))
                and values_match(historical.get("testbench_sha256"), current.get("testbench_sha256"))
                else "UNKNOWN",
            }
        )

        _, replay = run_deterministic_case(case, timeout=60, deterministic_source="pipeline_replay")
        report = replay["report"]
        legacy = build_legacy_row(case, report)
        if legacy["evaluation_outcome"] != historical.get("evaluation_outcome", ""):
            legacy_divergences.append((case.case_id, legacy_root_cause(historical, legacy)))
            write_divergence_report(case, historical, legacy, report)

    write_csv(RESULTS / "deterministic_parity_case_by_case.csv", case_rows)
    write_csv(RESULTS / "deterministic_metric_parity.csv", metric_rows)
    write_csv(RESULTS / "deterministic_artifact_hash_comparison.csv", hash_rows)

    exact_matches = sum(row["parity_status"] == "EXACT_MATCH" for row in case_rows)
    numeric_matches = sum(row["parity_status"] == "NUMERICALLY_EQUIVALENT" for row in case_rows)
    divergence_table = render_table(
        ["Case", "Legacy Replay Root Cause"],
        [[case_id, cause] for case_id, cause in legacy_divergences] or [["none", "none"]],
    )
    write_text(
        REPORTS / "deterministic_parity_audit.md",
        f"""
# Deterministic Parity Audit

Date: {CURRENT_DATE}

- Deterministic source: `frozen_v3_reference`
- Cases audited: {len(case_rows)}
- Exact matches: {exact_matches}
- Numeric equivalents: {numeric_matches}
- Divergences: {len(case_rows) - exact_matches - numeric_matches}
- Legacy replay classification divergences: {len(legacy_divergences)}

{render_table(
    ["Case", "Parity Status", "Historical Outcome", "New Outcome"],
    [
        [row["case_id"], row["parity_status"], row["historical_evaluation_outcome"], row["new_evaluation_outcome"]]
        for row in case_rows
    ],
)}

Legacy replay divergences kept for forensic traceability:

{divergence_table}
""",
    )


if __name__ == "__main__":
    main()
