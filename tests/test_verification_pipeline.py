import json

from spec2testbench.application.usecases.run_verification import VerificationPipeline, VerificationReport
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Stimulus, TestBench
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.value_objects.verdict import CheckResult, Verdict, ValidationStatus
from spec2testbench.domain.value_objects.scientific_status import (
    ComplianceStatus,
    ExecutionStatus,
    NetlistBindingStatus,
    ScientificCategory,
    SimulationMode,
)
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor
from spec2testbench.infrastructure.spec_checker.spec_checker import SpecChecker
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench import TestBenchGenerator as FrameworkTestBenchGenerator


def test_metric_extractor_accepts_transient_aliases():
    extractor = MetricExtractor()
    results = {
        "tran": {
            "time": [0.0, 1e-6, 2e-6],
            "voltage": {"out": [0.0, 1.0, 3.0]},
        }
    }

    assert extractor.extract(results, "slew_rate") == 2_000_000.0


def test_controlled_variant_override_applies_to_transient_analysis(tmp_path):
    spec_path = tmp_path / "specification.yaml"
    mutation_path = tmp_path / "mutation.json"
    spec_path.write_text(
        "\n".join([
            "name: override_case",
            "circuit_type: comparator",
            "performance_targets:",
            "  propagation_delay:",
            "    max: 0.001",
            "    unit: s",
            "input_conditions:",
            "  vdd: 5.0",
            "  vss: 0.0",
            "  vcm: 2.5",
            "  input_nodes: Vin",
            "  output_nodes: Vout",
            "test_categories:",
            "  - transient",
            "",
        ]),
        encoding="utf-8",
    )
    mutation_path.write_text(json.dumps({
        "case_id": "cv_override",
        "target_component": "TRAN",
        "original_value": "1U 10M",
        "mutated_value": "100U 2",
    }), encoding="utf-8")

    specification = Specification.from_yaml(spec_path)
    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification)
    transient = next(analysis for analysis in testbench.analyses if analysis.type == AnalysisType.TRANSIENT)

    assert transient.parameters["step_time"] == "100U"
    assert transient.parameters["end_time"] == "2"
    assert testbench.metadata["variant_overrides"][0]["application_status"] == "APPLIED"


def test_missing_measure_does_not_fall_back_to_synthetic_zero():
    simulator = PySpiceSimulator(allow_mock=False)
    testbench = TestBench(
        name="schmitt",
        category="transient",
        circuit_name="schmitt",
        analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={})],
        measurements=[],
        metadata={"required_metrics": ["propagation_delay"]},
    )
    results = {
        "transient": {
            "time": [0.0, 1.0, 2.0, 3.0],
            "vin": [2.3, 2.4, 2.6, 2.7],
            "vout": [0.0, 5.0, 5.0, 5.0],
        },
        "native_extractions": {
            "propagation_delay": {
                "metric_name": "propagation_delay",
                "measured_value": None,
                "status": "NOT_EVALUATED",
                "reason": "NGSPICE_MEASURE_MISSING",
                "synthetic_value_used": False,
            }
        },
    }

    metrics = simulator.extract_metrics(results, testbench)

    assert "propagation_delay" not in metrics


def test_metric_extractor_does_not_reconstruct_missing_propagation_delay():
    extractor = MetricExtractor()
    results = {
        "transient": {
            "time": [0.0, 1.0, 2.0, 3.0],
            "vin": [2.3, 2.4, 2.6, 2.7],
            "vout": [0.0, 5.0, 5.0, 5.0],
        },
        "native_extractions": {
            "propagation_delay": {
                "metric_name": "propagation_delay",
                "measured_value": None,
                "status": "NOT_EVALUATED",
                "reason": "NGSPICE_MEASURE_MISSING",
                "synthetic_value_used": False,
            }
        },
    }

    assert extractor.extract(results, "propagation_delay") is None


def test_small_threshold_minimum_does_not_snap_to_pass():
    checker = SpecChecker()
    specification = Specification(
        name="tiny_threshold",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"startup_amplitude": {"min": 1e-12, "unit": "V"}},
    )

    result = checker.verify_single_metric("startup_amplitude", 1.17961e-16, specification)

    assert result.verdict == Verdict.FAIL
    assert result.diagnostics["comparison_result"] is False


def test_small_threshold_explicit_tolerance_can_pass():
    checker = SpecChecker()
    specification = Specification(
        name="tiny_threshold_tol",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={"startup_amplitude": {"min": 1e-12, "unit": "V", "absolute_tolerance": 1e-12}},
    )

    result = checker.verify_single_metric("startup_amplitude", 1.17961e-16, specification)

    assert result.verdict == Verdict.PASS
    assert result.diagnostics["absolute_tolerance"] == 1e-12


def test_invalid_oscillation_blocks_frequency_metric():
    simulator = PySpiceSimulator(allow_mock=False)
    testbench = TestBench(
        name="oscillator",
        category="transient",
        circuit_name="oscillator",
        analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={})],
        measurements=[],
        metadata={"oscillation_amplitude_threshold": 1e-6},
    )
    results = {
        "transient": {
            "time": [0.0, 1e-6, 2e-6, 3e-6, 4e-6, 5e-6, 6e-6, 7e-6],
            "vout": [2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5],
        },
        "fourier": {"fundamental_frequency": 2e4},
    }

    metrics = simulator.extract_metrics(results, testbench)

    assert results["oscillation_validation"]["status"] == "AMPLITUDE_TOO_LOW"
    assert "oscillator_frequency" not in metrics


def test_unit_conversions_use_exact_units():
    checker = SpecChecker()

    assert checker._to_si(2500, "mV") == 2.5
    assert checker._to_si(2.5, "V") == 2.5
    assert checker._to_si(3, "MHz") == 3e6
    assert checker._to_si(4, "us") == 4e-6
    assert checker._to_si(7, "uA") == 7e-6


def test_incompatible_unit_is_not_evaluated():
    checker = SpecChecker()
    specification = Specification(
        name="unit_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"gain": {"min": 1, "unit": "bananas"}},
    )

    result = checker.verify_single_metric("gain", 2.0, specification)

    assert result.verdict == Verdict.ERROR
    assert "unit_conversion_failed" in result.message


def test_non_numeric_metric_is_not_evaluated():
    checker = SpecChecker()
    specification = Specification(
        name="numeric_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"gain": {"min": 1, "unit": "V"}},
    )

    result = checker.verify_single_metric("gain", "not-a-number", specification)

    assert result.verdict == Verdict.ERROR


def test_verification_report_treats_error_as_overall_error():
    report = VerificationReport(
        circuit_name="demo",
        testbench_generation_success=True,
        simulation_success=True,
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.ERROR, message="missing metric"),
        ],
    )

    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert report.scientific_category == ScientificCategory.UNEVALUATED
    assert report.overall_verdict == ValidationStatus.RUN


def test_empty_check_list_never_produces_pass():
    report = VerificationReport(
        circuit_name="demo",
        testbench_generation_success=True,
        simulation_success=True,
    )

    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert report.overall_verdict == ValidationStatus.RUN


def test_verification_report_counts_warning_as_success():
    report = VerificationReport(
        circuit_name="demo",
        testbench_generation_success=True,
        simulation_success=True,
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.PASS),
            CheckResult(test_name="phase_margin", verdict=Verdict.WARNING),
            CheckResult(test_name="thd", verdict=Verdict.FAIL),
        ],
    )

    assert report.success_rate == 2 / 3


def test_mock_simulation_uses_transient_key():
    pipeline = VerificationPipeline(use_llm=False)
    results = pipeline._run_mock_simulation(testbench=None)

    assert "transient" in results
    assert "tran" not in results


def test_pipeline_marks_missing_metric_as_error():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="slew_rate_check",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"slew_rate": {"min": 1e6, "unit": "V/s"}},
    )

    report = pipeline.verify(specification, simulation_results={"ac": {}, "currents": {}, "metrics": {}})

    assert report.spec_results[0].verdict == Verdict.ERROR
    assert report.execution_status == ExecutionStatus.SUCCESS
    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert report.scientific_category == ScientificCategory.UNEVALUATED
    assert report.overall_verdict == ValidationStatus.RUN


def test_successful_real_simulation_all_specs_pass():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="pass_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"dc_gain": 40},
        },
    )

    assert report.execution_status == ExecutionStatus.SUCCESS
    assert report.compliance_status == ComplianceStatus.PASS
    assert report.scientific_category == ScientificCategory.SIMULABLE_COMPLIANT
    assert report.eligible_for_paper_results is True


def test_missing_required_metric_stays_not_evaluated_not_pass():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="missing_required",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain_db": {"min": 20, "unit": "dB"}},
        test_categories=["ac"],
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {},
            "ac": {},
        },
    )

    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert report.overall_verdict == ValidationStatus.RUN
    assert report.spec_results[0].verdict == Verdict.ERROR


def test_missing_required_metric_does_not_hide_another_failure():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="mixed_required",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "dc_gain_db": {"min": 20, "unit": "dB"},
            "phase_margin": {"min": 60, "unit": "deg"},
        },
        test_categories=["ac"],
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"phase_margin": 20},
            "ac": {"phase_margin": 20},
        },
    )

    assert report.spec_results[0].verdict == Verdict.ERROR
    assert report.spec_results[1].verdict == Verdict.FAIL
    assert report.compliance_status == ComplianceStatus.FAIL


def test_wrong_metric_target_precheck_marks_case_not_evaluated():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="wrong_metric",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"unknown_metric_name": {"min": 1.0, "unit": "V"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"unknown_metric_name": 2.0},
            "dc": {"unknown_metric_name": 2.0},
        },
    )

    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert "precheck_failed" in report.spec_results[0].message


def test_netlist_binding_mismatch_is_not_paper_eligible():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="binding_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"operating_point": {"min": 0.8, "max": 1.2, "unit": "V"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": False,
            "execution_status": ExecutionStatus.ERROR.value,
            "simulation_mode": SimulationMode.REAL.value,
            "netlist_binding_status": NetlistBindingStatus.MISMATCH.value,
            "errors": ["Expected mutated netlist hash does not match the netlist included in the ngspice deck"],
        },
    )

    assert report.netlist_binding_status == NetlistBindingStatus.MISMATCH
    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert report.eligible_for_paper_results is False


def test_successful_real_simulation_one_spec_fails():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="fail_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 60, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"dc_gain": 40},
        },
    )

    assert report.execution_status == ExecutionStatus.SUCCESS
    assert report.compliance_status == ComplianceStatus.FAIL
    assert report.scientific_category == ScientificCategory.SIMULABLE_NONCOMPLIANT


def test_ngspice_error_is_non_simulable():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="error_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": False,
            "execution_status": ExecutionStatus.ERROR.value,
            "simulation_mode": SimulationMode.REAL.value,
            "errors": ["singular matrix"],
        },
    )

    assert report.execution_status == ExecutionStatus.ERROR
    assert report.scientific_category == ScientificCategory.NON_SIMULABLE


def test_timeout_is_non_simulable():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="timeout_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": False,
            "execution_status": ExecutionStatus.TIMEOUT.value,
            "simulation_mode": SimulationMode.REAL.value,
            "errors": ["Simulation timed out after 60 seconds"],
        },
    )

    assert report.execution_status == ExecutionStatus.TIMEOUT
    assert report.scientific_category == ScientificCategory.NON_SIMULABLE


def test_mock_explicitly_allowed_is_not_paper_eligible():
    pipeline = VerificationPipeline(use_llm=False, allow_mock=True)
    specification = Specification(
        name="mock_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"operating_point": {"min": 0.8, "max": 1.0, "unit": "V"}},
    )

    report = pipeline.verify(specification)

    assert report.simulation_mode == SimulationMode.MOCK
    assert report.execution_status == ExecutionStatus.SUCCESS
    assert report.eligible_for_paper_results is False


def test_mock_forbidden_without_netlist_is_skipped():
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False)
    specification = Specification(
        name="no_mock_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"operating_point": {"min": 0.8, "max": 1.0, "unit": "V"}},
    )

    report = pipeline.verify(specification)

    assert report.execution_status == ExecutionStatus.SKIPPED
    assert report.simulation_mode is None
    assert report.scientific_category == ScientificCategory.UNEVALUATED


def test_recovered_simulation_is_paper_eligible():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="recovered_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.RECOVERED.value,
            "execution_status": ExecutionStatus.SUCCESS.value,
            "recovery_actions": ["removed stale .control block"],
            "metrics": {"dc_gain": 40},
        },
    )

    assert report.simulation_mode == SimulationMode.RECOVERED
    assert report.compliance_status == ComplianceStatus.PASS
    assert report.eligible_for_paper_results is True


def test_nominal_pass_without_pvt_has_no_robustness_status():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="nominal_only",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"dc_gain": 40},
        },
    )

    assert report.compliance_status == ComplianceStatus.PASS
    assert report.robustness_status.value == "NOT_EVALUATED"


def test_nominal_pass_and_pvt_pass_are_robust_pass():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="robust_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "dc_gain": {"min": 20, "unit": "dB"},
            "pvt_dc_gain_variation": {"max": 5, "unit": "dB"},
        },
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"dc_gain": 40, "pvt_dc_gain_variation": 2},
            "pvt": {"summary": {"pvt_dc_gain_variation": 2}},
        },
    )

    assert report.compliance_status == ComplianceStatus.PASS
    assert report.robustness_status.value == "ROBUST_PASS"


def test_nominal_pass_but_pvt_fail_is_robust_fail():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="robust_fail_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "dc_gain": {"min": 20, "unit": "dB"},
            "pvt_dc_gain_variation": {"max": 5, "unit": "dB"},
        },
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": True,
            "simulation_mode": SimulationMode.REAL.value,
            "metrics": {"dc_gain": 40, "pvt_dc_gain_variation": 8},
            "pvt": {"summary": {"pvt_dc_gain_variation": 8}},
        },
    )

    assert report.compliance_status == ComplianceStatus.PASS
    assert report.robustness_status.value == "ROBUST_FAIL"


def test_absent_result_file_is_non_simulable_error():
    pipeline = VerificationPipeline(use_llm=False)
    specification = Specification(
        name="absent_file_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={"dc_gain": {"min": 20, "unit": "dB"}},
    )

    report = pipeline.verify(
        specification,
        simulation_results={
            "success": False,
            "execution_status": ExecutionStatus.ERROR.value,
            "simulation_mode": SimulationMode.REAL.value,
            "error_type": "result_file_absent",
            "errors": ["No structured ngspice result data was parsed"],
        },
    )

    assert report.error_type == "result_file_absent"
    assert report.scientific_category == ScientificCategory.NON_SIMULABLE


def test_testbench_generator_covers_paper_metrics():
    generator = FrameworkTestBenchGenerator(use_llm=False)
    specification = Specification(
        name="paper_ready_blocks",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.0, "unit": "V"},
            "quiescent_current": {"max": 2e-3, "unit": "A"},
            "power": {"max": 3e-3, "unit": "W"},
            "dc_gain_db": {"min": 50, "unit": "dB"},
            "cutoff_frequency_hz": {"min": 1e3, "unit": "Hz"},
            "ugbw": {"min": 1e5, "unit": "Hz"},
            "phase_margin_deg": {"min": 60, "unit": "deg"},
            "frequency_hz": {"min": 1e6, "unit": "Hz"},
            "thd_percent": {"max": 5.0, "unit": "%"},
            "pvt_vout_variation": {"max": 0.2, "unit": "V"},
        },
        test_categories=["dc", "ac", "transient", "spectral", "pvt"],
    )

    testbench = generator.generate(specification)
    measurement_names = {measurement.name for measurement in testbench.measurements}

    assert "operating_point" in measurement_names
    assert "quiescent_current" in measurement_names
    assert "dc_gain_db" in measurement_names
    assert "cutoff_frequency_hz" in measurement_names
    assert "ugbw" in measurement_names
    assert "frequency_hz" in measurement_names
    assert "thd_percent" in measurement_names
    assert "pvt_vout_variation" in measurement_names


def test_metric_extractor_supports_paper_metrics():
    extractor = MetricExtractor()
    results = {
        "metrics": {
            "operating_point": 0.92,
            "quiescent_current": 1.2e-3,
            "power": 2.16e-3,
            "dc_gain_db": 60.0,
            "cutoff_frequency_hz": 1e3,
            "ugbw": 1e6,
            "phase_margin_deg": 89.0,
            "propagation_delay_s": 2e-7,
            "frequency_hz": 1e7,
            "startup_amplitude": 0.6,
            "thd_percent": 0.75,
        },
        "pvt": {
            "summary": {
                "pvt_vout_variation": 0.06,
                "pvt_dc_gain_variation": 2.5,
            }
        },
    }

    assert extractor.extract(results, "operating_point") == 0.92
    assert extractor.extract(results, "quiescent_current") == 1.2e-3
    assert extractor.extract(results, "power") == 2.16e-3
    assert extractor.extract(results, "dc_gain_db") == 60.0
    assert extractor.extract(results, "cutoff_frequency_hz") == 1e3
    assert extractor.extract(results, "ugbw") == 1e6
    assert extractor.extract(results, "phase_margin_deg") == 89.0
    assert extractor.extract(results, "propagation_delay_s") == 2e-7
    assert extractor.extract(results, "frequency_hz") == 1e7
    assert extractor.extract(results, "startup_amplitude") == 0.6
    assert extractor.extract(results, "thd_percent") == 0.75
    assert extractor.extract(results, "pvt_vout_variation") == 0.06


def test_pipeline_mock_simulation_passes_core_paper_metrics():
    pipeline = VerificationPipeline(use_llm=False, allow_mock=True)
    specification = Specification(
        name="paper_eval",
        circuit_type=CircuitType.OSCILLATOR,
        performance_targets={
            "operating_point": {"min": 0.8, "max": 1.0, "unit": "V"},
            "quiescent_current": {"max": 2e-3, "unit": "A"},
            "power": {"max": 3e-3, "unit": "W"},
            "dc_gain_db": {"min": 50, "unit": "dB"},
            "cutoff_frequency_hz": {"min": 500, "unit": "Hz"},
            "ugbw": {"min": 5e5, "unit": "Hz"},
            "phase_margin_deg": {"min": 45, "unit": "deg"},
            "slew_rate": {"min": 1e5, "unit": "V/s"},
            "settling_time": {"max": 5e-6, "unit": "s"},
            "frequency_hz": {"min": 5e6, "max": 2e7, "unit": "Hz"},
            "startup_amplitude": {"min": 0.3, "unit": "V"},
            "thd_percent": {"max": 2.0, "unit": "%"},
            "pvt_vout_variation": {"max": 0.1, "unit": "V"},
            "pvt_dc_gain_variation": {"max": 5.0, "unit": "dB"},
            "pvt_power_variation": {"max": 5e-4, "unit": "W"},
        },
        test_categories=["dc", "ac", "transient", "spectral", "pvt"],
    )

    report = pipeline.verify(specification)

    assert report.overall_verdict == ValidationStatus.ROBUST_PASS
    assert all(result.verdict == Verdict.PASS for result in report.spec_results)


def test_verification_report_uses_run_for_spec_failures():
    report = VerificationReport(
        circuit_name="demo",
        testbench_generation_success=True,
        simulation_success=True,
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.PASS, category="ac"),
            CheckResult(test_name="phase_margin", verdict=Verdict.FAIL, category="ac"),
        ],
    )

    assert report.execution_status == ExecutionStatus.SUCCESS
    assert report.compliance_status == ComplianceStatus.FAIL
    assert report.scientific_category == ScientificCategory.SIMULABLE_NONCOMPLIANT
    assert report.overall_verdict == ValidationStatus.FAIL


def test_verification_report_computes_compliance_scores():
    specification = Specification(
        name="weighted_case",
        circuit_type=CircuitType.AMPLIFIER,
        performance_targets={
            "dc_gain": {"min": 40, "unit": "dB", "weight": 2.0},
            "phase_margin": {"min": 60, "unit": "deg", "weight": 1.0},
            "pvt_dc_gain_variation": {"max": 5.0, "unit": "dB", "weight": 1.0},
        },
    )
    report = VerificationReport(
        circuit_name="demo",
        specification=specification,
        testbench_generation_success=True,
        simulation_success=True,
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.PASS, category="ac"),
            CheckResult(test_name="phase_margin", verdict=Verdict.WARNING, category="ac"),
            CheckResult(test_name="pvt_dc_gain_variation", verdict=Verdict.PASS, category="pvt"),
        ],
    )

    assert report.compliance_score == 0.9375
    assert abs(report.nominal_compliance_score - ((2.0 * 1.0 + 1.0 * 0.75) / 3.0)) < 1e-9
    assert report.pvt_compliance_score == 1.0
    assert report.compliance_status == ComplianceStatus.PASS
    assert report.robustness_status.value == "ROBUST_PASS"
    assert report.overall_verdict == ValidationStatus.ROBUST_PASS


def test_ac_stimulus_preserves_dc_bias_when_collapsed():
    simulator = PySpiceSimulator()
    stimuli = [
        Stimulus(name="vin", type="dc", parameters={"value": 2.5}, node_positive="Vin", node_negative="0"),
        Stimulus(name="vin", type="ac", parameters={"magnitude": 1}, node_positive="Vin", node_negative="0"),
    ]
    analyses = [AnalysisConfig(type=AnalysisType.AC, parameters={"start_freq": 1, "stop_freq": 1e3})]

    collapsed = simulator._collapse_stimuli(stimuli, analyses)

    assert len(collapsed) == 1
    assert collapsed[0].type == "ac"
    assert collapsed[0].parameters["dc_value"] == 2.5
    assert collapsed[0].to_spice() == "Vvin Vin 0 DC 2.5 AC 1"


def test_extract_metrics_prefers_supply_current_for_quiescent_current():
    simulator = PySpiceSimulator()
    results = {
        "currents": {
            "ivvin": 0.0,
            "ivdd": -0.000225,
            "vdd": -0.000225,
        },
        "dc": {
            "vout_dc": 2.75,
            "operating_point": 2.75,
        },
        "ac": {},
        "fourier": {},
        "vdd": 5.0,
    }

    metrics = simulator.extract_metrics(results, TestBench(name="demo", category="dc"))

    assert metrics["supply_current_a"] == 0.000225
    assert metrics["quiescent_current"] == 0.000225
    assert metrics["idd"] == 0.000225


def test_pwl_stimulus_renders_valid_spice():
    stimulus = Stimulus(
        name="vin",
        type="pwl",
        parameters={"points": [("0", 0.8), ("20u", 4.2), ("40u", 0.8)]},
        node_positive="Vin",
        node_negative="0",
    )

    assert stimulus.to_spice() == "Vvin Vin 0 PWL(0 0.8 20u 4.2 40u 0.8)"


def test_simulator_extracts_included_netlist_hash(tmp_path):
    simulator = PySpiceSimulator()
    netlist = tmp_path / "variant.cir"
    netlist.write_text("R1 in out 1k\n.end\n", encoding="utf-8")
    deck = f'.include "{netlist.as_posix()}"\n.end\n'

    assert simulator._extract_included_netlist_sha(deck) == simulator._sha256_file(netlist)


def test_metric_extractor_extracts_schmitt_hysteresis_metrics():
    extractor = MetricExtractor()
    results = {
        "transient": {
            "time": [0.0, 1.0, 2.0, 3.0, 4.0],
            "vin": [1.0, 2.0, 3.0, 2.4, 2.2],
            "vout": [0.0, 0.0, 5.0, 5.0, 0.0],
        }
    }

    assert extractor.extract(results, "v_t_plus") == 3.0
    assert extractor.extract(results, "v_t_minus") == 2.2
    assert abs(extractor.extract(results, "hysteresis_width") - 0.8) < 1e-12
