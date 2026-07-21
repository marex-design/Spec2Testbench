from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.llm_capability_builder import LLMCapabilityBuilder
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.llm_testbench_plan_validator import LLMTestbenchPlanValidator
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.config.settings import settings
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.llm_status import GenerationMode, LLMTestbenchValidityStatus
from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator
from spec2testbench.application.usecases.run_verification import VerificationPipeline


GROUND_TRUTH_MANIFEST = ROOT / "experiments/ground_truth/ground_truth_manifest.yaml"
RESULTS_DIR = ROOT / "results/llm_deepseek"
REPORTS_DIR = ROOT / "reports/llm_deepseek"
ARTIFACTS_DIR = ROOT / "artifacts/llm_deepseek"


@dataclass(frozen=True)
class CampaignCase:
    case_id: str
    parent_circuit_id: str
    ground_truth_label: str
    circuit_family: str
    specification_file: Path
    netlist_file: Path
    targeted_metric: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_use_case(metric_name: str) -> str:
    metric_lower = metric_name.lower()
    if metric_lower in {"operating_point"}:
        return "UC_DC_BIAS"
    if metric_lower in {"quiescent_current", "idd", "power"}:
        return "UC_DC_CURRENT_POWER"
    if metric_lower in {"dc_gain", "dc_gain_db"}:
        return "UC_AC_GAIN"
    if metric_lower in {"bandwidth", "cutoff_frequency_hz"}:
        return "UC_FILTER_CUTOFF_BANDWIDTH"
    if metric_lower in {"propagation_delay", "propagation_delay_s", "settling_time", "slew_rate"}:
        return "UC_TRANSIENT_DELAY"
    if metric_lower in {"oscillator_frequency", "frequency_hz", "startup_amplitude"}:
        return "UC_OSCILLATION_FREQUENCY"
    if metric_lower in {"v_t_plus", "v_t_minus", "hysteresis_width"}:
        return "UC_SWITCHING_THRESHOLD_HYSTERESIS"
    return "UC_UNMAPPED"


def resolve_manifest_cases(manifest_path: Path) -> list[CampaignCase]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if payload.get("cases") and isinstance(payload["cases"][0], dict):
        return _load_explicit_cases(payload["cases"])
    if payload.get("references") or payload.get("violations"):
        return _load_frozen_pilot_v2_cases(payload)
    if payload.get("source_manifest") and payload.get("selected_case_ids"):
        source_cases = _load_ground_truth_cases(Path(payload["source_manifest"]))
        selected = set(payload["selected_case_ids"])
        return [case for case in source_cases if case.case_id in selected]
    if payload.get("cases") and isinstance(payload["cases"][0], str):
        source_cases = _load_ground_truth_cases(GROUND_TRUTH_MANIFEST)
        selected = set(payload["cases"])
        return [case for case in source_cases if case.case_id in selected]
    if payload.get("cases") and isinstance(payload["cases"], list):
        return _load_ground_truth_cases(manifest_path)
    return _load_ground_truth_cases(manifest_path)


def _load_explicit_cases(records: list[dict[str, Any]]) -> list[CampaignCase]:
    cases = []
    for record in records:
        cases.append(
            CampaignCase(
                case_id=record["case_id"],
                parent_circuit_id=record.get("parent_circuit_id", record["case_id"]),
                ground_truth_label=record.get("ground_truth_label", ""),
                circuit_family=record.get("circuit_family", ""),
                specification_file=ROOT / record["specification_file"],
                netlist_file=ROOT / record["netlist_file"],
                targeted_metric=(
                    record.get("targeted_metric", {}).get("name", "")
                    if isinstance(record.get("targeted_metric"), dict)
                    else str(record.get("targeted_metric", "") or "")
                ),
            )
        )
    return cases


def _load_ground_truth_cases(path: Path) -> list[CampaignCase]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = []
    for record in payload.get("cases", []):
        spec_file = record.get("specification_file")
        netlist_file = record.get("netlist_file")
        if not spec_file or not netlist_file:
            continue
        cases.append(
            CampaignCase(
                case_id=record["case_id"],
                parent_circuit_id=record.get("parent_circuit_id", record["case_id"]),
                ground_truth_label=record.get("ground_truth_label", ""),
                circuit_family=record.get("circuit_family", ""),
                specification_file=ROOT / spec_file,
                netlist_file=ROOT / netlist_file,
                targeted_metric=record.get("targeted_metric", {}).get("name", ""),
            )
        )
    return cases


def _load_frozen_pilot_v2_cases(payload: dict[str, Any]) -> list[CampaignCase]:
    cases: list[CampaignCase] = []
    for record in payload.get("references", []):
        case_id = record["case_id"]
        parent = case_id.removeprefix("ref_fp2_")
        cases.append(
            CampaignCase(
                case_id=case_id,
                parent_circuit_id=record.get("parent_circuit_id", parent),
                ground_truth_label=record.get("ground_truth_label", ""),
                circuit_family="",
                specification_file=ROOT / f"experiments/frozen_pilot_v2/{case_id}/specification.yaml",
                netlist_file=ROOT / f"benchmark/analogcoder_pro/{parent}.cir",
                targeted_metric=record.get("metric_name", ""),
            )
        )
    for record in payload.get("violations", []):
        case_id = record["case_id"]
        base, severity = case_id.rsplit("_", 1)
        cases.append(
            CampaignCase(
                case_id=case_id,
                parent_circuit_id=record.get("parent_circuit_id", ""),
                ground_truth_label=record.get("ground_truth_label", ""),
                circuit_family="",
                specification_file=ROOT / f"experiments/frozen_pilot_v2/{base}/{severity}/specification.yaml",
                netlist_file=ROOT / f"experiments/frozen_pilot_v2/{base}/{severity}/netlist.cir",
                targeted_metric=record.get("metric_name", ""),
            )
        )
    return cases


def build_provider(args: argparse.Namespace):
    if args.provider == "stub":
        return DeterministicStubProvider()
    if args.provider != "deepseek":
        raise ValueError("Supported providers are: deepseek, stub")
    config = DeepSeekProviderConfig(
        api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com",
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout,
        max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
    )
    return DeepSeekProvider(config)


def load_case_specification(case: CampaignCase) -> Specification:
    specification = Specification.from_yaml(case.specification_file)
    specification.case_id = case.case_id
    specification.parent_circuit_id = case.parent_circuit_id
    if case.targeted_metric and case.targeted_metric in specification.performance_targets:
        specification.performance_targets = {
            case.targeted_metric: specification.performance_targets[case.targeted_metric]
        }
    return specification


def run_deterministic_case(case: CampaignCase, *, timeout: int) -> tuple[Specification, dict[str, Any]]:
    specification = load_case_specification(case)
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=timeout)
    report = pipeline.verify(specification, netlist_path=case.netlist_file, spec_path=case.specification_file)
    return specification, {"report": report}


def run_llm_case(
    case: CampaignCase,
    *,
    provider,
    mode: GenerationMode,
    trial_id: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    specification = load_case_specification(case)
    deterministic_testbench = TestBenchGenerator(use_llm=False).generate(specification, netlist_path=case.netlist_file)
    generation = LLMGenerationService(
        provider,
        capability_builder=LLMCapabilityBuilder(),
        validator=LLMTestbenchPlanValidator(),
    )
    outcome = generation.generate_plan(
        specification=specification,
        netlist_path=case.netlist_file,
        deterministic_testbench=deterministic_testbench,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout,
        include_deterministic_summary=(mode == GenerationMode.DEEPSEEK_REFINEMENT),
    )
    compiler = TestbenchPlanCompiler()
    compiled = compiler.compile(outcome.parsed_plan, specification=specification) if outcome.parsed_plan else None

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=int(timeout))
    simulation_results = None
    report = None
    if compiled is not None:
        pipeline.testbench_gen.generate = lambda specification, netlist_path=None: compiled.testbench
        simulation_results = pipeline._run_simulation_with_ngspice(case.netlist_file, compiled.testbench)
        report = pipeline.verify(
            specification,
            netlist_path=case.netlist_file,
            simulation_results=simulation_results,
            spec_path=case.specification_file,
        )

    return {
        "specification": specification,
        "deterministic_testbench": deterministic_testbench,
        "planning_outcome": outcome,
        "compiled": compiled,
        "simulation_results": simulation_results,
        "report": report,
    }


def artifact_dir(run_id: str, case_id: str, mode: str, trial_id: str) -> Path:
    return ARTIFACTS_DIR / run_id / case_id / mode / trial_id


def write_llm_artifacts(
    *,
    run_id: str,
    case: CampaignCase,
    mode: GenerationMode,
    trial_id: str,
    execution: dict[str, Any],
) -> Path:
    output_dir = artifact_dir(run_id, case.case_id, mode.value, trial_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    specification = execution["specification"]
    outcome = execution["planning_outcome"]
    compiled = execution["compiled"]
    report = execution["report"]
    simulation_results = execution["simulation_results"] or {}

    (output_dir / "request_payload.json").write_text(
        json.dumps(outcome.request_payload, indent=2),
        encoding="utf-8",
    )
    (output_dir / "system_prompt.txt").write_text(outcome.system_prompt, encoding="utf-8")
    (output_dir / "prompt_sha256.txt").write_text(outcome.prompt_sha256, encoding="utf-8")
    (output_dir / "raw_response.txt").write_text(outcome.raw_response, encoding="utf-8")
    if outcome.parsed_plan is not None:
        (output_dir / "parsed_plan.json").write_text(
            json.dumps(outcome.parsed_plan.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
    (output_dir / "plan_validation.json").write_text(
        json.dumps(outcome.validation.to_dict(), indent=2),
        encoding="utf-8",
    )
    (output_dir / "repair_history.json").write_text(
        json.dumps(
            [
                {
                    "repair_status": item.repair_status.value,
                    "prompt": item.prompt,
                    "validation": item.validation,
                }
                for item in outcome.repair_history
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "provider_metadata.json").write_text(
        json.dumps(outcome.provider_metadata, indent=2),
        encoding="utf-8",
    )
    (output_dir / "netlist_sha256.txt").write_text(sha256_file(case.netlist_file), encoding="utf-8")
    (output_dir / "specification_sha256.txt").write_text(
        hashlib.sha256(json.dumps(specification.to_dict(), sort_keys=True).encode("utf-8")).hexdigest(),
        encoding="utf-8",
    )

    if compiled is not None:
        compiler = TestbenchPlanCompiler()
        deck = compiler.compile_to_spice_deck(outcome.parsed_plan, specification=specification, netlist_path=case.netlist_file)
        (output_dir / "compiled_testbench.cir").write_text(deck, encoding="utf-8")
        (output_dir / "testbench_sha256.txt").write_text(
            hashlib.sha256(deck.encode("utf-8")).hexdigest(),
            encoding="utf-8",
        )

    if simulation_results:
        (output_dir / "ngspice_command.json").write_text(
            json.dumps(simulation_results.get("ngspice_command", []), indent=2),
            encoding="utf-8",
        )
        (output_dir / "metrics.json").write_text(
            json.dumps(simulation_results.get("metrics", {}), indent=2),
            encoding="utf-8",
        )
        (output_dir / "compliance.json").write_text(
            json.dumps(
                {
                    "compliance_status": report.compliance_status.value if report else "NOT_EVALUATED",
                    "execution_status": report.execution_status.value if report else "ERROR",
                    "scientific_category": report.scientific_category.value if report else "UNEVALUATED",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (output_dir / "scientific_status.json").write_text(
            json.dumps(report.provenance if report else {}, indent=2),
            encoding="utf-8",
        )
        (output_dir / "provenance.json").write_text(
            json.dumps(report.provenance if report else {}, indent=2),
            encoding="utf-8",
        )
        (output_dir / "ngspice_stdout.txt").write_text(
            "\n".join(simulation_results.get("logs", [])),
            encoding="utf-8",
        )
        (output_dir / "ngspice_stderr.txt").write_text(
            "\n".join(simulation_results.get("errors", [])),
            encoding="utf-8",
        )
        artifacts = simulation_results.get("artifacts", {})
        for source_key, output_name in {
            "measures": "measures.txt",
            "vectors": "vectors.dat",
            "vectors_csv": "vectors.csv",
        }.items():
            source_path = artifacts.get(source_key)
            if source_path and Path(source_path).exists():
                (output_dir / output_name).write_text(Path(source_path).read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    return output_dir


def build_use_case_row(
    *,
    run_id: str,
    case: CampaignCase,
    mode: str,
    trial_id: str,
    provider_name: str,
    model: str,
    planning_outcome,
    report,
) -> dict[str, Any]:
    requested_metric_count = len(planning_outcome.request_payload.get("requested_metrics", []))
    evaluated_metric_count = 0
    compliance_status = "NOT_EVALUATED"
    execution_status = "ERROR"
    simulation_mode = ""
    measurement_backend = ""
    evaluation_outcome = "UNEVALUATED"
    generation_latency = 0.0
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None

    metadata = planning_outcome.provider_metadata or {}
    generation_latency = float(metadata.get("latency_seconds", 0.0) or 0.0)
    prompt_tokens = metadata.get("prompt_tokens")
    completion_tokens = metadata.get("completion_tokens")
    total_tokens = metadata.get("total_tokens")

    if report is not None:
        evaluated_metric_count = sum(1 for result in report.spec_results if result.measured_value is not None)
        compliance_status = report.compliance_status.value
        execution_status = report.execution_status.value
        simulation_mode = report.simulation_mode.value if report.simulation_mode else ""
        measurement_backend = report.measurement_backend or ""
        evaluation_outcome = report.scientific_category.value

    return {
        "run_id": run_id,
        "case_id": case.case_id,
        "use_case": infer_use_case(case.targeted_metric),
        "circuit_family": case.circuit_family or case.parent_circuit_id,
        "ground_truth_label": case.ground_truth_label,
        "generation_mode": mode,
        "trial_id": trial_id,
        "provider": provider_name,
        "model": model,
        "prompt_version": "deepseek_testbench_planner_v1",
        "initial_json_valid": planning_outcome.validation.status.value != "INVALID_JSON",
        "final_plan_valid": planning_outcome.validation.is_valid,
        "repair_count": len(planning_outcome.repair_history),
        "testbench_validity_status": (
            LLMTestbenchValidityStatus.VALID.value
            if report is not None and report.execution_status.value == "SUCCESS"
            else LLMTestbenchValidityStatus.INVALID_PLAN.value
            if not planning_outcome.validation.is_valid
            else LLMTestbenchValidityStatus.SIMULATION_FAILURE.value
        ),
        "execution_status": execution_status,
        "simulation_mode": simulation_mode,
        "measurement_backend": measurement_backend,
        "requested_metric_count": requested_metric_count,
        "evaluated_metric_count": evaluated_metric_count,
        "metric_coverage": (evaluated_metric_count / requested_metric_count) if requested_metric_count else 0.0,
        "compliance_status": compliance_status,
        "evaluation_outcome": evaluation_outcome,
        "generation_latency_s": generation_latency,
        "simulation_latency_s": report.runtime_seconds if report is not None else 0.0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_trial_stability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["generation_mode"] not in {GenerationMode.DEEPSEEK_PLAN.value, GenerationMode.DEEPSEEK_REFINEMENT.value}:
            continue
        grouped.setdefault(row["case_id"], []).append(row)
    summary_rows = []
    for case_id, items in grouped.items():
        compliance_values = {item["compliance_status"] for item in items}
        evaluation_values = {item["evaluation_outcome"] for item in items}
        latency_values = [float(item["simulation_latency_s"]) for item in items]
        summary_rows.append(
            {
                "case_id": case_id,
                "trial_count": len(items),
                "plan_agreement_across_trials": len({item["final_plan_valid"] for item in items}) == 1,
                "analysis_agreement": len({item["use_case"] for item in items}) == 1,
                "backend_agreement": len({item["measurement_backend"] for item in items}) == 1,
                "metric_coverage_variance": statistics.pvariance(float(item["metric_coverage"]) for item in items) if len(items) > 1 else 0.0,
                "verdict_stability": len(compliance_values) == 1 and len(evaluation_values) == 1,
                "latency_median_s": statistics.median(latency_values) if latency_values else 0.0,
                "latency_range_s": (max(latency_values) - min(latency_values)) if len(latency_values) > 1 else 0.0,
            }
        )
    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DeepSeek testbench campaign")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--temperature", required=True, type=float)
    parser.add_argument("--max-tokens", required=True, type=int)
    parser.add_argument("--timeout", required=True, type=float)
    parser.add_argument("--trials", required=True, type=int)
    parser.add_argument("--case-id")
    parser.add_argument("--use-case")
    parser.add_argument("--modes", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force-new-llm-call", action="store_true")
    parser.add_argument("--output-run-id", required=True)
    parser.add_argument("--disable-pyspice", action="store_true")
    parser.add_argument("--no-mock", action="store_true")
    args = parser.parse_args()

    if args.disable_pyspice:
        os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"

    provider = build_provider(args)
    manifest_path = ROOT / args.manifest
    cases = resolve_manifest_cases(manifest_path)
    if args.case_id:
        cases = [case for case in cases if case.case_id == args.case_id]
    if args.use_case:
        cases = [case for case in cases if infer_use_case(case.targeted_metric) == args.use_case]
    modes = [GenerationMode(item.strip()) for item in args.modes.split(",") if item.strip()]

    mapping_rows = [
        {
            "case_id": case.case_id,
            "parent_circuit_id": case.parent_circuit_id,
            "use_case": infer_use_case(case.targeted_metric),
            "targeted_metric": case.targeted_metric,
            "specification_file": str(case.specification_file.relative_to(ROOT)),
            "netlist_file": str(case.netlist_file.relative_to(ROOT)),
        }
        for case in cases
    ]
    write_csv(RESULTS_DIR / "use_case_mapping.csv", mapping_rows)

    if args.dry_run:
        summary = {
            "run_id": args.output_run_id,
            "provider": args.provider,
            "model": args.model,
            "cases": [case.case_id for case in cases],
            "modes": [mode.value for mode in modes],
            "status": "DRY_RUN",
        }
        (RESULTS_DIR / "deepseek_campaign_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    use_case_rows: list[dict[str, Any]] = []
    generation_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    verdict_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []

    for case in cases:
        deterministic_report = None
        if GenerationMode.DETERMINISTIC in modes:
            specification, deterministic = run_deterministic_case(case, timeout=int(args.timeout))
            deterministic_report = deterministic["report"]
            use_case_rows.append(
                {
                    "run_id": args.output_run_id,
                    "case_id": case.case_id,
                    "use_case": infer_use_case(case.targeted_metric),
                    "circuit_family": case.circuit_family or case.parent_circuit_id,
                    "ground_truth_label": case.ground_truth_label,
                    "generation_mode": GenerationMode.DETERMINISTIC.value,
                    "trial_id": "deterministic",
                    "provider": "none",
                    "model": "template",
                    "prompt_version": "",
                    "initial_json_valid": True,
                    "final_plan_valid": True,
                    "repair_count": 0,
                    "testbench_validity_status": "VALID" if deterministic_report.execution_status.value == "SUCCESS" else "SIMULATION_FAILURE",
                    "execution_status": deterministic_report.execution_status.value,
                    "simulation_mode": deterministic_report.simulation_mode.value if deterministic_report.simulation_mode else "",
                    "measurement_backend": deterministic_report.measurement_backend or "",
                    "requested_metric_count": len(specification.performance_targets),
                    "evaluated_metric_count": sum(1 for result in deterministic_report.spec_results if result.measured_value is not None),
                    "metric_coverage": (
                        sum(1 for result in deterministic_report.spec_results if result.measured_value is not None)
                        / len(specification.performance_targets)
                    ) if specification.performance_targets else 0.0,
                    "compliance_status": deterministic_report.compliance_status.value,
                    "evaluation_outcome": deterministic_report.scientific_category.value,
                    "generation_latency_s": 0.0,
                    "simulation_latency_s": deterministic_report.runtime_seconds,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                }
            )

        for mode in modes:
            if mode == GenerationMode.DETERMINISTIC:
                continue
            for trial_index in range(1, args.trials + 1):
                trial_id = f"trial_{trial_index:02d}"
                execution = run_llm_case(
                    case,
                    provider=provider,
                    mode=mode,
                    trial_id=trial_id,
                    model=args.model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                )
                output_dir = write_llm_artifacts(
                    run_id=args.output_run_id,
                    case=case,
                    mode=mode,
                    trial_id=trial_id,
                    execution=execution,
                )
                planning_outcome = execution["planning_outcome"]
                report = execution["report"]
                row = build_use_case_row(
                    run_id=args.output_run_id,
                    case=case,
                    mode=mode.value,
                    trial_id=trial_id,
                    provider_name=args.provider,
                    model=args.model,
                    planning_outcome=planning_outcome,
                    report=report,
                )
                use_case_rows.append(row)
                generation_rows.append(
                    {
                        "run_id": args.output_run_id,
                        "case_id": case.case_id,
                        "generation_mode": mode.value,
                        "trial_id": trial_id,
                        "provider": args.provider,
                        "model": args.model,
                        "prompt_sha256": planning_outcome.prompt_sha256,
                        "initial_json_valid": planning_outcome.validation.status.value != "INVALID_JSON",
                        "final_json_valid": planning_outcome.validation.status.value not in {"INVALID_JSON", "SCHEMA_ERROR"},
                        "initial_plan_valid": planning_outcome.validation.is_valid,
                        "final_plan_valid": planning_outcome.validation.is_valid,
                        "repair_rate": len(planning_outcome.repair_history) > 0,
                        "repair_count": len(planning_outcome.repair_history),
                        "provider_failure": report is None,
                        "artifact_dir": str(output_dir),
                    }
                )
                validation_rows.append(
                    {
                        "run_id": args.output_run_id,
                        "case_id": case.case_id,
                        "generation_mode": mode.value,
                        "trial_id": trial_id,
                        "validation_status": planning_outcome.validation.status.value,
                        "issue_count": len(planning_outcome.validation.issues),
                        "issues": " | ".join(issue.message for issue in planning_outcome.validation.issues),
                    }
                )
                execution_rows.append(
                    {
                        "run_id": args.output_run_id,
                        "case_id": case.case_id,
                        "generation_mode": mode.value,
                        "trial_id": trial_id,
                        "testbench_validity_status": row["testbench_validity_status"],
                        "execution_status": row["execution_status"],
                        "simulation_mode": row["simulation_mode"],
                        "measurement_backend": row["measurement_backend"],
                        "artifact_dir": str(output_dir),
                    }
                )
                coverage_rows.append(
                    {
                        "run_id": args.output_run_id,
                        "case_id": case.case_id,
                        "generation_mode": mode.value,
                        "trial_id": trial_id,
                        "requested_metric_count": row["requested_metric_count"],
                        "evaluated_metric_count": row["evaluated_metric_count"],
                        "metric_coverage": row["metric_coverage"],
                    }
                )
                verdict_rows.append(
                    {
                        "run_id": args.output_run_id,
                        "case_id": case.case_id,
                        "generation_mode": mode.value,
                        "trial_id": trial_id,
                        "ground_truth_label": case.ground_truth_label,
                        "compliance_status": row["compliance_status"],
                        "evaluation_outcome": row["evaluation_outcome"],
                    }
                )
                deterministic_summary = execution["deterministic_testbench"].to_dict()
                llm_plan = planning_outcome.parsed_plan.model_dump(mode="json") if planning_outcome.parsed_plan else {}
                delta_rows.append(
                    {
                        "case_id": case.case_id,
                        "trial_id": trial_id,
                        "analysis_changed": bool(llm_plan.get("analysis_type")) and bool(deterministic_summary.get("analyses")),
                        "stimulus_changed": llm_plan.get("stimuli", []) != deterministic_summary.get("stimuli", []),
                        "simulation_range_changed": llm_plan.get("simulation_parameters", {}) != {},
                        "observed_nodes_changed": set(llm_plan.get("observed_nodes", [])) != {item.get("node") for item in deterministic_summary.get("measurements", []) if item.get("node")},
                        "backend_preference_changed": any(item.get("backend_preference") not in {None, "AUTO"} for item in llm_plan.get("measurements", [])),
                        "measurement_parameters_changed": any(bool(item.get("measurement_parameters")) for item in llm_plan.get("measurements", [])),
                        "semantic_equivalence": planning_outcome.validation.is_valid,
                        "delta_classification": "VALID_REFINEMENT" if planning_outcome.validation.is_valid else "INVALID_REFINEMENT",
                    }
                )

    stability_rows = summarize_trial_stability(use_case_rows)

    write_csv(RESULTS_DIR / "use_case_results.csv", use_case_rows)
    write_csv(RESULTS_DIR / "llm_generation_attempts.csv", generation_rows)
    write_csv(RESULTS_DIR / "llm_plan_validation.csv", validation_rows)
    write_csv(RESULTS_DIR / "llm_testbench_execution.csv", execution_rows)
    write_csv(RESULTS_DIR / "llm_metric_coverage.csv", coverage_rows)
    write_csv(RESULTS_DIR / "llm_verdict_results.csv", verdict_rows)
    write_csv(RESULTS_DIR / "deterministic_vs_deepseek.csv", use_case_rows)
    write_csv(RESULTS_DIR / "plan_deltas.csv", delta_rows)
    write_csv(RESULTS_DIR / "deepseek_trial_stability.csv", stability_rows)

    llm_rows = [row for row in use_case_rows if row["generation_mode"] != GenerationMode.DETERMINISTIC.value]
    summary = {
        "run_id": args.output_run_id,
        "provider": args.provider,
        "model": args.model,
        "cases_attempted": len(cases),
        "rows": len(use_case_rows),
        "valid_plan_rate": (
            sum(1 for row in llm_rows if row["final_plan_valid"])
            / max(1, len(llm_rows))
        ),
        "real_simulation_rate": (
            sum(1 for row in llm_rows if row["simulation_mode"] == "REAL")
            / max(1, len(llm_rows))
        ),
    }
    (RESULTS_DIR / "deepseek_campaign_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
