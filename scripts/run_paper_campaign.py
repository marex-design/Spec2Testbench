import csv
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.value_objects.verdict import Verdict
from spec2testbench.presentation.formatters.report_formatter import ReportFormatter


SPEC_DIR = ROOT / "examples" / "benchmark_specs"
NETLIST_DIR = ROOT / "benchmark" / "analogcoder_pro"
CONFIG_FILE = ROOT / "configs" / "paper_experiment.yaml"
RESULTS_DIR = ROOT / "results"
ARTIFACT_ROOT = ROOT / "artifacts" / "paper_campaign"
TEST_CATEGORIES = ["dc", "ac", "transient", "spectral", "differential", "pvt"]


def main() -> None:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    pipeline = VerificationPipeline(
        use_llm=False,
        allow_mock=False,
        allow_recovery=True,
        timeout_seconds=60,
    )

    summary_rows = []
    metric_rows = []
    matrix_rows = []
    simulability_rows = []
    reports = []

    for spec_path in discover_reference_specs():
        circuit_id = spec_path.stem
        netlist_path = NETLIST_DIR / f"{circuit_id}.cir"
        circuit_dir = run_dir / circuit_id
        circuit_dir.mkdir(parents=True, exist_ok=True)

        if spec_path.exists():
            shutil.copy2(spec_path, circuit_dir / spec_path.name)
        if netlist_path.exists():
            shutil.copy2(netlist_path, circuit_dir / netlist_path.name)

        print(f"[paper-campaign] {circuit_id}")
        report = pipeline.verify_from_yaml(spec_path, netlist_path)
        reports.append(report)

        testbench_text = report.testbench.generate_spice_deck() if report.testbench else ""
        (circuit_dir / "testbench.cir").write_text(testbench_text, encoding="utf-8")
        (circuit_dir / "ngspice_command.txt").write_text(
            "ngspice -b -r <raw_file> testbench.cir\n",
            encoding="utf-8",
        )
        (circuit_dir / "stdout.txt").write_text("\n".join(report.simulation_logs), encoding="utf-8")
        (circuit_dir / "stderr.txt").write_text(
            "\n".join(report.simulation_errors or report.errors),
            encoding="utf-8",
        )
        (circuit_dir / "metrics.json").write_text(
            json.dumps([trace.to_dict() for trace in report.metric_traces], indent=2),
            encoding="utf-8",
        )
        (circuit_dir / "provenance.json").write_text(
            json.dumps(report.provenance, indent=2),
            encoding="utf-8",
        )

        formatter = ReportFormatter(output_dir=circuit_dir)
        (circuit_dir / "report.json").write_text(formatter.to_json(report, save=False), encoding="utf-8")
        (circuit_dir / "report.md").write_text(formatter.to_markdown(report, save=False), encoding="utf-8")

        expected_metrics = len(report.specification.performance_targets) if report.specification else 0
        extracted_metrics = sum(1 for result in report.spec_results if result.measured_value is not None)
        passed_metrics = sum(1 for result in report.spec_results if result.verdict in (Verdict.PASS, Verdict.WARNING))
        failed_metrics = sum(1 for result in report.spec_results if result.verdict == Verdict.FAIL)
        missing_metrics = sum(1 for result in report.spec_results if result.verdict == Verdict.ERROR)

        summary_rows.append({
            "circuit_id": circuit_id,
            "circuit_family": report.specification.circuit_type.value if report.specification else "",
            "simulation_mode": report.simulation_mode.value if report.simulation_mode else "",
            "execution_status": report.execution_status.value,
            "compliance_status": report.compliance_status.value,
            "robustness_status": report.robustness_status.value,
            "scientific_category": report.scientific_category.value,
            "expected_metrics": expected_metrics,
            "extracted_metrics": extracted_metrics,
            "passed_metrics": passed_metrics,
            "failed_metrics": failed_metrics,
            "missing_metrics": missing_metrics,
            "runtime_seconds": report.runtime_seconds,
            "paper_eligible": report.eligible_for_paper_results,
            "error_type": report.error_type or "",
        })

        for trace in report.metric_traces:
            metric_rows.append({
                "circuit_id": circuit_id,
                "metric_name": trace.metric_name,
                "measured_value": trace.measured_value,
                "unit": trace.unit,
                "operator": trace.expected_operator,
                "threshold": trace.expected_threshold,
                "metric_status": trace.status,
                "source_analysis": trace.source_analysis,
                "extraction_method": trace.extraction_method,
            })

        matrix_row = {"circuit_id": circuit_id}
        for category in TEST_CATEGORIES:
            category_results = [
                result for result in report.spec_results
                if (result.category or "").lower() == category
            ]
            matrix_row[category] = matrix_status(report, category_results)
        matrix_rows.append(matrix_row)

        simulability_rows.append({
            "circuit_id": circuit_id,
            "simulable": report.execution_status.value == "SUCCESS",
            "compliant": report.compliance_status.value == "PASS",
            "scientific_category": report.scientific_category.value,
        })

    write_csv(RESULTS_DIR / "paper_campaign_summary.csv", summary_rows)
    write_csv(RESULTS_DIR / "paper_metric_results.csv", metric_rows)
    write_csv(RESULTS_DIR / "circuit_test_matrix.csv", matrix_rows)
    write_csv(RESULTS_DIR / "simulability_vs_compliance.csv", simulability_rows)

    summary_json = {
        "run_id": run_id,
        "config_file": str(CONFIG_FILE),
        "artifact_dir": str(run_dir),
        "global_metrics": compute_global_metrics(summary_rows),
        "rows": summary_rows,
    }
    (RESULTS_DIR / "paper_campaign_summary.json").write_text(
        json.dumps(summary_json, indent=2),
        encoding="utf-8",
    )

    print(f"Paper campaign complete: {run_dir}")


def discover_reference_specs() -> list[Path]:
    spec_paths = []
    for spec_path in sorted(SPEC_DIR.glob("p*.yaml")):
        if (NETLIST_DIR / f"{spec_path.stem}.cir").exists():
            spec_paths.append(spec_path)
    return spec_paths


def matrix_status(report, category_results) -> str:
    if report.execution_status.value == "TIMEOUT":
        return "TIMEOUT"
    if report.execution_status.value == "ERROR":
        return "ERROR"
    if not category_results:
        return "NOT_EVALUATED"
    if any(result.verdict == Verdict.ERROR for result in category_results):
        return "NOT_EVALUATED"
    if any(result.verdict == Verdict.FAIL for result in category_results):
        return "FAIL"
    return "PASS"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def compute_global_metrics(rows: list[dict]) -> dict:
    total = len(rows)
    execution_success = sum(1 for row in rows if row["execution_status"] == "SUCCESS")
    simulable_compliant = sum(1 for row in rows if row["scientific_category"] == "SIMULABLE_COMPLIANT")
    simulable_noncompliant = sum(1 for row in rows if row["scientific_category"] == "SIMULABLE_NONCOMPLIANT")
    expected_metrics = sum(int(row["expected_metrics"]) for row in rows)
    extracted_metrics = sum(int(row["extracted_metrics"]) for row in rows)
    runtimes = sorted(float(row["runtime_seconds"]) for row in rows)
    paper_eligible = sum(1 for row in rows if str(row["paper_eligible"]).lower() == "true")
    counts = Counter(row["execution_status"] for row in rows)

    return {
        "simulation_success_rate": safe_ratio(execution_success, total),
        "specification_compliance_rate": safe_ratio(simulable_compliant, execution_success),
        "simulable_but_noncompliant_rate": safe_ratio(simulable_noncompliant, execution_success),
        "metric_extraction_success_rate": safe_ratio(extracted_metrics, expected_metrics),
        "paper_eligible_result_rate": safe_ratio(paper_eligible, total),
        "simulation_error_count": counts.get("ERROR", 0),
        "timeout_count": counts.get("TIMEOUT", 0),
        "average_metrics_per_circuit": safe_ratio(expected_metrics, total),
        "average_runtime_seconds": safe_ratio(sum(runtimes), len(runtimes)),
        "median_runtime_seconds": median(runtimes),
        "circuits_without_metrics": sum(1 for row in rows if int(row["extracted_metrics"]) == 0),
        "false_success_if_only_simulability": simulable_noncompliant,
    }


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / 2.0


if __name__ == "__main__":
    main()
