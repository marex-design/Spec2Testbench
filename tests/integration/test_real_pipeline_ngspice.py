import os
import sys
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.application.services.canonical_harness import build_case_analysis_testbenches
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.domain.value_objects.scientific_status import (
    ComplianceStatus,
    ExecutionStatus,
    ScientificCategory,
    SimulationMode,
)
from spec2testbench.presentation.formatters.report_formatter import ReportFormatter
from spec2testbench.infrastructure.simulator.result_backends import compute_dc_gain_db, parse_measure_file, parse_wrdata_file


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

UNEVALUATED_SMOKE_CASES = {
    "p08_currentmirror",
    "p22_oscillator",
}


def _integration_enabled() -> bool:
    return os.getenv("RUN_NGSPICE_INTEGRATION", "").lower() in {"1", "true", "yes"}


def _run_twice(case_id: str):
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    spec_path = Path(f"examples/benchmark_specs/{case_id}.yaml")
    netlist_path = Path(f"benchmark/analogcoder_pro/{case_id}.cir")
    return [
        pipeline.verify_from_yaml(spec_path, netlist_path),
        pipeline.verify_from_yaml(spec_path, netlist_path),
    ]


def _run_canonical_twice(case_id: str, analysis_key: str):
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    spec_path = ROOT / "examples" / "benchmark_specs" / f"{case_id}.yaml"
    netlist_path = ROOT / "benchmark" / "analogcoder_pro" / f"{case_id}.cir"
    specification = Specification.from_yaml(spec_path)
    specification.case_id = case_id
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == analysis_key)
    reports = []
    for run_index in range(2):
        artifact_dir = ROOT / "artifacts" / "canonical_harness_v1" / "integration" / f"{case_id}_{analysis_key}_{run_index + 1}"
        simulation_results = pipeline.simulator.run(netlist_path, build.testbench, output_dir=artifact_dir)
        reports.append(
            pipeline.verify(
                specification,
                netlist_path=netlist_path,
                simulation_results=simulation_results,
                spec_path=spec_path,
            )
        )
    return reports


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
    if case_id in UNEVALUATED_SMOKE_CASES:
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
    assert report.scientifically_eligible is True
    assert report.ngspice_command
    assert any("ngspice" in str(part).lower() for part in report.ngspice_command)
    assert report.ngspice_returncode == 0
    assert report.raw_result_file
    assert report.measurement_backend != "UNAVAILABLE"
    assert report.measurement_status == "SUCCESS"
    assert report.metric_traces
    if case_id == "p22_oscillator":
        osc_trace = next(metric for metric in report.metric_traces if metric.metric_name == "oscillator_frequency")
        assert osc_trace.status == "NOT_EVALUATED"
        assert osc_trace.measured_value is None
    else:
        for metric in report.metric_traces:
            assert metric.unit
            if metric.measured_value is None:
                assert metric.status == "NOT_EVALUATED"
            else:
                assert isinstance(metric.measured_value, (int, float))
                assert math.isfinite(float(metric.measured_value))
    assert report.provenance["run_id"]
    assert report.provenance["specification_hash"]
    assert report.provenance["netlist_hash"]
    assert report.provenance["simulation_mode"] == SimulationMode.REAL.value
    assert report.provenance["execution_status"] == ExecutionStatus.SUCCESS.value
    assert "ngspice" in report.provenance["ngspice_version"].lower()
    assert report.provenance["ngspice_returncode"] == 0
    assert report.provenance["measurement_backend"] != "UNAVAILABLE"
    assert report.provenance["scientific_category"] == report.scientific_category.value
    assert report.provenance["measurement_backend"] != "UNAVAILABLE"
    assert report.provenance["pyspice_required"] is False
    assert report.provenance["measurement_source"]
    assert not any("mock" in line.lower() for line in report.simulation_logs)
    assert generated_reports, f"No JSON report generated for {case_id}"


def test_real_pipeline_detects_noncompliant_frozen_variant():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    report = pipeline.verify_from_yaml(
        Path("experiments/frozen_pilot_v2/fp2_cv_019_p22_amplitude/strong/specification.yaml"),
        Path("experiments/frozen_pilot_v2/fp2_cv_019_p22_amplitude/strong/netlist.cir"),
    )

    amp_trace = next(trace for trace in report.metric_traces if trace.metric_name == "startup_amplitude")

    assert report.simulation_mode == SimulationMode.REAL
    assert report.execution_status == ExecutionStatus.SUCCESS
    assert amp_trace.status == "FAIL"
    assert report.compliance_status == ComplianceStatus.FAIL


def test_p22_replay_is_deterministic():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    first, second = _run_twice("p22_oscillator")
    first_trace = next(trace for trace in first.metric_traces if trace.metric_name == "oscillator_frequency")
    second_trace = next(trace for trace in second.metric_traces if trace.metric_name == "oscillator_frequency")
    first_amp = next(trace for trace in first.metric_traces if trace.metric_name == "startup_amplitude")
    second_amp = next(trace for trace in second.metric_traces if trace.metric_name == "startup_amplitude")

    assert first.execution_status == ExecutionStatus.SUCCESS
    assert second.execution_status == ExecutionStatus.SUCCESS
    assert first.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert second.compliance_status == ComplianceStatus.NOT_EVALUATED
    assert first_trace.status == second_trace.status == "NOT_EVALUATED"
    assert first_trace.measured_value is None
    assert second_trace.measured_value is None
    assert first_amp.status == second_amp.status == "PASS"
    assert first_amp.measured_value == pytest.approx(second_amp.measured_value, abs=1e-18)


def test_p23_replay_is_deterministic():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    first, second = _run_twice("p23_oscillator")
    first_trace = next(trace for trace in first.metric_traces if trace.metric_name == "oscillator_frequency")
    second_trace = next(trace for trace in second.metric_traces if trace.metric_name == "oscillator_frequency")
    first_amp = next(trace for trace in first.metric_traces if trace.metric_name == "startup_amplitude")
    second_amp = next(trace for trace in second.metric_traces if trace.metric_name == "startup_amplitude")

    assert first.execution_status == ExecutionStatus.SUCCESS
    assert second.execution_status == ExecutionStatus.SUCCESS
    assert first.compliance_status == ComplianceStatus.FAIL
    assert second.compliance_status == ComplianceStatus.FAIL
    assert first_trace.status == second_trace.status == "NOT_EVALUATED"
    assert first_trace.measured_value is None
    assert second_trace.measured_value is None
    assert first_amp.status == second_amp.status == "FAIL"
    assert first_amp.measured_value == pytest.approx(second_amp.measured_value, abs=0.0)


def test_ac_gain_is_invariant_to_ac_1_vs_ac_1n(tmp_path):
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    specification = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / "p04_amplifier.yaml")
    specification.case_id = "p04_amplifier"
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "ac_gain")
    simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    netlist_path = ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir"

    variant_1n = build.testbench
    variant_1n.stimuli[0].parameters["magnitude"] = 1e-9
    results_1n = simulator.run(netlist_path, variant_1n, output_dir=tmp_path / "p04_ac_1n")

    specification = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / "p04_amplifier.yaml")
    specification.case_id = "p04_amplifier"
    build = next(item for item in build_case_analysis_testbenches(specification) if item.analysis_key == "ac_gain")
    results_1 = simulator.run(netlist_path, build.testbench, output_dir=tmp_path / "p04_ac_1")

    wrdata_1n = compute_dc_gain_db(parse_wrdata_file(Path(results_1n["artifacts"]["vectors"])), {"in_real_column": 1, "in_imag_column": 2, "out_real_column": 3, "out_imag_column": 4})
    wrdata_1 = compute_dc_gain_db(parse_wrdata_file(Path(results_1["artifacts"]["vectors"])), {"in_real_column": 1, "in_imag_column": 2, "out_real_column": 3, "out_imag_column": 4})
    measures_1n = parse_measure_file(Path(results_1n["artifacts"]["measures"]))
    measures_1 = parse_measure_file(Path(results_1["artifacts"]["measures"]))
    measure_1n = measures_1n.get("dc_gain_db", {}).get("value")
    measure_1 = measures_1.get("dc_gain_db", {}).get("value")
    if measure_1n is None and measures_1n.get("vin_mag", {}).get("value") and measures_1n.get("vout_mag", {}).get("value"):
        measure_1n = 20.0 * math.log10(measures_1n["vout_mag"]["value"] / measures_1n["vin_mag"]["value"])
    if measure_1 is None and measures_1.get("vin_mag", {}).get("value") and measures_1.get("vout_mag", {}).get("value"):
        measure_1 = 20.0 * math.log10(measures_1["vout_mag"]["value"] / measures_1["vin_mag"]["value"])

    assert wrdata_1n == pytest.approx(wrdata_1, abs=1e-9)
    assert measure_1n == pytest.approx(measure_1, abs=1e-9)


def test_p22_canonical_replay_is_deterministic():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    first, second = _run_canonical_twice("p22_oscillator", "oscillation")
    first_trace = next(trace for trace in first.metric_traces if trace.metric_name == "oscillator_frequency")
    second_trace = next(trace for trace in second.metric_traces if trace.metric_name == "oscillator_frequency")
    first_amp = next(trace for trace in first.metric_traces if trace.metric_name == "startup_amplitude")
    second_amp = next(trace for trace in second.metric_traces if trace.metric_name == "startup_amplitude")

    assert first.execution_status == second.execution_status == ExecutionStatus.SUCCESS
    assert first.compliance_status == second.compliance_status == ComplianceStatus.PASS
    assert first_trace.status == second_trace.status == "PASS"
    assert first_trace.measured_value == pytest.approx(second_trace.measured_value, rel=0.0, abs=1e-9)
    assert first_amp.measured_value == pytest.approx(second_amp.measured_value, abs=1e-18)


def test_p23_canonical_replay_is_deterministic():
    if not _integration_enabled():
        pytest.skip("Set RUN_NGSPICE_INTEGRATION=1 to run ngspice integration tests")
    if not PySpiceSimulator(allow_mock=False).is_available:
        pytest.skip("ngspice executable is not available")

    first, second = _run_canonical_twice("p23_oscillator", "oscillation")
    first_trace = next(trace for trace in first.metric_traces if trace.metric_name == "oscillator_frequency")
    second_trace = next(trace for trace in second.metric_traces if trace.metric_name == "oscillator_frequency")
    first_amp = next(trace for trace in first.metric_traces if trace.metric_name == "startup_amplitude")
    second_amp = next(trace for trace in second.metric_traces if trace.metric_name == "startup_amplitude")

    assert first.execution_status == second.execution_status == ExecutionStatus.SUCCESS
    assert first.compliance_status == second.compliance_status == ComplianceStatus.FAIL
    assert first_trace.status == second_trace.status == "NOT_EVALUATED"
    assert first_amp.measured_value == pytest.approx(second_amp.measured_value, abs=0.0)
