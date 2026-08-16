from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_controlled_violations_are_materialized_and_effective():
    manifest = yaml.safe_load((ROOT / "experiments/controlled_violations/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["case_count"] == len(manifest["cases"])
    assert manifest["case_count"] >= 20
    for case in manifest["cases"]:
        mutated = ROOT / case["mutated_netlist"]
        original = ROOT / case["original_dut"]
        assert mutated.exists()
        assert original.exists()
        assert case["effective_mutation"] is True
        assert hashlib.sha256(original.read_bytes()).hexdigest() == case["original_sha256"]
        assert hashlib.sha256(mutated.read_bytes()).hexdigest() == case["mutated_sha256"]
        assert case["original_sha256"] != case["mutated_sha256"]
        active_lines = [line.strip() for line in mutated.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("*")]
        assert case["line_after"] in active_lines


def test_primary_ground_truth_is_independent_and_reproducible():
    manifest = yaml.safe_load((ROOT / "experiments/ground_truth/ground_truth_manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["oracle_policy"]["independent_of_framework_verdict"] is True
    labels = []
    for case in manifest["cases"]:
        assert (ROOT / case["specification_file"]).exists()
        assert (ROOT / case["netlist_file"]).exists()
        assert (ROOT / case["oracle_reference"]).exists()
        labels.append(case["ground_truth_label"])
    assert "GROUND_TRUTH_COMPLIANT" in labels
    assert "GROUND_TRUTH_NONCOMPLIANT" in labels
