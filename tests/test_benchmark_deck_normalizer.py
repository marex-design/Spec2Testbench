from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from spec2testbench.application.services.benchmark_deck_normalizer import BenchmarkDeckNormalizer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmark" / "analogcoder_pro" / "manifest.csv"


def _manifest() -> dict[str, dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {Path(row["netlist"]).stem: row for row in rows}


def _normalize(case_id: str):
    row = _manifest()[case_id]
    netlist_path = ROOT / "benchmark" / "analogcoder_pro" / row["netlist"]
    return BenchmarkDeckNormalizer().normalize(
        netlist_path,
        case_id=case_id,
        declared_type=row["type"],
        declared_topology=row["description"],
        description=row["description"],
    )


def test_original_hash_is_unchanged_and_normalization_is_idempotent():
    path = ROOT / "benchmark" / "analogcoder_pro" / "p01_amplifier.cir"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result_a = _normalize("p01_amplifier")
    result_b = _normalize("p01_amplifier")
    after = hashlib.sha256(path.read_bytes()).hexdigest()

    assert before == after
    assert result_a.canonical_dut_sha256 == result_b.canonical_dut_sha256
    assert result_a.metadata_sha256 == result_b.metadata_sha256
    assert result_a.classification_sha256 == result_b.classification_sha256
    assert result_a.original_dut_logical_sha256 == result_a.canonical_dut_logical_sha256


def test_required_line_classifications_and_replaceable_rules_are_present():
    result = _normalize("p01_amplifier")
    categories = {item.selected_category for item in result.line_classifications}
    assert "MODEL_DEFINITION" in categories
    assert "SUPPLY_SOURCE" in categories
    assert "SIGNAL_SOURCE" in categories
    assert "DUT_LOAD" in categories
    assert "DUT_DEVICE" in categories
    assert "EMBEDDED_ANALYSIS_DIRECTIVE" in categories
    assert "END_DIRECTIVE" in categories

    sources = {item.name: item for item in result.sources}
    assert sources["Vdd"].role == "SUPPLY_SOURCE"
    assert sources["Vdd"].replaceable_by_testbench is False
    assert sources["Vin"].role == "SIGNAL_SOURCE"
    assert sources["Vin"].replaceable_by_testbench is True


def test_unknown_directive_is_preserved_as_ambiguity(tmp_path):
    deck = tmp_path / "unknown.cir"
    deck.write_text(
        "* test\n"
        ".MODEL nmos_model NMOS (LEVEL=1 KP=0.0001 VTO=0.5)\n"
        "Vdd Vdd 0 5\n"
        "Vin Vin 0 DC 1 AC 1\n"
        ".FOO BAR\n"
        ".END\n",
        encoding="utf-8",
    )
    result = BenchmarkDeckNormalizer().normalize(
        deck,
        case_id="unknown_case",
        declared_type="Amplifier",
        declared_topology="test deck",
        description="test deck",
    )
    assert any(item.selected_category == "UNKNOWN_DIRECTIVE" for item in result.line_classifications)
    assert any(item.manual_review_required for item in result.classification_ambiguities)


def test_p1_p4_and_p5_circuit_specific_roles_and_topologies():
    p1 = _normalize("p01_amplifier")
    assert p1.harness_metadata["signal_input_nodes"] == ["Vin"]
    assert "Vdd" in p1.harness_metadata["supply_nodes"]
    assert p1.harness_metadata["output_nodes"] == ["Vout"]
    assert p1.inferred_topology == "common-source"
    assert any(item["code"] == "AC_INPUT_MAGNITUDE_NOT_UNITY" for item in p1.anomalies)

    p4 = _normalize("p04_amplifier")
    assert p4.harness_metadata["signal_input_nodes"] == ["Vin"]
    assert p4.harness_metadata["bias_nodes"] == ["Vbias"]
    assert p4.harness_metadata["output_nodes"] == ["Vout"]
    assert p4.inferred_topology == "common-gate"
    assert any(item["code"] == "AC_INPUT_MAGNITUDE_NOT_UNITY" for item in p4.anomalies)

    p5 = _normalize("p05_amplifier")
    assert p5.harness_metadata["signal_input_nodes"] == ["Vin"]
    assert p5.harness_metadata["bias_nodes"] == ["Vbias"]
    assert "Drain_M1" in p5.harness_metadata["internal_nodes"]
    assert p5.inferred_topology == "cascode"


def test_p2_internal_bias_source_and_manual_review():
    result = _normalize("p02_amplifier")
    sources = {item.name: item for item in result.sources}
    assert sources["Vin"].role == "SIGNAL_SOURCE"
    assert sources["Vbias_M2_gate"].role == "INTERNAL_BIAS_SOURCE"
    assert result.harness_metadata["bias_nodes"] == ["Bias_M2"]
    assert result.inferred_topology == "multi-stage amplifier with common-gate-like middle stage"
    assert any(item["code"] == "MANUAL_REVIEW_REQUIRED" for item in result.anomalies)


def test_p3_and_p6_special_cases():
    p3 = _normalize("p03_amplifier")
    assert p3.harness_metadata["output_nodes"] == ["Vout"]
    assert p3.inferred_topology == "common-drain/source-follower"

    p6 = _normalize("p06_inverter")
    assert p6.harness_metadata["signal_input_nodes"] == ["Vin"]
    vin = next(item for item in p6.sources if item.name == "Vin")
    assert vin.original_waveform is None
    assert vin.original_dc_value == 0.0
    assert any(item["code"] == "TRANSIENT_ANALYSIS_WITH_CONSTANT_INPUT" for item in p6.anomalies)
