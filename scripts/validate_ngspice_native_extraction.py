import csv
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.infrastructure.simulator.result_backends import parse_measure_file, parse_wrdata_file


CASES = [
    ("p10_lowpass", "examples/benchmark_specs/p10_lowpass.yaml", "benchmark/analogcoder_pro/p10_lowpass.cir", "cutoff_frequency_hz"),
    ("p01_amplifier", "examples/benchmark_specs/p01_amplifier.yaml", "benchmark/analogcoder_pro/p01_amplifier.cir", "dc_gain_db"),
    ("p22_oscillator", "examples/benchmark_specs/p22_oscillator.yaml", "benchmark/analogcoder_pro/p22_oscillator.cir", "oscillator_frequency"),
    ("p28_schmitt", "examples/benchmark_specs/p28_schmitt.yaml", "benchmark/analogcoder_pro/p28_schmitt.cir", "propagation_delay"),
]


def main() -> None:
    rows = []
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    for case_id, spec_path, netlist_path, metric_name in CASES:
        report = pipeline.verify_from_yaml(Path(spec_path), Path(netlist_path))
        pipeline_value = next((trace.measured_value for trace in report.metric_traces if trace.metric_name == metric_name), None)
        backend = report.provenance.get("measurement_backend") or "UNAVAILABLE"
        source = report.provenance.get("measurement_source")
        independent_value = None
        if source:
            source_path = Path(source)
            if backend == "NGSPICE_MEASURE":
                independent_value = parse_measure_file(source_path).get(metric_name, {}).get("value")
            elif backend == "NGSPICE_WRDATA":
                try:
                    parsed = parse_wrdata_file(source_path)
                    if parsed["data"].size:
                        independent_value = float(parsed["data"][0][1]) if parsed["data"].shape[1] > 1 else None
                except Exception:
                    independent_value = None
        absolute_error = abs(pipeline_value - independent_value) if pipeline_value is not None and independent_value is not None else ""
        relative_error = (absolute_error / abs(independent_value)) if independent_value not in (None, 0, "") and absolute_error != "" else ""
        tolerance = 0.05
        agreement = absolute_error != "" and absolute_error <= tolerance if absolute_error != "" else False
        rows.append({
            "case_id": case_id,
            "metric_name": metric_name,
            "backend": backend,
            "pipeline_value": pipeline_value if pipeline_value is not None else "",
            "independent_value": independent_value if independent_value is not None else "",
            "absolute_error": absolute_error,
            "relative_error": relative_error,
            "tolerance": tolerance,
            "agreement": agreement,
        })
    write_csv(ROOT / "results" / "ngspice_native_extraction_validation.csv", rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
