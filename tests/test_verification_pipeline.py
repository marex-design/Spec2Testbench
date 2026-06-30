from spec2testbench.application.usecases.run_verification import VerificationPipeline, VerificationReport
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Stimulus, TestBench
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.value_objects.verdict import CheckResult, Verdict, ValidationStatus
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor
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


def test_verification_report_treats_error_as_overall_error():
    report = VerificationReport(
        circuit_name="demo",
        testbench_generation_success=True,
        simulation_success=True,
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.ERROR, message="missing metric"),
        ],
    )

    assert report.overall_verdict == ValidationStatus.FAIL


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
    assert report.overall_verdict == ValidationStatus.FAIL


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
    pipeline = VerificationPipeline(use_llm=False)
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

    assert report.overall_verdict == ValidationStatus.RUN


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
    assert report.overall_verdict == ValidationStatus.PASS


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
