import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
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
    if shutil.which("ngspice") is None and shutil.which("ngspice.exe") is None:
        pytest.skip("ngspice executable is not available")

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    report = pipeline.verify_from_yaml(Path(spec_path), Path(netlist_path))
    formatter = ReportFormatter(output_dir=tmp_path)
    formatter.to_json(report, save=True)

    generated_reports = list(tmp_path.glob("*.json"))

    assert report.testbench_generation_success is True
    assert report.simulation_mode is None or report.simulation_mode.value != "MOCK"
    assert report.provenance["run_id"]
    assert report.provenance["specification_hash"]
    assert report.provenance["netlist_hash"]
    assert report.provenance["scientific_category"] == report.scientific_category.value
    assert generated_reports, f"No JSON report generated for {case_id}"
