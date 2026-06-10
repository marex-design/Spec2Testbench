from spec2testbench.application.usecases.run_verification import VerificationPipeline, VerificationReport
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.value_objects.verdict import CheckResult, Verdict
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor


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
        spec_results=[
            CheckResult(test_name="dc_gain", verdict=Verdict.ERROR, message="missing metric"),
        ],
    )

    assert report.overall_verdict == Verdict.ERROR


def test_verification_report_counts_warning_as_success():
    report = VerificationReport(
        circuit_name="demo",
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
    assert report.overall_verdict == Verdict.ERROR
