from __future__ import annotations

import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "manual_oracle_subset" / "manifest.yaml"


def test_manual_oracle_subset_is_independent_and_consistent():
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert data["oracle_policy"]["independent_of_framework_verdict"] is True
    assert data["oracle_policy"]["manual_decks_are_not_generated_by_spec2testbench"] is True
    assert len(data["cases"]) >= 4
    labels = {case["expected_ground_truth_label"] for case in data["cases"]}
    assert "GROUND_TRUTH_COMPLIANT" in labels
    assert "GROUND_TRUTH_NONCOMPLIANT" in labels

    for case in data["cases"]:
        deck = ROOT / "experiments" / "manual_oracle_subset" / case["manual_deck"]
        assert deck.exists()
        assert deck.suffix == ".ckt"
        reference = case["independent_reference"]
        expected = 1.0 / (2.0 * math.pi * reference["R_ohm"] * reference["C_farad"])
        assert math.isclose(reference["expected_cutoff_frequency_hz"], expected, rel_tol=1e-12)
        expected_verdict = "PASS" if 1.0 <= expected <= 1e9 else "FAIL"
        assert case["expected_manual_verdict"] == expected_verdict
        assert case["uses_spec2testbench_verdict"] is False
