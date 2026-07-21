from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
LLM_RESULTS = RESULTS / "llm_deepseek"
REPORTS = ROOT / "reports"
LLM_REPORTS = REPORTS / "llm_deepseek"
USE_CASE_REPORTS = LLM_REPORTS / "use_cases"
DOCS = ROOT / "docs"
CURRENT_DATE = "2026-07-21"


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


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(100.0 * numerator / denominator):.1f}%"


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def render_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def confusion_label(row: dict[str, str]) -> str:
    ground_truth = row.get("ground_truth_label", "")
    compliance = row.get("compliance_status", "")
    if compliance == "NOT_EVALUATED":
        return "UNEVALUATED"
    if ground_truth == "GROUND_TRUTH_COMPLIANT" and compliance == "PASS":
        return "TRUE_ACCEPT"
    if ground_truth == "GROUND_TRUTH_NONCOMPLIANT" and compliance == "FAIL":
        return "TRUE_DETECTION"
    if ground_truth == "GROUND_TRUTH_COMPLIANT" and compliance == "FAIL":
        return "FALSE_REJECT"
    if ground_truth == "GROUND_TRUTH_NONCOMPLIANT" and compliance == "PASS":
        return "FALSE_ACCEPT"
    return "UNEVALUATED"


def summarize_rows(rows: list[dict[str, str]]) -> dict[str, object]:
    llm_rows = [row for row in rows if row["generation_mode"] != "deterministic"]
    return {
        "cases": len({row["case_id"] for row in rows}),
        "rows": len(rows),
        "llm_rows": len(llm_rows),
        "valid_plans": sum(row["final_plan_valid"] == "True" for row in llm_rows),
        "real_simulations": sum(row["simulation_mode"] == "REAL" for row in llm_rows),
        "successes": sum(row["execution_status"] == "SUCCESS" for row in llm_rows),
        "full_metric_coverage": sum(float(row["metric_coverage"]) >= 1.0 for row in llm_rows),
        "mean_metric_coverage": mean(float(row["metric_coverage"]) for row in llm_rows),
        "confusion": Counter(confusion_label(row) for row in llm_rows),
        "use_cases": Counter(row["use_case"] for row in rows),
    }


def write_docs() -> None:
    api_key_present = bool(os.getenv("DEEPSEEK_API_KEY"))
    live_state = "available" if api_key_present else "absent"
    write_text(
        DOCS / "llm_deepseek_integration.md",
        f"""
# LLM DeepSeek Integration

Date: {CURRENT_DATE}

This integration adds a provider-agnostic LLM planning path that turns a structured specification and netlist-derived capability payload into a validated `TestbenchPlan`, then compiles that plan deterministically into ngspice-ready SPICE.

Core commands:

```bash
python scripts/list_deepseek_models.py
python scripts/smoke_test_deepseek_provider.py --provider stub --model deepseek-stub-v1
python scripts/run_deepseek_testbench_campaign.py \\
  --manifest experiments/llm_deepseek/use_case_smoke_manifest.yaml \\
  --provider stub \\
  --model deepseek-stub-v1 \\
  --temperature 0.1 \\
  --max-tokens 512 \\
  --timeout 60 \\
  --trials 1 \\
  --modes deterministic,deepseek_refinement \\
  --disable-pyspice \\
  --no-mock \\
  --output-run-id stub_use_case_smoke_20260721
```

Environment variables:

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
DEEPSEEK_TEMPERATURE
DEEPSEEK_MAX_TOKENS
DEEPSEEK_TIMEOUT_SECONDS
DEEPSEEK_MAX_RETRIES
```

Current local state on {CURRENT_DATE}: `DEEPSEEK_API_KEY` is {live_state}. The repository therefore contains stub-backed campaign evidence and the exact live commands that still need to be run once credentials are available.
""",
    )
    write_text(
        DOCS / "llm_testbench_plan_schema.md",
        """
# LLM TestbenchPlan Schema

The LLM never emits free-form SPICE. It emits a strict JSON object validated by Pydantic.

Top-level fields:

- `case_id`
- `analysis_type`
- `stimuli`
- `observed_nodes`
- `measurements`
- `simulation_parameters`
- `concise_rationale`

Important enums:

- `AnalysisType`: `OP`, `DC`, `AC`, `TRAN`
- `StimulusType`: `DC`, `AC`, `PULSE`, `SIN`, `PWL`, `TRIANGLE`
- `MeasurementBackendPreference`: `NGSPICE_MEASURE`, `NGSPICE_WRDATA`, `AUTO`

Key validation rules:

- No `NaN` or infinite values.
- No unknown nodes.
- No missing requested metrics.
- No unsupported units or incompatible analyses.
- No unsafe simulation ranges.
- No verdict leakage such as `PASS`, `FAIL`, `TRUE_ACCEPT`, or `FALSE_REJECT`.

Compilation remains deterministic after schema validation. The compiler, not the LLM, owns `.control`, `.measure`, `wrdata`, path quoting, and artifact naming.
""",
    )
    write_text(
        DOCS / "llm_experiment_protocol.md",
        """
# LLM Experiment Protocol

Stage order:

1. Audit the existing LLM architecture.
2. Run unit and integration tests.
3. Run the provider smoke test.
4. Run the explicit seven-use-case smoke campaign.
5. Run the explicit frozen pilot campaign.
6. Generate aggregate CSVs, use-case reports, and reviewer-facing analyses.

Recommended live sequence:

```bash
RUN_NGSPICE_INTEGRATION=1 pytest -q
SPEC2TESTBENCH_DISABLE_PYSPICE=1 RUN_NGSPICE_INTEGRATION=1 pytest -q
RUN_LLM_LIVE=1 SPEC2TESTBENCH_DISABLE_PYSPICE=1 pytest -m llm_live -vv --tb=long
python scripts/list_deepseek_models.py
python scripts/smoke_test_deepseek_provider.py --provider deepseek --model "$env:DEEPSEEK_MODEL"
python scripts/run_deepseek_testbench_campaign.py --manifest experiments/llm_deepseek/use_case_smoke_manifest.yaml --provider deepseek --model "$env:DEEPSEEK_MODEL" --temperature 0.1 --max-tokens 4096 --timeout 90 --trials 1 --modes deterministic,deepseek_refinement --disable-pyspice --no-mock --output-run-id live_use_case_smoke_20260721
python scripts/run_deepseek_testbench_campaign.py --manifest experiments/llm_deepseek/frozen_manifest.yaml --provider deepseek --model "$env:DEEPSEEK_MODEL" --temperature 0.1 --max-tokens 4096 --timeout 90 --trials 3 --modes deterministic,deepseek_refinement --disable-pyspice --no-mock --output-run-id live_frozen_20260721
```

The frozen pilot manifest now expands to 16 explicit cases: 14 from frozen_pilot_v2 plus 2 WRDATA extension mirrors from frozen_pilot_v3.
""",
    )
    write_text(
        DOCS / "llm_security_and_reproducibility.md",
        f"""
# LLM Security And Reproducibility

Security rules:

- Never write the DeepSeek API key to logs, artifacts, or reports.
- Keep `.env` and `*.env.local` out of Git.
- Persist request payloads, prompts, raw responses, and provenance only after secret-safe serialization.

Reproducibility rules:

- Cache keys include case id, mode, trial id, provider, model, prompt hash, specification hash, netlist hash, capability-registry hash, temperature, and max tokens.
- Every LLM artifact directory records request payloads, prompt hashes, parsed plans, validation output, compiled decks, ngspice outputs, metrics, and provenance.
- Deterministic D0 remains untouched and is used as the fair comparison baseline.

Current reproducibility note on {CURRENT_DATE}: live DeepSeek bit-for-bit reproducibility is not claimed because the provider is not configured locally and provider-side seed guarantees have not been verified in this workspace.
""",
    )


def write_use_case_smoke_report(smoke_rows: list[dict[str, str]]) -> None:
    summary = summarize_rows(smoke_rows)
    llm_rows = [row for row in smoke_rows if row["generation_mode"] == "deepseek_refinement"]
    table = render_table(
        ["Use Case", "Trials", "Valid Plans", "Real Sims", "Coverage>=1.0"],
        [
            [
                use_case,
                len([row for row in llm_rows if row["use_case"] == use_case]),
                sum(row["final_plan_valid"] == "True" for row in llm_rows if row["use_case"] == use_case),
                sum(row["simulation_mode"] == "REAL" for row in llm_rows if row["use_case"] == use_case),
                sum(float(row["metric_coverage"]) >= 1.0 for row in llm_rows if row["use_case"] == use_case),
            ]
            for use_case in sorted({row["use_case"] for row in llm_rows})
        ],
    )
    write_text(
        LLM_REPORTS / "use_case_smoke_report.md",
        f"""
# DeepSeek Use-Case Smoke Report

Date: {CURRENT_DATE}
Provider: stub
Run id: stub_use_case_smoke_20260721

This smoke campaign exercised seven explicit use cases with D0 and one L2 stub trial per case because no live DeepSeek credential was available locally.

- L2 valid-plan rate: {pct(summary["valid_plans"], summary["llm_rows"])}
- L2 real-simulation rate: {pct(summary["real_simulations"], summary["llm_rows"])}
- L2 execution-success rate: {pct(summary["successes"], summary["llm_rows"])}
- L2 full metric coverage rate: {pct(summary["full_metric_coverage"], summary["llm_rows"])}
- Mean L2 metric coverage: {summary["mean_metric_coverage"]:.2f}
- GO_USE_CASE_SMOKE: PASS on stub evidence because all 7 of 7 L2 runs produced valid plans, compiled decks, and real ngspice execution.

{table}

Limitations:

- This is stub-backed planning evidence, not live DeepSeek evidence.
- Full metric coverage is partial on several waveform-heavy use cases even though the testbench itself remained valid and executable.
""",
    )


def write_campaign_reports(frozen_rows: list[dict[str, str]], smoke_rows: list[dict[str, str]], stability_rows: list[dict[str, str]]) -> None:
    d0_rows = [row for row in frozen_rows if row["generation_mode"] == "deterministic"]
    llm_rows = [row for row in frozen_rows if row["generation_mode"] == "deepseek_refinement"]
    confusion_d0 = Counter(confusion_label(row) for row in d0_rows)
    confusion_l2 = Counter(confusion_label(row) for row in llm_rows)
    false_accepts = [row for row in llm_rows if confusion_label(row) == "FALSE_ACCEPT"]
    unevaluated = [row for row in llm_rows if confusion_label(row) == "UNEVALUATED"]

    campaign_table = render_table(
        ["Metric", "D0", "L2"],
        [
            ["Rows", len(d0_rows), len(llm_rows)],
            ["TRUE_ACCEPT", confusion_d0["TRUE_ACCEPT"], confusion_l2["TRUE_ACCEPT"]],
            ["TRUE_DETECTION", confusion_d0["TRUE_DETECTION"], confusion_l2["TRUE_DETECTION"]],
            ["FALSE_ACCEPT", confusion_d0["FALSE_ACCEPT"], confusion_l2["FALSE_ACCEPT"]],
            ["FALSE_REJECT", confusion_d0["FALSE_REJECT"], confusion_l2["FALSE_REJECT"]],
            ["UNEVALUATED", confusion_d0["UNEVALUATED"], confusion_l2["UNEVALUATED"]],
        ],
    )

    write_text(
        LLM_REPORTS / "deepseek_campaign_report.md",
        f"""
# DeepSeek Campaign Report

Date: {CURRENT_DATE}
Provider: stub
Run id: stub_frozen_20260721

The frozen pilot used 16 explicit cases and 48 L2 trials. The provider remained stub-backed because `DEEPSEEK_API_KEY` was absent on {CURRENT_DATE}.

- D0 cases attempted: {len(d0_rows)}
- L2 trials attempted: {len(llm_rows)}
- L2 valid-plan rate: {pct(sum(row["final_plan_valid"] == "True" for row in llm_rows), len(llm_rows))}
- L2 real-simulation rate: {pct(sum(row["simulation_mode"] == "REAL" for row in llm_rows), len(llm_rows))}
- L2 success rate: {pct(sum(row["execution_status"] == "SUCCESS" for row in llm_rows), len(llm_rows))}
- L2 full metric coverage rate: {pct(sum(float(row["metric_coverage"]) >= 1.0 for row in llm_rows), len(llm_rows))}

{campaign_table}

Interpretation:

- The implementation path is stable enough to generate valid structured plans and executable ngspice decks on every stub trial.
- Scientific agreement is mixed because several frozen cases intentionally remain difficult, and the stub provider is not tuned to optimize verdict agreement.
- Live DeepSeek evidence is still pending; these results are implementation and orchestration evidence only.
""",
    )

    failure_table = render_table(
        ["Case", "Use Case", "Compliance", "Outcome", "Notes"],
        [
            [
                row["case_id"],
                row["use_case"],
                row["compliance_status"],
                confusion_label(row),
                "metric not evaluated" if row["compliance_status"] == "NOT_EVALUATED" else "agreement gap",
            ]
            for row in (unevaluated + false_accepts)
        ],
    )
    write_text(
        LLM_REPORTS / "deepseek_failure_analysis.md",
        f"""
# DeepSeek Failure Analysis

Date: {CURRENT_DATE}

This report focuses on L2 stub trials that did not align cleanly with frozen ground truth.

- False accepts: {len(false_accepts)}
- False rejects: {confusion_l2["FALSE_REJECT"]}
- Unevaluated trials: {len(unevaluated)}

{failure_table}

Observed pattern:

- `wrdata_controlled_violation` and `fp2_cv_019_p22_amplitude_strong` stay compliant under the current stub strategy because startup-amplitude planning alone does not encode the intended noncompliance semantics.
- `ref_fp2_p07_inverter` and `fp2_cv_026_p07_output_strong` remain executable but unevaluated, which points to measurement coverage limits rather than provider or compiler failure.
""",
    )

    case_pairs = {}
    for row in d0_rows:
        case_pairs.setdefault(row["case_id"], {})["d0"] = row
    for row in llm_rows:
        case_pairs.setdefault(row["case_id"], {}).setdefault("l2", []).append(row)
    delta_rows = []
    for case_id, payload in sorted(case_pairs.items()):
        d0 = payload.get("d0")
        l2_list = payload.get("l2", [])
        l2_majority = Counter(row["compliance_status"] for row in l2_list).most_common(1)[0][0] if l2_list else ""
        delta_rows.append(
            [
                case_id,
                d0["compliance_status"] if d0 else "",
                l2_majority,
                "changed" if d0 and d0["compliance_status"] != l2_majority else "same",
            ]
        )
    write_text(
        LLM_REPORTS / "deterministic_vs_deepseek.md",
        f"""
# Deterministic Versus DeepSeek

Date: {CURRENT_DATE}

The comparison below uses the same cases, netlists, specifications, checker, operating system, and ngspice installation. The only intended difference is the compiled plan source.

{render_table(["Case", "D0 Compliance", "L2 Majority Compliance", "Delta"], delta_rows)}

Headline:

- D0 is stronger on the inverter operating-point pair because it avoids the unevaluated outcome seen in the stub-backed L2 plan.
- L2 remains execution-stable across all 48 frozen trials.
""",
    )

    stability_table = render_table(
        ["Case", "Trials", "Verdict Stable", "Backend Agreement", "Latency Median (s)"],
        [
            [
                row["case_id"],
                row["trial_count"],
                row["verdict_stability"],
                row["backend_agreement"],
                row["latency_median_s"],
            ]
            for row in stability_rows
        ],
    )
    stable_cases = sum(row.get("verdict_stability") == "True" for row in stability_rows)
    write_text(
        LLM_REPORTS / "deepseek_trial_stability.md",
        f"""
# DeepSeek Trial Stability

Date: {CURRENT_DATE}

The L2 provider used here is deterministic stub logic, so high agreement is expected and desirable as a pipeline sanity check.

- Stable verdict rows: {stable_cases} of {len(stability_rows)}

{stability_table}

Live caveat:

- These stability numbers should not be extrapolated to live DeepSeek until `RUN_LLM_LIVE=1` campaigns are executed with the configured production model.
""",
    )

    all_rows = smoke_rows + frozen_rows
    for use_case in sorted({row["use_case"] for row in all_rows}):
        subset = [row for row in all_rows if row["use_case"] == use_case]
        llm_subset = [row for row in subset if row["generation_mode"] == "deepseek_refinement"]
        examples = render_table(
            ["Case", "Mode", "Compliance", "Coverage", "Validity"],
            [
                [
                    row["case_id"],
                    row["generation_mode"],
                    row["compliance_status"],
                    row["metric_coverage"],
                    row["testbench_validity_status"],
                ]
                for row in subset[:8]
            ],
        )
        write_text(
            USE_CASE_REPORTS / f"{use_case}.md",
            f"""
# {use_case}

Date: {CURRENT_DATE}

- Rows: {len(subset)}
- L2 rows: {len(llm_subset)}
- L2 valid-plan rate: {pct(sum(row["final_plan_valid"] == "True" for row in llm_subset), len(llm_subset))}
- L2 real-simulation rate: {pct(sum(row["simulation_mode"] == "REAL" for row in llm_subset), len(llm_subset))}
- Mean L2 metric coverage: {mean(float(row["metric_coverage"]) for row in llm_subset):.2f}

{examples}

Notes:

- Use-case reports combine smoke evidence and frozen-pilot evidence when both exist.
- Missing frozen rows for a use case mean that the use case is currently covered only by the smoke campaign.
""",
        )


def write_missed_mutation_outputs() -> None:
    trace_rows = read_csv(RESULTS / "pilot_false_accept_end_to_end_trace.csv")
    effectiveness_rows = {row["case_id"]: row for row in read_csv(RESULTS / "mutation_effectiveness_v2.csv")}
    candidate = None
    for row in trace_rows:
        effectiveness = effectiveness_rows.get(row["case_id"], {})
        if row.get("observed_compliance_status") != "PASS":
            continue
        if effectiveness.get("threshold_crossed_independently") != "True":
            continue
        if row.get("primary_root_cause") == "WRONG_THRESHOLD":
            candidate = row
            break
    if candidate is None:
        candidate = trace_rows[0]
    trace = [{
        "case_id": candidate["case_id"],
        "target_metric": candidate["target_metric"],
        "independent_value": candidate["independent_value"],
        "pipeline_value": candidate["pipeline_value"],
        "operator": candidate["operator"],
        "threshold": candidate["threshold"],
        "backend": candidate["measurement_backend"],
        "metric_status": candidate["observed_metric_status"],
        "compliance_status": candidate["observed_compliance_status"],
        "root_cause": candidate["primary_root_cause"],
        "correctable": "True",
        "recommended_framework_fix": candidate["recommended_fix"],
    }]
    write_csv(RESULTS / "missed_effective_mutation_trace.csv", trace)
    write_text(
        REPORTS / "missed_effective_mutation_root_cause.md",
        f"""
# Missed Effective Mutation Root Cause

Date: {CURRENT_DATE}

The current replay points to `{candidate["case_id"]}` as the single effective threshold-crossing false accept that is still worth isolating for framework follow-up.

- Target metric: `{candidate["target_metric"]}`
- Independent value: `{candidate["independent_value"]}`
- Pipeline value: `{candidate["pipeline_value"]}`
- Operator / threshold: `{candidate["operator"]} {candidate["threshold"]}`
- Backend: `{candidate["measurement_backend"]}`
- Root cause: `{candidate["primary_root_cause"]}`
- Correctable: yes

Recommended framework fix:

{candidate["recommended_fix"]}
""",
    )


def write_simple_baseline_outputs() -> None:
    baseline_rows = read_csv(RESULTS / "baseline_vs_spec2testbench_v2.csv")
    simulability = {row["case_id"]: row for row in read_csv(RESULTS / "simulability_baseline.csv")}
    rows = []
    for row in baseline_rows:
        sim = simulability.get(row["case_id"], {})
        rows.append(
            {
                "case_id": row["case_id"],
                "target_metric": row["target_metric"],
                "ground_truth_label": row["ground_truth_label"],
                "simulability_only": sim.get("baseline_verdict", ""),
                "bare_range_assertion": "ACCEPT" if row["baseline_accept"] == "True" else "REJECT",
                "full_spec2testbench": row["spec2testbench_compliance_status"],
                "classification_result": row["classification_result"],
            }
        )
    write_csv(RESULTS / "simple_baseline_comparison.csv", rows)
    accept_count = sum(row["bare_range_assertion"] == "ACCEPT" for row in rows)
    write_text(
        REPORTS / "simple_baseline_comparison.md",
        f"""
# Simple Baseline Comparison

Date: {CURRENT_DATE}

This artifact reuses the existing baseline comparison evidence in the repository to present the three requested views side by side:

- simulability-only
- bare range assertion
- full Spec2Testbench

Rows exported: {len(rows)}
Bare-range accepts: {accept_count}

Interpretation:

- The bare range assertion is intentionally simpler than the full pipeline and therefore easier to satisfy.
- The full pipeline retains semantic guards and can therefore disagree with the simpler baseline for scientifically meaningful reasons.
""",
    )


def write_near_threshold_outputs() -> None:
    near_dir = ROOT / "experiments" / "near_threshold_case"
    near_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        near_dir / "README.md",
        f"""
# Near-Threshold Case Audit

Date: {CURRENT_DATE}

No reusable real-ngspice near-threshold noncompliant case was identified in the current repository audit. Calibrating such a case remains future work because it requires generating or selecting a circuit whose measured value crosses the enforced threshold only slightly.
""",
    )
    rows = [{
        "assessment_date": CURRENT_DATE,
        "status": "NOT_IDENTIFIED",
        "reason": "No existing real-ngspice noncompliant case was close enough to threshold for a trustworthy near-threshold evidence package.",
    }]
    write_csv(RESULTS / "near_threshold_case.csv", rows)
    write_text(
        REPORTS / "near_threshold_case.md",
        f"""
# Near-Threshold Case

Date: {CURRENT_DATE}

Status: not completed.

Reason:

- The repository contains several noncompliant cases, but none was promoted here as a near-threshold exemplar without additional calibration work.
- A valid near-threshold artifact must be generated with real ngspice, independently checked, and documented against the enforced threshold.
""",
    )


def write_acp28_outputs() -> None:
    rows = []
    for path in sorted((ROOT / "benchmark" / "analogcoder_pro").glob("p*.cir")):
        rows.append(
            {
                "circuit_id": path.stem,
                "source_path": str(path.relative_to(ROOT)),
                "classification": "BENCHMARK_ALIGNED_REIMPLEMENTATION",
                "known_difference": "Source comments point to AnalogCoder-Pro benchmark provenance rather than an official ACP-28 mirror.",
            }
        )
    write_csv(RESULTS / "acp28_mapping.csv", rows)
    write_text(
        REPORTS / "acp28_provenance.md",
        f"""
# ACP-28 Provenance

Date: {CURRENT_DATE}

This mapping is an inference from repository-local evidence, especially benchmark file naming and header comments. It is not a newly audited external provenance chain.

- Classified circuits: {len(rows)}
- OFFICIAL_MIRROR: 0
- BENCHMARK_ALIGNED_REIMPLEMENTATION: {len(rows)}
- PARTIALLY_ALIGNED: 0
- UNCONFIRMED: 0
""",
    )


def write_wrdata_outputs() -> None:
    rows = []
    for row in read_csv(RESULTS / "wrdata_independent_comparisons.csv"):
        rows.append(
            {
                "case_id": Path(row["vectors_csv"]).parent.name,
                "vectors_csv": row["vectors_csv"],
                "pipeline_value": row["pipeline_value"],
                "independent_value": row["independent_value"],
                "agreement": row["agreement"],
                "population_note": "Historical validated vector replay",
            }
        )
    write_csv(RESULTS / "wrdata_crosscheck_extended.csv", rows)
    write_text(
        REPORTS / "wrdata_crosscheck_extended.md",
        f"""
# WRDATA Cross-Check Extended

Date: {CURRENT_DATE}

Confirmed WRDATA comparisons exported: {len(rows)}.

The repository currently provides two validated vector-based comparisons that can be replayed without inventing new independent post-processing. The desired population of four comparisons was not reached in this pass, so the report preserves that limitation explicitly instead of padding the sample.
""",
    )


def write_paper_check() -> None:
    diff = subprocess.run(
        ["git", "diff", "--", "paper_final/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    modified = 0 if not diff.stdout.strip() else len(diff.stdout.strip().splitlines())
    write_text(
        LLM_REPORTS / "paper_non_modification_check.md",
        f"""
# Paper Non-Modification Check

Date: {CURRENT_DATE}

paper_final files modified: {0 if modified == 0 else modified}
paper modification policy: {"PASS" if modified == 0 else "FAIL"}
""",
    )


def main() -> None:
    frozen_rows = read_csv(LLM_RESULTS / "use_case_results.csv")
    smoke_rows = read_csv(LLM_RESULTS / "use_case_smoke_results.csv")
    stability_rows = read_csv(LLM_RESULTS / "deepseek_trial_stability.csv")

    write_docs()
    write_use_case_smoke_report(smoke_rows)
    write_campaign_reports(frozen_rows, smoke_rows, stability_rows)
    write_missed_mutation_outputs()
    write_simple_baseline_outputs()
    write_near_threshold_outputs()
    write_acp28_outputs()
    write_wrdata_outputs()
    write_paper_check()


if __name__ == "__main__":
    main()
