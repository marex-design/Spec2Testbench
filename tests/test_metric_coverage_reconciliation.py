from __future__ import annotations

import math
import os
from copy import deepcopy
from pathlib import Path

import pytest

from spec2testbench.application.services.canonical_harness import build_case_analysis_testbenches
from spec2testbench.application.services.canonical_reconciliation import summarize_nominal_rows
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.metric_coverage import (
    AnalysisExecutionBundle,
    CaseEvidenceAggregator,
    analysis_id_for_metric,
)
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, TestBench
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.value_objects.scientific_status import ComplianceStatus, ExecutionStatus, SimulationMode
from spec2testbench.domain.value_objects.verdict import CheckResult, Verdict
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.simulator.result_backends import compute_dc_gain_db, parse_measure_file, parse_wrdata_file
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator as FrameworkTestBenchGenerator
from spec2testbench.application.services.llm_metric_registry import METRIC_DEFINITIONS


ROOT = Path(__file__).resolve().parents[1]


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
    artifact_name: str | None = None,
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
                    "input_node": next((item.get("input_node") for item in measurement_requests if item.get("name") == metric_name), ""),
                    "output_node": next((item.get("output_node") for item in measurement_requests if item.get("name") == metric_name), ""),
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
        artifact_path=ROOT / "artifacts" / "metric_coverage_reconciliation_v1" / (artifact_name or f"{case_id}_{analysis_id}"),
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
    return aggregator, aggregated_results, report, evidence


def test_all_requested_metrics_map_to_analysis():
    unmapped = [name for name in METRIC_DEFINITIONS if analysis_id_for_metric(name) == "unknown"]
    assert unmapped == []


def test_all_supported_metrics_have_measurement_recipe():
    missing = [name for name, definition in METRIC_DEFINITIONS.items() if not definition.measurement_expression_id]
    assert missing == []


def test_analysis_specific_results_are_aggregated():
    specification = Specification(
        name="aggregate_case",
        case_id="aggregate_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.2, "unit": "V"},
            "dc_gain_db": {"min": 20.0, "unit": "dB"},
        },
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    op_tb = TestBench(
        name="aggregate_case__op",
        category="dc",
        circuit_name="aggregate_case",
        case_id="aggregate_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="op", unit="V", node="Vout")],
        metadata={},
    )
    ac_tb = TestBench(
        name="aggregate_case__ac",
        category="ac",
        circuit_name="aggregate_case",
        case_id="aggregate_case",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
        stimuli=[],
    )
    generator._attach_measurement_metadata(op_tb, specification)
    generator._attach_measurement_metadata(ac_tb, specification)

    aggregator, aggregated_results, report, evidence = _aggregate_report(
        specification,
        [
            _bundle(case_id="aggregate_case", analysis_id="op", testbench=op_tb, metric_name="operating_point", value=0.92, backend="NGSPICE_MEASURE"),
            _bundle(case_id="aggregate_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=35.0),
        ],
    )

    assert aggregated_results["native_metrics"]["operating_point"] == pytest.approx(0.92)
    assert aggregated_results["native_metrics"]["dc_gain_db"] == pytest.approx(35.0)
    assert report.compliance_status == ComplianceStatus.PASS
    assert {row.metric_name for row in evidence} == {"operating_point", "dc_gain_db"}


def test_multiple_analysis_decks_share_case_id():
    specification = Specification(
        name="multi_case",
        case_id="multi_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"operating_point": {"min": 0.8, "max": 1.2, "unit": "V"}},
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    op_tb = TestBench(
        name="multi_case__op",
        category="dc",
        circuit_name="multi_case",
        case_id="multi_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="op", unit="V", node="Vout")],
        metadata={},
    )
    generator._attach_measurement_metadata(op_tb, specification)
    bundle = _bundle(case_id="multi_case", analysis_id="op", testbench=op_tb, metric_name="operating_point", value=0.9)
    aggregator = CaseEvidenceAggregator(case_id="multi_case")
    aggregator.add_execution(bundle)

    aggregated_testbench = aggregator.aggregate_testbench(specification.name)

    assert aggregated_testbench.case_id == "multi_case"
    assert all(item["case_id"] == "multi_case" for item in aggregated_testbench.metadata["analysis_execution_bundles"])


def test_checker_receives_aggregated_metric_bundle():
    specification = Specification(
        name="bundle_case",
        case_id="bundle_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.2, "unit": "V"},
            "dc_gain_db": {"min": 20.0, "unit": "dB"},
        },
    )
    generator = FrameworkTestBenchGenerator(use_llm=False)
    op_tb = TestBench(
        name="bundle_case__op",
        category="dc",
        circuit_name="bundle_case",
        case_id="bundle_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="op", unit="V", node="Vout")],
        metadata={},
    )
    ac_tb = TestBench(
        name="bundle_case__ac",
        category="ac",
        circuit_name="bundle_case",
        case_id="bundle_case",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
    )
    generator._attach_measurement_metadata(op_tb, specification)
    generator._attach_measurement_metadata(ac_tb, specification)

    _, aggregated_results, report, _ = _aggregate_report(
        specification,
        [
            _bundle(case_id="bundle_case", analysis_id="op", testbench=op_tb, metric_name="operating_point", value=0.95, backend="NGSPICE_MEASURE"),
            _bundle(case_id="bundle_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=40.0),
        ],
    )

    assert len(report.spec_results) == 2
    assert all(result.verdict == Verdict.PASS for result in report.spec_results)
    assert {request["name"] for request in aggregated_results["measurement_requests"]} == {"operating_point", "dc_gain_db"}
    assert all(report.required_metric_validation[name]["required_analysis_generated"] for name in report.required_metric_validation)


def test_missing_analysis_deck_is_reported():
    specification = Specification(
        name="missing_analysis_case",
        case_id="missing_analysis_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.2, "unit": "V"},
            "dc_gain_db": {"min": 20.0, "unit": "dB"},
        },
    )
    ac_tb = TestBench(
        name="missing_analysis_case__ac",
        category="ac",
        circuit_name="missing_analysis_case",
        case_id="missing_analysis_case",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
    )
    FrameworkTestBenchGenerator(use_llm=False)._attach_measurement_metadata(ac_tb, specification)

    _, _, _, evidence = _aggregate_report(
        specification,
        [_bundle(case_id="missing_analysis_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=25.0)],
    )

    op_row = next(row for row in evidence if row.metric_name == "operating_point")
    assert op_row.root_cause_category == "MISSING_ANALYSIS_DECK"
    assert op_row.not_evaluated_reason


def test_missing_vector_is_not_zero():
    specification = Specification(
        name="missing_vector_case",
        case_id="missing_vector_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain_db": {"min": 20.0, "unit": "dB"}},
    )
    ac_tb = TestBench(
        name="missing_vector_case__ac",
        category="ac",
        circuit_name="missing_vector_case",
        case_id="missing_vector_case",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
    )
    FrameworkTestBenchGenerator(use_llm=False)._attach_measurement_metadata(ac_tb, specification)

    _, _, _, evidence = _aggregate_report(
        specification,
        [_bundle(case_id="missing_vector_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=None, reason="WRDATA_FILE_MISSING")],
    )

    row = evidence[0]
    assert row.raw_value is None
    assert row.normalized_value is None
    assert row.root_cause_category == "MISSING_VECTOR"


def test_semantic_guard_rejection_is_not_parser_failure():
    specification = Specification(
        name="guard_case",
        case_id="guard_case",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"oscillator_frequency": {"min": 1e6, "unit": "Hz"}},
    )
    tb = TestBench(
        name="guard_case__oscillation",
        category="transient",
        circuit_name="guard_case",
        case_id="guard_case",
        analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={"step_time": "1n", "end_time": "1u", "start_time": 0})],
        measurements=[Measurement(name="oscillator_frequency", expression="freq", unit="Hz", node="Vout")],
        metadata={},
    )
    FrameworkTestBenchGenerator(use_llm=False)._attach_measurement_metadata(tb, specification)
    bundle = _bundle(case_id="guard_case", analysis_id="oscillation", testbench=tb, metric_name="oscillator_frequency", value=None, reason="OSCILLATION_GUARD_AMPLITUDE_TOO_LOW")
    bundle.simulation_results["oscillation_validation"] = {"status": "AMPLITUDE_TOO_LOW"}

    _, _, _, evidence = _aggregate_report(specification, [bundle])

    row = evidence[0]
    assert row.root_cause_category == "EXPECTED_NOT_EVALUATED"
    assert row.root_cause_category != "PARSER_FAILURE"


def test_expected_not_evaluated_is_explicit():
    specification = Specification(
        name="expected_case",
        case_id="expected_case",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"oscillator_frequency": {"min": 1e6, "unit": "Hz"}},
    )
    tb = TestBench(
        name="expected_case__oscillation",
        category="transient",
        circuit_name="expected_case",
        case_id="expected_case",
        analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={"step_time": "1n", "end_time": "1u", "start_time": 0})],
        measurements=[Measurement(name="oscillator_frequency", expression="freq", unit="Hz", node="Vout")],
        metadata={},
    )
    FrameworkTestBenchGenerator(use_llm=False)._attach_measurement_metadata(tb, specification)
    bundle = _bundle(case_id="expected_case", analysis_id="oscillation", testbench=tb, metric_name="oscillator_frequency", value=None, reason="OSCILLATION_GUARD_NO_VALID_PERIOD")
    bundle.simulation_results["oscillation_validation"] = {"status": "NO_VALID_PERIOD"}

    _, _, _, evidence = _aggregate_report(specification, [bundle])

    row = evidence[0]
    assert row.root_cause_category == "EXPECTED_NOT_EVALUATED"
    assert row.not_evaluated_reason


def test_p04_measure_transfer_gain():
    specification = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / "p04_amplifier.yaml")
    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(
        specification,
        netlist_path=ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir",
    )
    simulator = PySpiceSimulator(allow_mock=True)

    commands = simulator._native_measure_commands(testbench)
    request = next(item for item in testbench.metadata["measurement_requests"] if item["name"] == "dc_gain_db")

    assert any("20*log10(vout_mag/vin_mag)" in command for command in commands)
    assert request["measurement_expression_id"] == "AC_TRANSFER_GAIN_DB"


def test_p04_measure_and_wrdata_agree_or_limitation_is_declared(tmp_path):
    if os.getenv("RUN_NGSPICE_INTEGRATION", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run the p04 backend reconciliation test")
    simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    if not simulator.is_available:
        pytest.skip("ngspice executable is not available")

    specification = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / "p04_amplifier.yaml")
    specification.case_id = "p04_amplifier"
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "ac_gain")
    netlist_path = ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir"

    wrdata_tb = deepcopy(build.testbench)
    wrdata_tb.metadata["measurement"] = {"required_backend": "NGSPICE_WRDATA", "allow_backend_fallback": False}
    wrdata_results = simulator.run(netlist_path, wrdata_tb, output_dir=tmp_path / "wrdata")
    wrdata_gain = compute_dc_gain_db(parse_wrdata_file(Path(wrdata_results["artifacts"]["vectors"])), {})

    measure_tb = deepcopy(build.testbench)
    measure_tb.metadata["measurement"] = {"required_backend": "NGSPICE_MEASURE", "allow_backend_fallback": False}
    measure_results = simulator.run(netlist_path, measure_tb, output_dir=tmp_path / "measure")
    measures = parse_measure_file(Path(measure_results["artifacts"]["measures"]))
    measure_gain = measures.get("dc_gain_db", {}).get("value")
    if measure_gain is None and measures.get("vin_mag", {}).get("value") and measures.get("vout_mag", {}).get("value"):
        measure_gain = 20.0 * math.log10(measures["vout_mag"]["value"] / measures["vin_mag"]["value"])

    if measure_gain is None:
        extraction = measure_results.get("native_extractions", {}).get("dc_gain_db", {})
        assert extraction.get("status") == "NOT_EVALUATED"
        assert extraction.get("reason")
    else:
        assert measure_gain == pytest.approx(wrdata_gain, abs=1e-6)


def test_nominal_summary_counts_case_rows():
    summary = summarize_nominal_rows(
        [
            {"case_id": "p01", "historical_compliance": "COMPLIANT", "reconciled_compliance": "COMPLIANT"},
            {"case_id": "p04", "historical_compliance": "COMPLIANT", "reconciled_compliance": "NONCOMPLIANT"},
            {"case_id": "p22", "historical_compliance": "COMPLIANT", "reconciled_compliance": "NOT_EVALUATED"},
        ]
    )

    assert summary["total"] == 3
    assert summary["compliant"] == 1
    assert summary["noncompliant"] == 1
    assert summary["not_evaluated"] == 1


def test_not_evaluated_reason_is_never_empty():
    specification = Specification(
        name="reason_case",
        case_id="reason_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain_db": {"min": 20.0, "unit": "dB"}},
    )
    ac_tb = TestBench(
        name="reason_case__ac",
        category="ac",
        circuit_name="reason_case",
        case_id="reason_case",
        analyses=[AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 10, "start_freq": 1.0, "stop_freq": 1e6})],
        measurements=[Measurement(name="dc_gain_db", expression="gain", unit="dB", node="Vout")],
        metadata={},
    )
    FrameworkTestBenchGenerator(use_llm=False)._attach_measurement_metadata(ac_tb, specification)

    _, _, _, evidence = _aggregate_report(
        specification,
        [_bundle(case_id="reason_case", analysis_id="ac_gain", testbench=ac_tb, metric_name="dc_gain_db", value=None, reason="WRDATA_FILE_EMPTY")],
    )

    assert all(row.not_evaluated_reason for row in evidence if row.evaluation_status == "NOT_EVALUATED")
