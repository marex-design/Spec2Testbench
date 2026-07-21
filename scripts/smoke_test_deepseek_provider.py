from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.llm_status import GenerationMode
from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator


CASE_SPEC = ROOT / "examples/benchmark_specs/p10_lowpass.yaml"
CASE_NETLIST = ROOT / "benchmark/analogcoder_pro/p10_lowpass.cir"
REPORT_PATH = ROOT / "reports/llm_deepseek/deepseek_provider_smoke_test.md"


def build_provider(name: str, model: str, temperature: float, max_tokens: int, timeout: float):
    if name == "stub":
        return DeterministicStubProvider()
    if name != "deepseek":
        raise ValueError("Supported smoke providers are: deepseek, stub")
    config = DeepSeekProviderConfig.from_env()
    config = DeepSeekProviderConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout,
        max_retries=config.max_retries,
    )
    return DeepSeekProvider(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the DeepSeek testbench planner")
    parser.add_argument("--provider", default="stub", choices=["deepseek", "stub"])
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--mode", default=GenerationMode.DEEPSEEK_REFINEMENT.value)
    args = parser.parse_args()

    specification = Specification.from_yaml(CASE_SPEC)
    specification.case_id = "smoke_p10_lowpass"
    specification.parent_circuit_id = "p10_lowpass"
    deterministic_testbench = TestBenchGenerator(use_llm=False).generate(specification, netlist_path=CASE_NETLIST)

    provider = build_provider(args.provider, args.model, args.temperature, args.max_tokens, args.timeout)
    generation = LLMGenerationService(provider)
    outcome = generation.generate_plan(
        specification=specification,
        netlist_path=CASE_NETLIST,
        deterministic_testbench=deterministic_testbench,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout,
        include_deterministic_summary=(args.mode == GenerationMode.DEEPSEEK_REFINEMENT.value),
    )

    compiler = TestbenchPlanCompiler()
    compiled = compiler.compile(outcome.parsed_plan, specification=specification) if outcome.parsed_plan else None
    report = None
    if compiled is not None:
        pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=int(args.timeout))
        pipeline.testbench_gen.generate = lambda specification, netlist_path=None: compiled.testbench
        simulation_results = pipeline._run_simulation_with_ngspice(CASE_NETLIST, compiled.testbench)
        report = pipeline.verify(
            specification,
            netlist_path=CASE_NETLIST,
            simulation_results=simulation_results,
            spec_path=CASE_SPEC,
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "\n".join(
            [
                "# DeepSeek Provider Smoke Test",
                "",
                f"- Date: 2026-07-21",
                f"- Provider: {args.provider}",
                f"- Model: {args.model}",
                f"- Case: {specification.case_id}",
                f"- Plan validation: {outcome.validation.status.value}",
                f"- Repairs attempted: {len(outcome.repair_history)}",
                f"- Compiled testbench: {'yes' if compiled is not None else 'no'}",
                f"- Real ngspice execution: {'yes' if report and report.simulation_mode and report.simulation_mode.value == 'REAL' else 'no'}",
                f"- Execution status: {report.execution_status.value if report else 'ERROR'}",
                f"- Measurement backend: {report.measurement_backend if report else ''}",
                f"- Compliance status: {report.compliance_status.value if report else 'NOT_EVALUATED'}",
                "",
                "## Parsed Plan",
                "```json",
                json.dumps(outcome.parsed_plan.model_dump(mode='json') if outcome.parsed_plan else {}, indent=2),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
