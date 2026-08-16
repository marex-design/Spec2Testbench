from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.evaluation_metrics import (
    compute_coverage,
    confusion_from_rows,
    llm_quality_summary,
    majority_vote_rows,
    mcnemar_exact,
)
from spec2testbench.application.services.hybrid_feedback_loop import HybridFeedbackLoop, RetryPolicy
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator


def _repo_path(value: str) -> Path:
    # Ground-truth manifests may have been frozen on Windows.  Normalize their
    # separators so the same scientific manifest is executable cross-platform.
    return ROOT / Path(str(value).replace("\\", "/"))


def load_cases(manifest: Path, limit: int = 0) -> list[dict[str, Any]]:
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    cases = []
    for record in data.get("cases", []):
        spec = record.get("specification_file")
        netlist = record.get("netlist_file")
        if not spec or not netlist:
            continue
        cases.append({
            "case_id": record.get("case_id") or Path(spec).stem,
            "ground_truth_label": record.get("ground_truth_label", ""),
            "specification_file": _repo_path(spec),
            "netlist_file": _repo_path(netlist),
        })
    return cases[:limit] if limit else cases


def make_provider(args):
    if args.provider == "stub":
        return DeterministicStubProvider(), "STUB", False
    config = DeepSeekProviderConfig(
        api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com",
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout,
        max_retries=args.provider_retries,
    )
    return DeepSeekProvider(config), "LIVE", True


def report_row(case, mode: str, trial: int, result=None, report=None) -> dict[str, Any]:
    if result is not None:
        report = result.report
        validation = result.planning_outcome.validation
        requested = len(result.planning_outcome.request_payload.get("requested_metrics", []))
        evaluated = 0 if report is None else sum(1 for item in report.spec_results if item.measured_value is not None)
        issues = " | ".join(issue.status.value for issue in validation.issues)
        execution_status = "" if report is None else report.execution_status.value
        compliance_status = "NOT_EVALUATED" if report is None else report.compliance_status.value
        analysis_type = result.planning_outcome.parsed_plan.analysis_type.value if result.planning_outcome.parsed_plan else ""
        row = result.to_dict()
        initial_validation = row.get("initial_validation") or {}
        initial_issues = " | ".join(
            str(issue.get("status") or "") for issue in initial_validation.get("issues", [])
        )
        return {
            "case_id": case["case_id"],
            "trial": trial,
            "mode": mode,
            "ground_truth_label": case["ground_truth_label"],
            "initial_plan_status": row.get("initial_plan_status", ""),
            "initial_json_valid": row.get("initial_json_valid", row["json_valid"]),
            "initial_plan_valid": row.get("initial_plan_valid", row["final_plan_valid"]),
            "json_valid": row["json_valid"],
            "final_plan_valid": row["final_plan_valid"],
            "issues": issues,
            "initial_issues": initial_issues,
            "repair_count": result.repair_count,
            "llm_call_count": result.llm_call_count,
            "requested_metric_count": requested,
            "evaluated_metric_count": evaluated,
            "requested_analysis_count": 1 if analysis_type else 0,
            "executed_analysis_count": 1 if execution_status == "SUCCESS" and analysis_type else 0,
            "analysis_type": analysis_type,
            "execution_status": execution_status,
            "compliance_status": compliance_status,
            "final_status": result.final_status.value,
            "invariants_ok": result.invariants_ok,
            "stopped_on_electrical_fail": result.stopped_on_electrical_fail,
            "total_tokens": row["total_tokens"],
            "total_llm_latency_seconds": row["total_llm_latency_seconds"],
            "provider_transport_attempt_count": row.get("provider_transport_attempt_count", 0),
            "provider_transport_retry_count": row.get("provider_transport_retry_count", 0),
            "prompt_sha256": row.get("prompt_sha256", ""),
        }

    requested = len(report.specification.performance_targets) if getattr(report, "specification", None) else len(report.spec_results)
    evaluated = sum(1 for item in report.spec_results if item.measured_value is not None)
    return {
        "case_id": case["case_id"],
        "trial": trial,
        "mode": mode,
        "ground_truth_label": case["ground_truth_label"],
        "initial_plan_status": "NOT_APPLICABLE",
        "initial_json_valid": True,
        "initial_plan_valid": True,
        "json_valid": True,
        "final_plan_valid": True,
        "issues": "",
        "initial_issues": "",
        "repair_count": 0,
        "llm_call_count": 0,
        "requested_metric_count": requested,
        "evaluated_metric_count": evaluated,
        "requested_analysis_count": len(report.testbench.analyses) if report.testbench else 0,
        "executed_analysis_count": len(report.testbench.analyses) if report.execution_status.value == "SUCCESS" and report.testbench else 0,
        "analysis_type": ",".join(a.type.value for a in report.testbench.analyses) if report.testbench else "",
        "execution_status": report.execution_status.value,
        "compliance_status": report.compliance_status.value,
        "final_status": report.overall_verdict.value,
        "invariants_ok": True,
        "stopped_on_electrical_fail": False,
        "total_tokens": 0,
        "total_llm_latency_seconds": 0.0,
        "provider_transport_attempt_count": 0,
        "provider_transport_retry_count": 0,
        "prompt_sha256": "",
    }




def raw_diagnostic_row(case: dict[str, Any], trial: int, outcome) -> dict[str, Any]:
    validation = outcome.validation
    issues = " | ".join(issue.status.value for issue in validation.issues)
    analysis_type = outcome.parsed_plan.analysis_type.value if outcome.parsed_plan else ""
    call_history = list(getattr(outcome, "call_history", []) or [])
    return {
        "case_id": case["case_id"],
        "trial": trial,
        "mode": "llm_raw_diagnostic",
        "ground_truth_label": case["ground_truth_label"],
        "initial_plan_status": validation.status.value,
        "initial_json_valid": validation.status.value not in {"INVALID_JSON", "SCHEMA_ERROR"},
        "initial_plan_valid": validation.is_valid,
        "json_valid": validation.status.value not in {"INVALID_JSON", "SCHEMA_ERROR"},
        "final_plan_valid": validation.is_valid,
        "issues": issues,
        "initial_issues": issues,
        "repair_count": 0,
        "llm_call_count": len(call_history),
        "requested_metric_count": len(outcome.request_payload.get("requested_metrics", [])),
        "evaluated_metric_count": 0,
        "requested_analysis_count": 1 if analysis_type else 0,
        "executed_analysis_count": 0,
        "analysis_type": analysis_type,
        "execution_status": "NOT_EXECUTED_SAFETY_DIAGNOSTIC",
        "compliance_status": "NOT_EVALUATED",
        "final_status": validation.status.value,
        "invariants_ok": True,
        "stopped_on_electrical_fail": False,
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in call_history),
        "total_llm_latency_seconds": sum(float(item.get("latency_seconds") or 0.0) for item in call_history),
        "prompt_sha256": outcome.prompt_sha256,
        "provider_transport_attempt_count": sum(len(item.get("attempts") or []) for item in call_history),
        "provider_transport_retry_count": sum(max(len(item.get("attempts") or []) - 1, 0) for item in call_history),
    }


def write_llm_artifacts(out_dir: Path, case_id: str, mode: str, trial: int, outcome, result=None) -> None:
    run_dir = out_dir / "evidence" / case_id / mode / f"trial_{trial:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request_payload.json").write_text(
        json.dumps(outcome.request_payload, indent=2, default=str), encoding="utf-8"
    )
    (run_dir / "system_prompt.txt").write_text(outcome.system_prompt, encoding="utf-8")
    (run_dir / "raw_response.txt").write_text(outcome.raw_response, encoding="utf-8")
    (run_dir / "plan_validation.json").write_text(
        json.dumps(outcome.validation.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (run_dir / "provider_call_history.json").write_text(
        json.dumps(outcome.call_history, indent=2, default=str), encoding="utf-8"
    )
    if result is not None:
        (run_dir / "hybrid_evidence.json").write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )

def summarize_mode(rows: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = compute_coverage(rows).to_dict()
    confusion_run = confusion_from_rows(rows).to_dict()
    case_rows = majority_vote_rows(rows)
    confusion_case = confusion_from_rows(case_rows).to_dict()
    quality = llm_quality_summary(rows)
    return {
        "coverage": coverage,
        "confusion": confusion_run,
        "confusion_run_level": confusion_run,
        "confusion_case_level_majority": confusion_case,
        "case_level_majority_rows": case_rows,
        "llm_quality": quality,
    }


def stability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["case_id"], row["mode"]), []).append(row)
    out = []
    for (case_id, mode), items in groups.items():
        if len(items) <= 1:
            continue
        out.append({
            "case_id": case_id,
            "mode": mode,
            "trials": len(items),
            "plan_valid_stability": len({bool(i["final_plan_valid"]) for i in items}) == 1,
            "analysis_stability": len({i["analysis_type"] for i in items}) == 1,
            "verdict_stability": len({i["compliance_status"] for i in items}) == 1,
            "repair_count_mean": statistics.mean(int(i["repair_count"]) for i in items),
            "llm_latency_median_s": statistics.median(float(i["total_llm_latency_seconds"]) for i in items),
        })
    return out




def comparison_delta(summary: dict[str, Any], left: str, right: str) -> dict[str, float]:
    if left not in summary.get("modes", {}) or right not in summary.get("modes", {}):
        return {}
    l = summary["modes"][left]
    r = summary["modes"][right]
    pairs = {
        "cov_circuits": (l["coverage"].get("cov_circuits", 0.0), r["coverage"].get("cov_circuits", 0.0)),
        "cov_metrics": (l["coverage"].get("cov_metrics", 0.0), r["coverage"].get("cov_metrics", 0.0)),
        "cov_analyses": (l["coverage"].get("cov_analyses", 0.0), r["coverage"].get("cov_analyses", 0.0)),
        "accuracy": (l["confusion_case_level_majority"].get("accuracy", 0.0), r["confusion_case_level_majority"].get("accuracy", 0.0)),
        "false_accept_rate": (l["confusion_case_level_majority"].get("false_accept_rate", 0.0), r["confusion_case_level_majority"].get("false_accept_rate", 0.0)),
        "false_reject_rate": (l["confusion_case_level_majority"].get("false_reject_rate", 0.0), r["confusion_case_level_majority"].get("false_reject_rate", 0.0)),
        "executable_plan_rate": (l["llm_quality"].get("executable_plan_rate", 0.0), r["llm_quality"].get("executable_plan_rate", 0.0)),
        "final_plan_rejection_rate": (l["llm_quality"].get("final_plan_rejection_rate", 0.0), r["llm_quality"].get("final_plan_rejection_rate", 0.0)),
        "mean_tokens": (l["llm_quality"].get("mean_tokens", 0.0), r["llm_quality"].get("mean_tokens", 0.0)),
        "mean_latency_seconds": (l["llm_quality"].get("mean_latency_seconds", 0.0), r["llm_quality"].get("mean_latency_seconds", 0.0)),
    }
    return {name: float(a) - float(b) for name, (a, b) in pairs.items()}


def aggregate_stability(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"groups": 0, "plan_valid_stability_rate": 0.0, "analysis_stability_rate": 0.0, "verdict_stability_rate": 0.0}
    return {
        "groups": len(items),
        "plan_valid_stability_rate": sum(bool(item["plan_valid_stability"]) for item in items) / len(items),
        "analysis_stability_rate": sum(bool(item["analysis_stability"]) for item in items) / len(items),
        "verdict_stability_rate": sum(bool(item["verdict_stability"]) for item in items) / len(items),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare deterministic, LLM one-shot, and hybrid feedback verification")
    parser.add_argument("--manifest", default="experiments/ground_truth/ground_truth_manifest.yaml")
    parser.add_argument("--provider", choices=["deepseek", "stub"], default="stub")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-stub-v1"))
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--provider-retries", type=int, default=3)
    parser.add_argument(
        "--model-release",
        default=os.getenv("LLM_MODEL_RELEASE", ""),
        help="Optional provider-published model version/date for reproducibility; never guessed by the framework",
    )
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--modes",
        default="deterministic,llm_raw_diagnostic,llm_one_shot,hybrid",
        help="Comma-separated modes. Raw LLM is diagnostic-only and is never executed without the deterministic safety gate.",
    )
    parser.add_argument("--output", default="results/hybrid_feedback_campaign")
    args = parser.parse_args()

    cases = load_cases(ROOT / args.manifest, args.limit)
    provider, provider_mode, scientific_evidence = make_provider(args)
    modes = {item.strip() for item in args.modes.split(",") if item.strip()}
    rows: list[dict[str, Any]] = []
    out_dir = ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    run_started_utc = datetime.now(timezone.utc).isoformat()

    for case in cases:
        specification = Specification.from_yaml(case["specification_file"])
        specification.case_id = case["case_id"]
        if "deterministic" in modes:
            pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=int(args.timeout))
            report = pipeline.verify(specification, netlist_path=case["netlist_file"], spec_path=case["specification_file"])
            rows.append(report_row(case, "deterministic", 0, report=report))

        if "llm_raw_diagnostic" in modes:
            for trial in range(1, args.trials + 1):
                raw_specification = Specification.from_yaml(case["specification_file"])
                raw_specification.case_id = case["case_id"]
                deterministic_tb = TestBenchGenerator(use_llm=False).generate(
                    raw_specification, netlist_path=case["netlist_file"]
                )
                raw_outcome = LLMGenerationService(provider).generate_plan(
                    specification=raw_specification,
                    netlist_path=case["netlist_file"],
                    deterministic_testbench=deterministic_tb,
                    model=args.model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    top_p=args.top_p,
                    timeout_seconds=args.timeout,
                    include_deterministic_summary=False,
                    max_repairs=0,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_evidence,
                )
                rows.append(raw_diagnostic_row(case, trial, raw_outcome))
                write_llm_artifacts(out_dir, case["case_id"], "llm_raw_diagnostic", trial, raw_outcome)

        for mode, retries in (("llm_one_shot", 0), ("hybrid", args.max_retries)):
            if mode not in modes:
                continue
            for trial in range(1, args.trials + 1):
                # Re-create provider for live trials only if desired by external SDK; provider itself is stateless for requests.
                loop = HybridFeedbackLoop(
                    LLMGenerationService(provider),
                    retry_policy=RetryPolicy(max_retries=retries),
                )
                trial_specification = Specification.from_yaml(case["specification_file"])
                trial_specification.case_id = case["case_id"]
                result = loop.run(
                    specification=trial_specification,
                    netlist_path=case["netlist_file"],
                    model=args.model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    top_p=args.top_p,
                    timeout_seconds=args.timeout,
                    include_deterministic_summary=True,
                    provider_mode=provider_mode,
                    scientific_llm_evidence=scientific_evidence,
                    spec_path=case["specification_file"],
                )
                rows.append(report_row(case, mode, trial, result=result))
                write_llm_artifacts(out_dir, case["case_id"], mode, trial, result.planning_outcome, result=result)

    with (out_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader(); writer.writerows(rows)

    summary = {
        "provider": args.provider,
        "model": args.model,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "max_retries": args.max_retries,
        "provider_transport_retries": args.provider_retries,
        "model_release": args.model_release or None,
        "trials": args.trials,
        "scientific_llm_evidence": scientific_evidence,
        "run_started_utc": run_started_utc,
        "sampling": {"temperature": args.temperature, "top_p": args.top_p},
        "system_prompt_file": "spec2testbench/infrastructure/llm/prompts/deepseek_testbench_planner_v1.txt",
        "raw_llm_policy": "DIAGNOSTIC_ONLY_NO_EXECUTION",
        "modes": {},
        "stability": stability(rows),
    }
    for mode in sorted({row["mode"] for row in rows}):
        summary["modes"][mode] = summarize_mode([row for row in rows if row["mode"] == mode])
    summary["stability_summary"] = aggregate_stability(summary["stability"])
    summary["comparison_deltas"] = {
        "hybrid_minus_llm_one_shot": comparison_delta(summary, "hybrid", "llm_one_shot"),
        "hybrid_minus_deterministic": comparison_delta(summary, "hybrid", "deterministic"),
        "llm_one_shot_minus_llm_raw_diagnostic": comparison_delta(summary, "llm_one_shot", "llm_raw_diagnostic"),
    }
    summary["paired_significance"] = {}
    for left, right in (("deterministic", "hybrid"), ("llm_one_shot", "hybrid")):
        if left in summary["modes"] and right in summary["modes"]:
            summary["paired_significance"][f"{left}_vs_{right}"] = mcnemar_exact(
                summary["modes"][left]["case_level_majority_rows"],
                summary["modes"][right]["case_level_majority_rows"],
            )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
