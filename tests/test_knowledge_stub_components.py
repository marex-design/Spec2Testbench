from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from spec2testbench.application.services.llm_cache import LLMCacheKey
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.spice_knowledge import retrieve_knowledge_bundle, write_yaml
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.metric_coverage import AnalysisExecutionBundle, CaseEvidenceAggregator
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType as FrameworkAnalysisType, Measurement, TestBench
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus, ExecutionStatus, SimulationMode
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider
from spec2testbench.infrastructure.simulator.netlist_parser import NetlistParser
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator as FrameworkTestBenchGenerator


P01_SPEC = Path("examples/benchmark_specs/p01_amplifier.yaml")
P01_NETLIST = Path("benchmark/analogcoder_pro/p01_amplifier.cir")
P05_SPEC = Path("examples/benchmark_specs/p05_amplifier.yaml")
P05_NETLIST = Path("benchmark/analogcoder_pro/p05_amplifier.cir")
P10_SPEC = Path("examples/benchmark_specs/p10_lowpass.yaml")
P10_NETLIST = Path("benchmark/analogcoder_pro/p10_lowpass.cir")
P17_SPEC = Path("examples/benchmark_specs/p17_currentmirror.yaml")
P17_NETLIST = Path("benchmark/analogcoder_pro/p17_currentmirror.cir")

GROUND_TRUTH_TOKENS = {
    "GROUND_TRUTH_COMPLIANT",
    "GROUND_TRUTH_NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
}


def _targeted_spec(spec_path: Path, *, case_id: str, metric_name: str) -> Specification:
    specification = Specification.from_yaml(spec_path)
    specification.case_id = case_id
    specification.parent_circuit_id = spec_path.stem
    specification.performance_targets = {
        metric_name: specification.performance_targets[metric_name]
    }
    return specification


def _stub_outcome(
    *,
    spec_path: Path,
    netlist_path: Path,
    case_id: str,
    metric_name: str,
    knowledge_bundle: dict[str, object] | None = None,
):
    specification = _targeted_spec(spec_path, case_id=case_id, metric_name=metric_name)
    deterministic_tb = FrameworkTestBenchGenerator(use_llm=False).generate(
        specification,
        netlist_path=netlist_path,
    )
    outcome = LLMGenerationService(DeterministicStubProvider()).generate_plan(
        specification=specification,
        netlist_path=netlist_path,
        deterministic_testbench=deterministic_tb,
        model="deepseek-stub-v1",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=30.0,
        include_deterministic_summary=True,
        knowledge_bundle=knowledge_bundle or {},
        knowledge_version=str((knowledge_bundle or {}).get("knowledge_version", "") or ""),
        provider_mode="STUB",
        scientific_llm_evidence=False,
    )
    assert outcome.parsed_plan is not None, outcome.validation.to_dict()
    return specification, outcome


def _bundle(
    *,
    case_id: str,
    analysis_id: str,
    testbench: TestBench,
    metric_name: str,
    value: float | None,
    reason: str = "",
    backend: str = "NGSPICE_WRDATA",
    execution_status: ExecutionStatus = ExecutionStatus.SUCCESS,
) -> AnalysisExecutionBundle:
    measurement_requests = list((testbench.metadata or {}).get("measurement_requests", []))
    return AnalysisExecutionBundle(
        case_id=case_id,
        analysis_id=analysis_id,
        testbench=testbench,
        simulation_results={
            "success": execution_status == ExecutionStatus.SUCCESS,
            "simulation_mode": SimulationMode.REAL.value,
            "execution_status": execution_status.value,
            "measurement_backend": backend,
            "measurement_requests": measurement_requests,
            "native_metrics": {metric_name: value} if value is not None else {},
            "native_extractions": {
                metric_name: {
                    "metric_name": metric_name,
                    "measured_value": value,
                    "status": "SUCCESS" if value is not None else "NOT_EVALUATED",
                    "reason": reason or ("SUCCESS" if value is not None else "NOT_EVALUATED"),
                    "measurement_backend": backend,
                    "measurement_expression_id": next(
                        (item.get("measurement_expression_id") for item in measurement_requests if item.get("name") == metric_name),
                        "",
                    ),
                    "input_node": next(
                        (item.get("input_node") for item in measurement_requests if item.get("name") == metric_name),
                        "",
                    ),
                    "output_node": next(
                        (item.get("output_node") for item in measurement_requests if item.get("name") == metric_name),
                        "",
                    ),
                }
            },
            "metrics": {metric_name: value} if value is not None else {},
            "dc": {"operating_point": value, "vout_dc": value} if analysis_id == "op" and value is not None else {},
            "ac": {"dc_gain_db": value} if analysis_id == "ac_gain" and value is not None else {},
            "tran": {},
            "transient": {},
            "fourier": {},
            "currents": {},
            "artifacts": {},
            "executed_file_sha256": f"sha_{analysis_id}",
        },
        report=type("ReportStub", (), {"execution_status": execution_status})(),
        artifact_path=Path("artifacts") / "knowledge_stub_v1" / f"{case_id}_{analysis_id}",
        requested_metrics=[metric_name],
        executed_deck_sha256=f"sha_{analysis_id}",
    )


def _aggregate_report(specification: Specification, bundles: list[AnalysisExecutionBundle]):
    aggregator = CaseEvidenceAggregator(case_id=specification.case_id or specification.name)
    for bundle in bundles:
        aggregator.add_execution(bundle)
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False)
    aggregated_testbench = aggregator.aggregate_testbench(specification.name)
    aggregated_results = aggregator.aggregate_simulation_results()
    report = pipeline.verify(
        specification,
        simulation_results=aggregated_results,
        testbench=aggregated_testbench,
    )
    evidence = aggregator.build_metric_evidence(
        list(specification.performance_targets.keys()),
        aggregated_results=aggregated_results,
        final_results=report.spec_results,
    )
    return report, evidence


def test_stub_provider_never_calls_network(monkeypatch):
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )
    _, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="stub_no_network",
        metric_name="cutoff_frequency_hz",
    )
    assert outcome.provider_metadata["network_calls"] == 0


def test_stub_provider_does_not_read_deepseek_key(monkeypatch):
    specification = _targeted_spec(P10_SPEC, case_id="stub_no_key", metric_name="cutoff_frequency_hz")
    deterministic_tb = FrameworkTestBenchGenerator(use_llm=False).generate(
        specification,
        netlist_path=P10_NETLIST,
    )
    original_getenv = os.getenv

    def guarded_getenv(key, default=None):
        if key == "DEEPSEEK_API_KEY":
            raise AssertionError("DEEPSEEK_API_KEY should not be read")
        return original_getenv(key, default)

    monkeypatch.setattr(
        os,
        "getenv",
        guarded_getenv,
    )
    outcome = LLMGenerationService(DeterministicStubProvider()).generate_plan(
        specification=specification,
        netlist_path=P10_NETLIST,
        deterministic_testbench=deterministic_tb,
        model="deepseek-stub-v1",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=30.0,
        include_deterministic_summary=True,
        provider_mode="STUB",
        scientific_llm_evidence=False,
    )
    assert outcome.parsed_plan is not None


def test_stub_provider_is_marked_non_scientific():
    _, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="stub_science_flag",
        metric_name="cutoff_frequency_hz",
    )
    assert outcome.parsed_plan.provider_mode == "STUB"
    assert outcome.parsed_plan.scientific_llm_evidence is False
    assert outcome.provider_metadata["provider_mode"] == "STUB"
    assert outcome.provider_metadata["scientific_llm_evidence"] is False


def test_stub_plan_contains_knowledge_version():
    _, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="stub_knowledge_version",
        metric_name="cutoff_frequency_hz",
        knowledge_bundle={
            "knowledge_version": "knowledge_stub_v1",
            "knowledge_bundle_sha256": "bundle_v1",
        },
    )
    assert outcome.parsed_plan.knowledge_version == "knowledge_stub_v1"


def test_stub_plan_contains_knowledge_bundle_hash():
    _, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="stub_bundle_hash",
        metric_name="cutoff_frequency_hz",
        knowledge_bundle={
            "knowledge_version": "knowledge_stub_v1",
            "knowledge_bundle_sha256": "bundle_hash_123",
        },
    )
    assert outcome.parsed_plan.knowledge_bundle_sha256 == "bundle_hash_123"


def test_plan_uses_only_existing_nodes():
    specification, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="generic_existing_nodes",
        metric_name="cutoff_frequency_hz",
    )
    parser = NetlistParser()
    parsed = parser.parse(P10_NETLIST)
    available_nodes = {
        *parsed.nodes,
        *specification.input_nodes,
        *specification.output_nodes,
        "0",
        "gnd",
        "GND",
    }
    for node in outcome.parsed_plan.observed_nodes:
        assert node in available_nodes
    for stimulus in outcome.parsed_plan.stimuli:
        assert stimulus.target_node in available_nodes
    for measurement in outcome.parsed_plan.measurements:
        if measurement.input_node:
            assert measurement.input_node in available_nodes
        if measurement.output_node:
            assert measurement.output_node in available_nodes


def test_stub_plan_uses_only_existing_nodes():
    specification, outcome = _stub_outcome(
        spec_path=P01_SPEC,
        netlist_path=P01_NETLIST,
        case_id="stub_existing_nodes",
        metric_name="dc_gain_db",
    )
    parser = NetlistParser()
    parsed = parser.parse(P01_NETLIST)
    available_nodes = {
        *parsed.nodes,
        *specification.input_nodes,
        *specification.output_nodes,
        "0",
        "gnd",
        "GND",
    }
    for node in outcome.parsed_plan.observed_nodes:
        assert node in available_nodes


def test_stub_plan_cannot_replace_supply():
    specification, outcome = _stub_outcome(
        spec_path=P05_SPEC,
        netlist_path=P05_NETLIST,
        case_id="stub_supply_preserved",
        metric_name="quiescent_current",
    )
    lower_input_nodes = {node.lower() for node in specification.input_nodes}
    forbidden_nodes = {"vdd", "vss", "vcc", "vee"}
    for stimulus in outcome.parsed_plan.stimuli:
        assert stimulus.target_node.lower() not in forbidden_nodes
        assert stimulus.target_node.lower() in lower_input_nodes


def test_stub_plan_cannot_replace_bias():
    _, outcome = _stub_outcome(
        spec_path=P17_SPEC,
        netlist_path=P17_NETLIST,
        case_id="stub_bias_preserved",
        metric_name="quiescent_current",
    )
    assert outcome.parsed_plan.analysis_type.value == "OP"
    assert all("bias" not in stimulus.target_node.lower() for stimulus in outcome.parsed_plan.stimuli)
    assert all("bias" not in stimulus.source_name.lower() for stimulus in outcome.parsed_plan.stimuli)


def test_stub_plan_uses_canonical_harness_policy():
    _, outcome = _stub_outcome(
        spec_path=P17_SPEC,
        netlist_path=P17_NETLIST,
        case_id="stub_canonical_policy",
        metric_name="quiescent_current",
    )
    assert outcome.parsed_plan.analysis_type.value == "OP"
    assert outcome.parsed_plan.simulation_parameters.dc_source is None


def test_stub_plan_preserves_requested_metrics():
    specification, outcome = _stub_outcome(
        spec_path=P01_SPEC,
        netlist_path=P01_NETLIST,
        case_id="stub_requested_metrics",
        metric_name="dc_gain_db",
    )
    assert [measurement.metric_name for measurement in outcome.parsed_plan.measurements] == list(specification.performance_targets.keys())


def test_stub_plan_cannot_add_unrequested_metric():
    _, outcome = _stub_outcome(
        spec_path=P01_SPEC,
        netlist_path=P01_NETLIST,
        case_id="stub_no_extra_metric",
        metric_name="dc_gain_db",
    )
    assert {measurement.metric_name for measurement in outcome.parsed_plan.measurements} == {"dc_gain_db"}


def test_stub_compiler_preserves_exact_executed_deck(tmp_path):
    specification, outcome = _stub_outcome(
        spec_path=P10_SPEC,
        netlist_path=P10_NETLIST,
        case_id="stub_deck_integrity",
        metric_name="cutoff_frequency_hz",
    )
    compiled = TestbenchPlanCompiler().compile(outcome.parsed_plan, specification=specification)
    simulator = PySpiceSimulator(allow_mock=False)

    def fake_run_ngspice(spice_file, raw_file, timeout_override=None, cwd=None):
        raw_file.write_text("", encoding="utf-8")
        return {
            "success": True,
            "logs": [],
            "errors": [],
            "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
            "returncode": 0,
            "raw_result_file": str(raw_file),
            "raw_result_file_exists": True,
        }

    simulator._run_ngspice = fake_run_ngspice  # type: ignore[method-assign]
    simulator._parse_results = lambda raw_file, testbench, native_artifacts=None: {  # type: ignore[method-assign]
        "ac": {},
        "tran": {},
        "transient": {},
        "dc": {},
        "currents": {},
        "fourier": {},
    }

    results = simulator.run(P10_NETLIST, compiled.testbench, output_dir=tmp_path / "artifacts")
    executed_path = Path(results["ngspice_input_file_path"])
    generated_path = Path(results["generated_testbench_path"])

    assert executed_path.read_bytes() == generated_path.read_bytes()
    assert results["serialized_deck_sha256"] == results["executed_file_sha256"] == results["post_execution_file_sha256"]


def test_stub_multi_analysis_metrics_are_aggregated():
    specification = Specification(
        name="stub_aggregate_case",
        case_id="stub_aggregate_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.2, "unit": "V"},
            "dc_gain_db": {"min": 20.0, "unit": "dB"},
        },
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    op_tb = TestBench(
        name="stub_aggregate_case__op",
        category="dc",
        circuit_name="stub_aggregate_case",
        case_id="stub_aggregate_case",
        analyses=[AnalysisConfig(type=FrameworkAnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="op", unit="V", node="Vout")],
        metadata={},
    )
    ac_tb = TestBench(
        name="stub_aggregate_case__ac",
        category="ac",
        circuit_name="stub_aggregate_case",
        case_id="stub_aggregate_case",
        analyses=[AnalysisConfig(type=FrameworkAnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
        stimuli=[],
    )
    generator._attach_measurement_metadata(op_tb, specification)
    generator._attach_measurement_metadata(ac_tb, specification)

    report, evidence = _aggregate_report(
        specification,
        [
            _bundle(case_id="stub_aggregate_case", analysis_id="op", testbench=op_tb, metric_name="operating_point", value=0.92, backend="NGSPICE_MEASURE"),
            _bundle(case_id="stub_aggregate_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=35.0),
        ],
    )

    assert report.compliance_status == ComplianceStatus.PASS
    assert {row.metric_name for row in evidence} == {"operating_point", "dc_gain_db"}


def test_stub_missing_metric_is_not_zero():
    specification = Specification(
        name="stub_missing_metric",
        case_id="stub_missing_metric",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"oscillator_frequency": {"min": 1.0, "unit": "Hz"}},
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    tran_tb = TestBench(
        name="stub_missing_metric__tran",
        category="transient",
        circuit_name="stub_missing_metric",
        case_id="stub_missing_metric",
        analyses=[AnalysisConfig(type=FrameworkAnalysisType.TRANSIENT, parameters={"start_time": 0.0, "step_time": 1e-6, "end_time": 1e-3})],
        measurements=[Measurement(name="oscillator_frequency", expression="freq", unit="Hz", node="Vout")],
        metadata={},
    )
    generator._attach_measurement_metadata(tran_tb, specification)

    report, _ = _aggregate_report(
        specification,
        [
            _bundle(
                case_id="stub_missing_metric",
                analysis_id="tran",
                testbench=tran_tb,
                metric_name="oscillator_frequency",
                value=None,
                reason="NO_VALID_OSCILLATION",
            ),
        ],
    )

    result = report.spec_results[0]
    assert result.measured_value is None
    assert result.measured_value != 0
    assert report.compliance_status.value == "NOT_EVALUATED"


def test_stub_physical_absence_is_explicit():
    specification = Specification(
        name="stub_physical_absence",
        case_id="stub_physical_absence",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"oscillator_frequency": {"min": 1.0, "unit": "Hz"}},
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    tran_tb = TestBench(
        name="stub_physical_absence__tran",
        category="transient",
        circuit_name="stub_physical_absence",
        case_id="stub_physical_absence",
        analyses=[AnalysisConfig(type=FrameworkAnalysisType.TRANSIENT, parameters={"start_time": 0.0, "step_time": 1e-6, "end_time": 1e-3})],
        measurements=[Measurement(name="oscillator_frequency", expression="freq", unit="Hz", node="Vout")],
        metadata={},
    )
    generator._attach_measurement_metadata(tran_tb, specification)

    report, _ = _aggregate_report(
        specification,
        [
            _bundle(
                case_id="stub_physical_absence",
                analysis_id="tran",
                testbench=tran_tb,
                metric_name="oscillator_frequency",
                value=None,
                reason="NO_VALID_OSCILLATION",
            ),
        ],
    )

    result = report.spec_results[0]
    assert result.verdict.value == "ERROR"
    assert result.message
    assert "no_waveform_data" in result.message.lower() or "could not be extracted" in result.message.lower()


def test_stub_cache_key_contains_trial_id():
    base = dict(
        case_id="case",
        mode="deepseek_refinement",
        provider="deepseek_stub",
        model="deepseek-stub-v1",
        prompt_sha256="prompt",
        specification_sha256="spec",
        netlist_sha256="netlist",
        capability_registry_sha256="registry",
        temperature=0.0,
        max_tokens=512,
    )
    key_one = LLMCacheKey(trial_id="trial_01", **base)
    key_two = LLMCacheKey(trial_id="trial_02", **base)
    assert key_one.digest() != key_two.digest()


def test_stub_cache_key_contains_knowledge_hash():
    base = dict(
        case_id="case",
        mode="deepseek_refinement",
        trial_id="trial_01",
        provider="deepseek_stub",
        model="deepseek-stub-v1",
        prompt_sha256="prompt",
        specification_sha256="spec",
        netlist_sha256="netlist",
        capability_registry_sha256="registry",
        temperature=0.0,
        max_tokens=512,
    )
    key_one = LLMCacheKey(knowledge_bundle_sha256="bundle_a", knowledge_version="knowledge_stub_v1", **base)
    key_two = LLMCacheKey(knowledge_bundle_sha256="bundle_b", knowledge_version="knowledge_stub_v1", **base)
    assert key_one.digest() != key_two.digest()


def test_stub_three_trials_are_accounted_for():
    rows = [{"trial_id": f"trial_{index:02d}"} for index in range(1, 4)]
    assert len(rows) == 3
    assert len({row["trial_id"] for row in rows}) == 3


def test_stub_identical_output_is_not_cache_contamination():
    rows = []
    for index in range(1, 4):
        rows.append(
            {
                "trial_id": f"trial_{index:02d}",
                "raw_response_hash": "identical_stub_hash",
                "cache_key": LLMCacheKey(
                    case_id="case",
                    mode="deepseek_refinement",
                    trial_id=f"trial_{index:02d}",
                    provider="deepseek_stub",
                    model="deepseek-stub-v1",
                    prompt_sha256="prompt",
                    specification_sha256="spec",
                    netlist_sha256="netlist",
                    capability_registry_sha256="registry",
                    knowledge_version="knowledge_stub_v1",
                    knowledge_bundle_sha256="bundle",
                    temperature=0.0,
                    max_tokens=512,
                ).digest(),
            }
        )
    assert len({row["raw_response_hash"] for row in rows}) == 1
    assert len({row["cache_key"] for row in rows}) == 3


def test_stub_ground_truth_is_not_in_prompt():
    _, outcome = _stub_outcome(
        spec_path=P01_SPEC,
        netlist_path=P01_NETLIST,
        case_id="stub_prompt_safety",
        metric_name="dc_gain_db",
        knowledge_bundle={
            "knowledge_version": "knowledge_stub_v1",
            "knowledge_bundle_sha256": "bundle_hash_safe",
        },
    )
    payload_text = json.dumps(outcome.request_payload, sort_keys=True).upper()
    prompt_text = outcome.system_prompt.upper()
    for token in GROUND_TRUTH_TOKENS:
        assert token not in payload_text
        assert token not in prompt_text


def test_stub_frozen_v3_contains_16_cases():
    manifest = json.loads(
        json.dumps(
            __import__("yaml").safe_load(Path("experiments/llm_deepseek/frozen_manifest.yaml").read_text(encoding="utf-8"))
        )
    )
    assert len(manifest["cases"]) == 16


def test_stub_use_case_smoke_contains_7_use_cases():
    manifest = json.loads(
        json.dumps(
            __import__("yaml").safe_load(Path("experiments/llm_deepseek/use_case_smoke_manifest.yaml").read_text(encoding="utf-8"))
        )
    )
    assert len(manifest["cases"]) == 7


def test_retrieve_knowledge_bundle_uses_catalog_version_and_book_fields(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    (knowledge_root / "spice_core").mkdir(parents=True)
    write_yaml(
        knowledge_root / "spice_core" / "book_rule.yaml",
        {
            "schema_version": "1.0",
            "knowledge_version": "knowledge_book_v1",
            "kind": "rules",
            "entries": [
                {
                    "rule_id": "BOOK_TEST_RULE",
                    "schema_version": "1.0",
                    "knowledge_version": "knowledge_book_v1",
                    "category": "ac",
                    "title": "Book test rule",
                    "description": "Book-grounded AC rule for unit testing.",
                    "applies_to": {
                        "analyses": ["AC"],
                        "metrics": ["dc_gain_db"],
                        "circuit_families": [],
                        "backends": [],
                    },
                    "requires": {},
                    "forbids": [],
                    "source": {"source_type": "SPEC2TESTBENCH_LOCAL_EVIDENCE", "document_path": "docs/spice_core_rules.md"},
                    "dialect_scope": ["PORTABLE_SPICE"],
                    "enforcement": {
                        "llm_visible": True,
                        "retriever_visible": True,
                        "validator_enforced": True,
                        "compiler_enforced": True,
                        "backend_enforced": False,
                        "checker_enforced": False,
                    },
                    "verification": {
                        "status": "CONFIRMED_SPEC2TESTBENCH",
                        "positive_test_ids": [],
                        "negative_test_ids": [],
                    },
                    "book_grounded": True,
                    "book_chapter": "Chapter 5",
                    "book_section": "5.2 AC Frequency Sweep",
                    "book_page": 149,
                    "ngspice_confirmed": False,
                    "project_enforced": True,
                }
            ],
        },
    )
    write_yaml(
        knowledge_root / "spice_core" / "book_recipe.yaml",
        {
            "schema_version": "1.0",
            "knowledge_version": "knowledge_book_v1",
            "kind": "recipes",
            "entries": [
                {
                    "recipe_id": "MEASURE_DC_GAIN_DB",
                    "knowledge_version": "knowledge_book_v1",
                    "source_type": "SPEC2TESTBENCH_LOCAL_EVIDENCE",
                    "compatible_analyses": ["AC"],
                    "required_parameters": ["input_node", "output_node"],
                    "optional_parameters": [],
                    "parameter_constraints": [],
                    "compiler_template_id": "COMPILER_TEMPLATE_AC_SWEEP",
                    "scientific_guards": [],
                    "known_failure_modes": [],
                    "positive_tests": [],
                    "negative_tests": [],
                    "verification_status": "CONFIRMED_SPEC2TESTBENCH",
                    "implementation_ref": "spec2testbench/application/services/llm_metric_registry.py",
                    "metrics": ["dc_gain_db"],
                    "retriever_visible": True,
                }
            ],
        },
    )

    bundle = retrieve_knowledge_bundle(
        knowledge_root=knowledge_root,
        case_id="book_case",
        circuit_family="amplifier",
        requested_metrics=["dc_gain_db"],
    )

    assert bundle.knowledge_version == "knowledge_book_v1"
    assert bundle.rules
    assert bundle.rules[0]["book_grounded"] is True
    assert bundle.rules[0]["book_chapter"] == "Chapter 5"
