from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec2testbench.application.ports.llm_provider import LLMProvider, LLMRequest, LLMResponse
from spec2testbench.application.services.llm_cache import FileLLMCache, LLMCacheKey
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.llm_testbench_plan_validator import LLMTestbenchPlanValidator
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan as PlanModel


P10_SPEC = Path("examples/benchmark_specs/p10_lowpass.yaml")
P10_NETLIST = Path("benchmark/analogcoder_pro/p10_lowpass.cir")


def load_lowpass_spec() -> Specification:
    specification = Specification.from_yaml(P10_SPEC)
    specification.case_id = "test_p10_lowpass"
    specification.parent_circuit_id = "p10_lowpass"
    return specification


def valid_plan_json() -> str:
    return json.dumps(
        {
            "case_id": "test_p10_lowpass",
            "analysis_type": "AC",
            "stimuli": [
                {
                    "source_name": "vin",
                    "target_node": "Vin",
                    "stimulus_type": "AC",
                    "parameters": {"magnitude": 1.0, "dc_value": 2.5},
                }
            ],
            "observed_nodes": ["Vout"],
            "measurements": [
                {
                    "metric_name": "cutoff_frequency_hz",
                    "analysis_type": "AC",
                    "input_node": "Vin",
                    "output_node": "Vout",
                    "expected_unit": "Hz",
                    "backend_preference": "NGSPICE_WRDATA",
                    "measurement_parameters": {},
                }
            ],
            "simulation_parameters": {
                "frequency_start_hz": 1.0,
                "frequency_stop_hz": 1000000000.0,
                "points_per_decade": 20,
            },
            "concise_rationale": "Use an AC sweep and observe the output transfer.",
        }
    )


def test_llm_validator_accepts_valid_json_plan():
    specification = load_lowpass_spec()
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        valid_plan_json(),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.is_valid
    assert result.status.value == "VALID"


def test_llm_validator_rejects_invalid_json():
    specification = load_lowpass_spec()
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        "{not json}",
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "INVALID_JSON"


def test_llm_validator_rejects_unknown_node():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["measurements"][0]["output_node"] = "MadeUpNode"
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "UNKNOWN_NODE"


def test_llm_validator_rejects_missing_and_extra_metric():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["measurements"][0]["metric_name"] = "bandwidth"
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value in {"MISSING_REQUIRED_METRIC", "EXTRA_UNREQUESTED_METRIC"}


def test_llm_validator_rejects_invalid_unit():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["measurements"][0]["expected_unit"] = "V"
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "UNIT_MISMATCH"


def test_llm_validator_rejects_analysis_mismatch():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["measurements"][0]["analysis_type"] = "TRAN"
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "ANALYSIS_MISMATCH"


def test_llm_validator_rejects_backend_mismatch():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["measurements"][0]["backend_preference"] = "NGSPICE_MEASURE"
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "UNSUPPORTED_BACKEND"


def test_llm_validator_rejects_invalid_simulation_range():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["simulation_parameters"]["frequency_stop_hz"] = 0.5
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "SCHEMA_ERROR"


def test_llm_validator_rejects_verdict_leakage():
    specification = load_lowpass_spec()
    payload = json.loads(valid_plan_json())
    payload["concise_rationale"] = "This PASS result should stay compliant."
    validator = LLMTestbenchPlanValidator()
    result = validator.parse_and_validate(
        json.dumps(payload),
        specification=specification,
        netlist_path=P10_NETLIST,
        expected_case_id=specification.case_id,
    )
    assert result.status.value == "VERDICT_LEAKAGE"


def test_testbench_plan_compiler_generates_backend_requests():
    specification = load_lowpass_spec()
    plan = PlanModel.model_validate(json.loads(valid_plan_json()))
    compiled = TestbenchPlanCompiler().compile(plan, specification=specification)
    assert compiled.testbench.metadata["measurement_context"]["input_node"] == "Vin"
    assert compiled.measurement_requests[0]["preferred_backend"] == "NGSPICE_WRDATA"


def test_llm_cache_round_trip(tmp_path):
    cache = FileLLMCache(tmp_path)
    key = LLMCacheKey(
        case_id="case",
        mode="deepseek_refinement",
        trial_id="trial_01",
        provider="deepseek",
        model="deepseek-chat",
        prompt_sha256="a",
        specification_sha256="b",
        netlist_sha256="c",
        capability_registry_sha256="d",
        temperature=0.1,
        max_tokens=128,
    )
    payload = {"ok": True}
    cache.save(key, payload)
    assert cache.load(key) == payload


class SequenceProvider(LLMProvider):
    def __init__(self, responses):
        self._responses = list(responses)

    def list_models(self):
        return ["stub"]

    def generate(self, request: LLMRequest) -> LLMResponse:
        content = self._responses.pop(0)
        return LLMResponse(
            content=content,
            provider="stub",
            model=request.model,
            finish_reason="stop",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            latency_seconds=0.0,
            raw_metadata={"attempts": [{"attempt_number": 1, "http_status": 200, "error_type": None, "retryable": False, "delay_before_retry": 0.0, "final_status": "SUCCESS"}]},
        )


def test_llm_generation_service_repairs_invalid_plan():
    specification = load_lowpass_spec()
    provider = SequenceProvider(
        [
            '{"case_id":"wrong","analysis_type":"AC","stimuli":[],"observed_nodes":["Vout"],"measurements":[],"simulation_parameters":{"frequency_start_hz":1.0,"frequency_stop_hz":1000.0,"points_per_decade":10},"concise_rationale":"bad"}',
            valid_plan_json(),
        ]
    )
    service = LLMGenerationService(provider)
    deterministic_testbench = TestbenchPlanCompiler  # dummy non-None object not used structurally
    from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator as FrameworkGenerator

    deterministic_tb = FrameworkGenerator(use_llm=False).generate(specification, netlist_path=P10_NETLIST)
    outcome = service.generate_plan(
        specification=specification,
        netlist_path=P10_NETLIST,
        deterministic_testbench=deterministic_tb,
        model="stub",
        temperature=0.1,
        max_tokens=128,
        timeout_seconds=30.0,
        include_deterministic_summary=True,
    )
    assert outcome.parsed_plan is not None
    assert len(outcome.repair_history) == 1
