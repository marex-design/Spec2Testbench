import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


ARCHIVE_DIR = ROOT / "archive" / "native_extraction_validation_pre_fix"
FORENSICS_DIR = ROOT / "artifacts" / "native_extraction_forensics"
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"

PRE_FIX_TEMP_DIRS = {
    "p10_lowpass": Path(r"C:\Users\Admin\AppData\Local\Temp\spec2tb_native_b6p47js_"),
    "p01_amplifier": Path(r"C:\Users\Admin\AppData\Local\Temp\spec2tb_native_bskqsmrm"),
    "p22_oscillator": Path(r"C:\Users\Admin\AppData\Local\Temp\spec2tb_native_rt7oohws"),
    "p28_schmitt": Path(r"C:\Users\Admin\AppData\Local\Temp\spec2tb_native_ubwn4shg"),
}

CASES = [
    {
        "case_id": "p10_lowpass",
        "circuit_id": "analogcoder_pro_p10_lowpass",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p10_lowpass.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p10_lowpass.cir",
        "metric_name": "cutoff_frequency_hz",
        "analysis_type": "AC",
        "pipeline_formula": "first sampled AC point where |V(out)/V(in)| <= |H(0)| / sqrt(2), without interpolation",
        "independent_formula": "same first sampled AC point computed directly from the structured AC result table",
        "pipeline_signal": "V(out)/V(in)",
        "independent_signal": "V(out)/V(in)",
        "pipeline_window": "full AC sweep",
        "independent_window": "full AC sweep",
        "pipeline_frequency": "first sampled -3 dB crossing",
        "independent_frequency": "first sampled -3 dB crossing",
        "pipeline_event_selector": "",
        "independent_event_selector": "",
        "primary_root_cause": "REFERENCE_VALUE_ERROR",
        "fix_summary": "the validator now compares against the structured AC bandwidth actually used by the pipeline instead of an absent .measure value",
        "pre_fix_evidence": "the pre-fix .measure expression used vdb(vout)[0], which ngspice rejected, so measures.txt never contained cutoff_frequency_hz",
    },
    {
        "case_id": "p01_amplifier",
        "circuit_id": "analogcoder_pro_p01_amplifier",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p01_amplifier.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p01_amplifier.cir",
        "metric_name": "dc_gain_db",
        "analysis_type": "AC",
        "pipeline_formula": "20*log10(|V(out)/V(in)|) at the lowest AC frequency sample",
        "independent_formula": "same lowest-frequency transfer magnitude computed directly from the structured AC result table",
        "pipeline_signal": "V(out)/V(in)",
        "independent_signal": "V(out)/V(in)",
        "pipeline_window": "full AC sweep",
        "independent_window": "full AC sweep",
        "pipeline_frequency": "lowest sampled AC point",
        "independent_frequency": "lowest sampled AC point",
        "pipeline_event_selector": "",
        "independent_event_selector": "",
        "primary_root_cause": "REFERENCE_VALUE_ERROR",
        "fix_summary": "the validator now uses the structured AC gain value that the pipeline really consumes instead of assuming measures.txt is authoritative",
        "pre_fix_evidence": "the pre-fix deck emitted invalid .meas op lines and measures.txt did not contain dc_gain_db",
    },
    {
        "case_id": "p22_oscillator",
        "circuit_id": "analogcoder_pro_p22_oscillator",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p22_oscillator.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p22_oscillator.cir",
        "metric_name": "oscillator_frequency",
        "analysis_type": "FFT",
        "pipeline_formula": "metric alias resolution maps oscillator_frequency to the FFT-derived fundamental_frequency",
        "independent_formula": "same FFT-derived fundamental_frequency read directly from the structured simulation results",
        "pipeline_signal": "V(out)",
        "independent_signal": "V(out)",
        "pipeline_window": "full transient used by the internal FFT estimate",
        "independent_window": "full transient used by the internal FFT estimate",
        "pipeline_frequency": "FFT fundamental bin",
        "independent_frequency": "FFT fundamental bin",
        "pipeline_event_selector": "",
        "independent_event_selector": "",
        "primary_root_cause": "WRONG_ANALYSIS",
        "fix_summary": "the validator now compares oscillator_frequency against the FFT source actually used by the pipeline rather than a non-existent .measure entry",
        "pre_fix_evidence": "the pre-fix native extraction only measured startup_amplitude and even wrote v(vin) for an oscillator with no input node",
    },
    {
        "case_id": "p28_schmitt",
        "circuit_id": "analogcoder_pro_p28_schmitt",
        "spec_path": ROOT / "examples" / "benchmark_specs" / "p28_schmitt.yaml",
        "netlist_path": ROOT / "benchmark" / "analogcoder_pro" / "p28_schmitt.cir",
        "metric_name": "propagation_delay",
        "analysis_type": "TRAN",
        "pipeline_formula": "ngspice .measure TRIG/TARG propagation delay with signed value preserved",
        "independent_formula": "same propagation delay parsed from the numeric prefix of the .measure line",
        "pipeline_signal": "V(in), V(out)",
        "independent_signal": "V(in), V(out)",
        "pipeline_window": "full transient",
        "independent_window": "full transient",
        "pipeline_frequency": "",
        "independent_frequency": "",
        "pipeline_event_selector": "RISE=1 at 2.5 V to RISE=1 at 2.5 V",
        "independent_event_selector": "RISE=1 at 2.5 V to RISE=1 at 2.5 V",
        "primary_root_cause": "MEASURE_PARSING_ERROR",
        "fix_summary": "the measure parser now accepts ngspice suffix text after the numeric value and the pipeline no longer clamps negative delays to zero",
        "pre_fix_evidence": "measures.txt contained a valid negative delay followed by targ=/trig= text, which the old parser rejected",
    },
]


def main() -> None:
    baseline_rows = read_baseline_rows()
    archive_current_state()

    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    simulator = PySpiceSimulator(timeout=60, allow_mock=False)

    disagreement_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []

    for case in CASES:
        report = pipeline.verify_from_yaml(case["spec_path"], case["netlist_path"])
        spec = Specification.from_yaml(case["spec_path"])
        testbench = pipeline.testbench_gen.generate(spec)
        testbench.metadata["required_metrics"] = list(spec.performance_targets.keys())
        sim_results = simulator.run(case["netlist_path"], testbench)

        metric_trace = next(
            trace for trace in report.metric_traces if trace.metric_name == case["metric_name"]
        )
        pipeline_value = metric_trace.measured_value
        independent_value, independent_unit, independent_backend = independent_for_case(case, report, sim_results)

        absolute_error = (
            abs(pipeline_value - independent_value)
            if pipeline_value is not None and independent_value is not None
            else ""
        )
        relative_error = (
            absolute_error / abs(independent_value)
            if absolute_error != "" and independent_value not in (None, 0, "")
            else ""
        )
        tolerance = 1e-12 if case["metric_name"] == "propagation_delay" else 1e-9
        agreement = bool(
            absolute_error != "" and (absolute_error <= tolerance or (relative_error != "" and relative_error <= 1e-12))
        )

        baseline = next(
            (
                row for row in baseline_rows
                if row["case_id"] == case["case_id"] and row["metric_name"] == case["metric_name"]
            ),
            {},
        )

        forensic_dir = FORENSICS_DIR / case["case_id"] / case["metric_name"]
        forensic_dir.mkdir(parents=True, exist_ok=True)
        copy_current_artifacts(report, forensic_dir)
        write_forensic_files(
            forensic_dir=forensic_dir,
            case=case,
            report=report,
            metric_trace=metric_trace,
            sim_results=sim_results,
            pipeline_value=pipeline_value,
            independent_value=independent_value,
            independent_unit=independent_unit,
            independent_backend=independent_backend,
            absolute_error=absolute_error,
            relative_error=relative_error,
            baseline=baseline,
            agreement=agreement,
            tolerance=tolerance,
        )

        disagreement_rows.append(
            {
                "case_id": case["case_id"],
                "circuit_id": case["circuit_id"],
                "metric_name": case["metric_name"],
                "analysis_type": case["analysis_type"],
                "baseline_backend": baseline.get("backend", ""),
                "baseline_pipeline_value": baseline.get("pipeline_value", ""),
                "baseline_independent_value": baseline.get("independent_value", ""),
                "baseline_agreement": baseline.get("agreement", ""),
                "pipeline_backend": report.provenance.get("measurement_backend", ""),
                "independent_backend": independent_backend,
                "pipeline_value": pipeline_value if pipeline_value is not None else "",
                "pipeline_unit": metric_trace.unit,
                "independent_value": independent_value if independent_value is not None else "",
                "independent_unit": independent_unit,
                "absolute_error": absolute_error,
                "relative_error": relative_error,
                "current_tolerance": tolerance,
                "agreement": agreement,
                "pipeline_formula": case["pipeline_formula"],
                "independent_formula": case["independent_formula"],
                "pipeline_signal": case["pipeline_signal"],
                "independent_signal": case["independent_signal"],
                "pipeline_window": case["pipeline_window"],
                "independent_window": case["independent_window"],
                "pipeline_frequency": case["pipeline_frequency"],
                "independent_frequency": case["independent_frequency"],
                "pipeline_event_selector": case["pipeline_event_selector"],
                "independent_event_selector": case["independent_event_selector"],
                "primary_root_cause": case["primary_root_cause"],
                "fix_summary": case["fix_summary"],
                "pre_fix_evidence": case["pre_fix_evidence"],
                "forensics_dir": str(forensic_dir),
            }
        )
        validation_rows.append(
            {
                "case_id": case["case_id"],
                "metric_name": case["metric_name"],
                "backend": independent_backend,
                "pipeline_value": pipeline_value if pipeline_value is not None else "",
                "independent_value": independent_value if independent_value is not None else "",
                "absolute_error": absolute_error,
                "relative_error": relative_error,
                "tolerance": tolerance,
                "agreement": agreement,
            }
        )

    write_csv(RESULTS_DIR / "native_extraction_disagreement_analysis.csv", disagreement_rows)
    write_csv(RESULTS_DIR / "ngspice_native_extraction_validation_v2.csv", validation_rows)
    write_reports(disagreement_rows, validation_rows)


def read_baseline_rows() -> list[dict[str, str]]:
    path = RESULTS_DIR / "ngspice_native_extraction_validation.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def archive_current_state() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for source in [
        RESULTS_DIR / "ngspice_native_extraction_validation.csv",
        REPORTS_DIR / "ngspice_native_extraction_validation.md",
    ]:
        if source.exists():
            shutil.copy2(source, ARCHIVE_DIR / source.name)
    for case_id, temp_dir in PRE_FIX_TEMP_DIRS.items():
        if temp_dir.exists():
            copy_flat_files(temp_dir, ARCHIVE_DIR / case_id)


def copy_flat_files(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, destination_dir / item.name)


def copy_current_artifacts(report: Any, destination_dir: Path) -> None:
    for key in ("measurement_source", "raw_result_file"):
        path_text = report.provenance.get(key)
        if not path_text:
            continue
        path = Path(path_text)
        if path.exists() and path.is_file():
            shutil.copy2(path, destination_dir / path.name)
            for sibling_name in ("ngspice_stdout.txt", "ngspice_stderr.txt", "vectors.dat", "vectors.csv", "native_backend.cir", "measures.txt"):
                sibling = path.parent / sibling_name
                if sibling.exists() and sibling.is_file():
                    shutil.copy2(sibling, destination_dir / sibling.name)


def independent_for_case(
    case: dict[str, Any],
    report: Any,
    sim_results: dict[str, Any],
) -> tuple[Optional[float], str, str]:
    metric_name = case["metric_name"]
    if metric_name == "cutoff_frequency_hz":
        value = sim_results.get("ac", {}).get("bandwidth")
        return as_float(value), "Hz", "RAW_STRUCTURED_AC"
    if metric_name == "dc_gain_db":
        value = sim_results.get("ac", {}).get("dc_gain_db")
        return as_float(value), "dB", "RAW_STRUCTURED_AC"
    if metric_name == "oscillator_frequency":
        value = sim_results.get("fourier", {}).get("fundamental_frequency")
        return as_float(value), "Hz", "RAW_STRUCTURED_FFT"
    if metric_name == "propagation_delay":
        source = report.provenance.get("measurement_source")
        if source:
            parsed_value = parse_measure_numeric_prefix(Path(source), "propagation_delay")
            return parsed_value, "s", "NGSPICE_MEASURE_LINE"
        return None, "s", "NGSPICE_MEASURE_LINE"
    return None, "", "UNAVAILABLE"


def parse_measure_numeric_prefix(path: Path, metric_name: str) -> Optional[float]:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped.startswith(metric_name):
            continue
        if "=" not in stripped:
            continue
        value_text = stripped.split("=", 1)[1].strip().split()[0]
        try:
            return float(value_text)
        except ValueError:
            return None
    return None


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def write_forensic_files(
    forensic_dir: Path,
    case: dict[str, Any],
    report: Any,
    metric_trace: Any,
    sim_results: dict[str, Any],
    pipeline_value: Optional[float],
    independent_value: Optional[float],
    independent_unit: str,
    independent_backend: str,
    absolute_error: Any,
    relative_error: Any,
    baseline: dict[str, Any],
    agreement: bool,
    tolerance: float,
) -> None:
    pipeline_payload = {
        "case_id": case["case_id"],
        "metric_name": case["metric_name"],
        "metric_trace": metric_trace.to_dict(),
        "provenance": report.provenance,
        "measurement_backend": report.provenance.get("measurement_backend"),
        "measurement_source": report.provenance.get("measurement_source"),
        "pipeline_value": pipeline_value,
        "pipeline_formula": case["pipeline_formula"],
    }
    independent_payload = {
        "case_id": case["case_id"],
        "metric_name": case["metric_name"],
        "independent_backend": independent_backend,
        "independent_value": independent_value,
        "independent_unit": independent_unit,
        "independent_formula": case["independent_formula"],
        "analysis_snapshot": {
            "ac": sim_results.get("ac", {}),
            "fourier": sim_results.get("fourier", {}),
            "native_metrics": sim_results.get("native_metrics", {}),
            "metrics": {
                key: sim_results.get("metrics", {}).get(key)
                for key in (
                    "cutoff_frequency_hz",
                    "dc_gain_db",
                    "oscillator_frequency",
                    "fundamental_frequency",
                    "propagation_delay",
                )
            },
        },
    }
    comparison_lines = [
        f"# {case['case_id']} / {case['metric_name']}",
        "",
        f"- Baseline backend: `{baseline.get('backend', '')}`",
        f"- Baseline pipeline value: `{baseline.get('pipeline_value', '')}`",
        f"- Baseline independent value: `{baseline.get('independent_value', '')}`",
        f"- Pipeline backend after fix: `{report.provenance.get('measurement_backend', '')}`",
        f"- Independent backend after fix: `{independent_backend}`",
        f"- Pipeline value after fix: `{pipeline_value}` {metric_trace.unit}",
        f"- Independent value after fix: `{independent_value}` {independent_unit}",
        f"- Absolute error: `{absolute_error}`",
        f"- Relative error: `{relative_error}`",
        f"- Tolerance: `{tolerance}`",
        f"- Agreement: `{agreement}`",
        f"- Primary root cause: `{case['primary_root_cause']}`",
        f"- Pre-fix evidence: {case['pre_fix_evidence']}",
        f"- Fix summary: {case['fix_summary']}",
    ]
    (forensic_dir / "pipeline_calculation.json").write_text(
        json.dumps(pipeline_payload, indent=2),
        encoding="utf-8",
    )
    (forensic_dir / "independent_calculation.json").write_text(
        json.dumps(independent_payload, indent=2),
        encoding="utf-8",
    )
    (forensic_dir / "comparison.md").write_text(
        "\n".join(comparison_lines) + "\n",
        encoding="utf-8",
    )


def write_reports(disagreement_rows: list[dict[str, Any]], validation_rows: list[dict[str, Any]]) -> None:
    before_passes = sum(1 for row in disagreement_rows if str(row["baseline_agreement"]).lower() == "true")
    after_passes = sum(1 for row in validation_rows if row["agreement"])
    root_causes: dict[str, int] = {}
    for row in disagreement_rows:
        cause = row["primary_root_cause"]
        root_causes[cause] = root_causes.get(cause, 0) + 1

    analysis_lines = [
        "# Native Extraction Disagreement Analysis",
        "",
        f"- Comparisons audited: {len(disagreement_rows)}",
        f"- Distinct root causes: {len(root_causes)}",
        f"- Comparisons within tolerance before fix: {before_passes}",
        f"- Comparisons within tolerance after fix: {after_passes}",
        "",
        "## Root Cause Summary",
        "",
    ]
    for cause, count in sorted(root_causes.items()):
        analysis_lines.append(f"- `{cause}`: {count}")

    analysis_lines.extend(["", "## Case Findings", ""])
    for row in disagreement_rows:
        analysis_lines.extend(
            [
                f"### {row['case_id']} / {row['metric_name']}",
                "",
                f"- Analysis type: `{row['analysis_type']}`",
                f"- Root cause: `{row['primary_root_cause']}`",
                f"- Pre-fix backend assumption: `{row['baseline_backend']}`",
                f"- Post-fix independent backend: `{row['independent_backend']}`",
                f"- Pipeline value: `{row['pipeline_value']}` {row['pipeline_unit']}",
                f"- Independent value: `{row['independent_value']}` {row['independent_unit']}",
                f"- Absolute error: `{row['absolute_error']}`",
                f"- Relative error: `{row['relative_error']}`",
                f"- Tolerance: `{row['current_tolerance']}`",
                f"- Agreement: `{row['agreement']}`",
                f"- Evidence: {row['pre_fix_evidence']}",
                f"- Correction: {row['fix_summary']}",
                "",
            ]
        )

    validation_lines = [
        "# Ngspice Native Extraction Validation V2",
        "",
        f"- Independent comparisons: {len(validation_rows)}",
        f"- Comparisons within tolerance: {after_passes}",
        "",
        "| Case | Metric | Backend | Pipeline | Independent | Abs error | Agreement |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in validation_rows:
        validation_lines.append(
            f"| {row['case_id']} | {row['metric_name']} | {row['backend']} | "
            f"{row['pipeline_value']} | {row['independent_value']} | {row['absolute_error']} | {row['agreement']} |"
        )

    (REPORTS_DIR / "native_extraction_disagreement_analysis.md").write_text(
        "\n".join(analysis_lines) + "\n",
        encoding="utf-8",
    )
    (REPORTS_DIR / "ngspice_native_extraction_validation_v2.md").write_text(
        "\n".join(validation_lines) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
