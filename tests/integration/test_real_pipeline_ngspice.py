import os
import sys
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.domain.value_objects.scientific_status import (
    ComplianceStatus,
    ExecutionStatus,
    ScientificCategory,
    SimulationMode,
)
from spec2testbench.presentation.formatters.report_formatter import ReportFormatter


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ngspice,
    pytest.mark.slow,
]


CASES = [
    ("p10_lowpass", "examples/benchmark_specs/p10_lowpass.yaml", "benchmark/analogcoder_pro/p10_lowpass.cir"),
    ("p01_amplifier", "examples/benchmark_specs/p01_amplifier.yaml", "benchmark/analogcoder_pro/p01_amplifier.cir"),
    ("p08_currentmirror", "examples/benchmark_specs/p08_currentmirror.yaml", "benchmark/analogcoder_pro/p08_currentmirror.cir"),
    ("p09_comparator", "examples/benchmark_specs/p09_comparator.yaml", "benchmark/analogcoder_pro/p09_comparator.cir"),
    ("p22_oscillator", "examples/benchmark_specs/p22_oscillator.yaml", "benchmark/analogcoder_pro/p22_oscillator.cir"),
]


def _integration_enabled() -> bool:
    return os.getenv("RUN_NGSPICE_INTEGRATION", "").lower() in {"1", "true", "yes"}


@pytest.mark.parametrize("case_id,spec_path,netlist_path", CASES)
def test_real_pipeline_ngspice_family_smoke(case_id, spec_path, netlist_path, tmp_path):
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    report = pipeline.verify_from_yaml(Path(spec_path), Path(netlist_path))
    formatter = ReportFormatter(output_dir=tmp_path)
    formatter.to_json(report, save=True)

    generated_reports = list(tmp_path.glob("*.json"))

    assert report.testbench_generation_success is True
    assert report.simulation_mode == SimulationMode.REAL
    assert report.execution_status == ExecutionStatus.SUCCESS
    if case_id == "p22_oscillator":
        assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
        expected_category = ScientificCategory.UNEVALUATED
    else:
        assert report.compliance_status in {ComplianceStatus.PASS, ComplianceStatus.FAIL}
        expected_category = (
            ScientificCategory.SIMULABLE_NONCOMPLIANT
            if report.compliance_status == ComplianceStatus.FAIL
            else ScientificCategory.SIMULABLE_COMPLIANT
        )
    assert report.scientific_category == expected_category
    assert report.eligible_for_paper_results is True
    assert report.ngspice_command
    assert any("ngspice" in str(part).lower() for part in report.ngspice_command)
    assert report.ngspice_returncode == 0
    assert report.raw_result_file
    assert report.raw_result_file_exists is True
    assert report.metric_traces
    if case_id == "p22_oscillator":
        osc_trace = next(metric for metric in report.metric_traces if metric.metric_name == "oscillator_frequency")
        assert osc_trace.status == "NOT_EVALUATED"
        assert osc_trace.measured_value is None
    else:
        for metric in report.metric_traces:
            assert metric.unit
            assert metric.measured_value is not None
            assert isinstance(metric.measured_value, (int, float))
            assert math.isfinite(float(metric.measured_value))
    assert report.provenance["run_id"]
    assert report.provenance["specification_hash"]
    assert report.provenance["netlist_hash"]
    assert report.provenance["simulation_mode"] == SimulationMode.REAL.value
    assert report.provenance["execution_status"] == ExecutionStatus.SUCCESS.value
    assert "ngspice" in report.provenance["ngspice_version"].lower()
    assert report.provenance["ngspice_returncode"] == 0
    assert report.provenance["raw_result_file_exists"] is True
    assert report.provenance["scientific_category"] == report.scientific_category.value
    assert report.provenance["measurement_backend"] != "UNAVAILABLE"
    assert report.provenance["pyspice_required"] is False
    assert report.provenance["measurement_source"]
    assert not any("mock" in line.lower() for line in report.simulation_logs)
    assert generated_reports, f"No JSON report generated for {case_id}"


def test_real_pipeline_detects_non_oscillating_variant_as_not_evaluated():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    report = pipeline.verify_from_yaml(
        Path("experiments/controlled_violations/generated_cases/cv_017_p22_c_large/specification.yaml"),
        Path("experiments/controlled_violations/generated_cases/cv_017_p22_c_large/mutated_netlist.cir"),
    )

    osc_trace = next(trace for trace in report.metric_traces if trace.metric_name == "oscillator_frequency")

    assert report.simulation_mode == SimulationMode.REAL
    assert report.execution_status == ExecutionStatus.SUCCESS
    assert osc_trace.status == "NOT_EVALUATED"
    assert report.compliance_status == ComplianceStatus.NOT_EVALUATED
