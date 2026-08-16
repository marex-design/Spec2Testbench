from __future__ import annotations

import csv
from pathlib import Path

from spec2testbench.application.services.canonical_reconciliation import (
    build_mutation_label_reconciliation_rows,
    summarize_nominal_rows,
)
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.metric_semantics import ACQuantityType, TRANSFER_GAIN_V2
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench import TestBenchGenerator as FrameworkTestBenchGenerator


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "canonical_reconciliation"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_nominal_p4_uses_transfer_gain_v2():
    spec = Specification.from_yaml(ROOT / "benchmark" / "analogcoder_pro" / "specs" / "p04_amplifier.yaml")
    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(
        spec,
        netlist_path=ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir",
    )

    request = next(item for item in testbench.metadata["measurement_requests"] if item["name"] == "dc_gain_db")

    assert request["metric_definition_version"] == TRANSFER_GAIN_V2
    assert request["quantity_type"] == ACQuantityType.TRANSFER_GAIN_DB.value
    assert request["measurement_expression_id"] == "AC_TRANSFER_GAIN_DB"


def test_p4_value_passed_to_checker_matches_backend_metric():
    spec = Specification.from_yaml(ROOT / "benchmark" / "analogcoder_pro" / "specs" / "p04_amplifier.yaml")
    spec.performance_targets = {"dc_gain_db": spec.performance_targets["dc_gain_db"]}
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)

    report = pipeline.verify(
        spec,
        netlist_path=ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir",
        simulation_results={
            "success": True,
            "execution_status": "SUCCESS",
            "simulation_mode": "REAL",
            "netlist_binding_status": "MATCH",
            "measurement_backend": "NGSPICE_WRDATA",
            "native_metrics": {"dc_gain_db": -160.0000000868589},
            "native_extractions": {
                "dc_gain_db": {
                    "measurement_backend": "NGSPICE_WRDATA",
                    "metric_definition_version": TRANSFER_GAIN_V2,
                    "quantity_type": ACQuantityType.TRANSFER_GAIN_DB.value,
                    "measurement_expression_id": "AC_TRANSFER_GAIN_DB",
                    "input_node": "Vin",
                    "output_node": "Vout",
                    "input_ac_magnitude": 1.0,
                    "reference_frequency_hz": 1.0,
                }
            },
            "metrics": {"dc_gain_db": 0.6527913723508354},
        },
        spec_path=ROOT / "benchmark" / "analogcoder_pro" / "specs" / "p04_amplifier.yaml",
    )

    result = next(item for item in report.spec_results if item.test_name == "dc_gain_db")
    trace = next(item for item in report.metric_traces if item.metric_name == "dc_gain_db")

    assert result.measured_value == -160.0000000868589
    assert trace.measured_value == -160.0000000868589
    assert trace.measurement_backend == "NGSPICE_WRDATA"


def test_no_active_nominal_path_uses_vdb_vout_as_gain():
    spec = Specification.from_yaml(ROOT / "benchmark" / "analogcoder_pro" / "specs" / "p04_amplifier.yaml")
    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(
        spec,
        netlist_path=ROOT / "benchmark" / "analogcoder_pro" / "p04_amplifier.cir",
    )
    simulator = PySpiceSimulator(allow_mock=True)

    commands = simulator._native_measure_commands(testbench)
    gain_request = next(item for item in testbench.metadata["measurement_requests"] if item["name"] == "dc_gain_db")

    assert any("20*log10(vout_mag/vin_mag)" in command for command in commands)
    assert not any("vdb(" in command.lower() for command in commands)
    assert gain_request["measurement_expression_id"] == "AC_TRANSFER_GAIN_DB"


def test_nominal_summary_is_recomputed_from_case_rows():
    rows = [
        {"case_id": "p01", "historical_compliance": "COMPLIANT", "reconciled_compliance": "COMPLIANT"},
        {"case_id": "p22", "historical_compliance": "COMPLIANT", "reconciled_compliance": "NOT_EVALUATED"},
        {"case_id": "p23", "historical_compliance": "COMPLIANT", "reconciled_compliance": "NONCOMPLIANT"},
        {"case_id": "p04", "historical_compliance": "NONCOMPLIANT", "reconciled_compliance": "NONCOMPLIANT"},
    ]

    summary = summarize_nominal_rows(rows)

    assert summary["compliant"] == 1
    assert summary["noncompliant"] == 2
    assert summary["not_evaluated"] == 1
    assert summary["total"] == 4
    assert summary["changed_case_ids"] == ["p22", "p23"]
    assert summary["internally_consistent"] is True
    assert summary["recomputed_from_rows"] is True


def test_mutation_label_transition_is_documented():
    rows = build_mutation_label_reconciliation_rows(
        inventory_rows=_read_csv(FIXTURE_DIR / "gain_mutation_inventory.csv"),
        old_vs_new_rows=_read_csv(FIXTURE_DIR / "mutation_old_vs_new.csv"),
        revalidation_rows=_read_csv(FIXTURE_DIR / "mutation_revalidation.csv"),
    )

    assert len(rows) == 4
    assert all(row["transition_documented"] for row in rows)
    assert all(row["transition_reason"] for row in rows)
    assert all(row["reason_for_old_label"] for row in rows)
    assert all(row["reason_for_new_label"] for row in rows)
    assert {row["final_effectiveness_label"] for row in rows} == {"INEFFECTIVE_MUTATION"}
