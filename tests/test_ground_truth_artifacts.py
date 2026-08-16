from pathlib import Path
import hashlib
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "ground_truth" / "ground_truth_manifest.yaml"


def test_ground_truth_manifest_integrity():
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert data["oracle_policy"]["independent_of_framework_verdict"] is True
    assert data["oracle_policy"]["labels_frozen_before_spec2testbench_execution"] is True
    cases = data["cases"]
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert len(cases) >= 4
    labels = {case["ground_truth_label"] for case in cases}
    assert "GROUND_TRUTH_COMPLIANT" in labels
    assert "GROUND_TRUTH_NONCOMPLIANT" in labels
    for case in cases:
        assert (ROOT / case["specification_file"]).exists()
        assert (ROOT / case["netlist_file"]).exists()
        assert (ROOT / case["oracle_reference"]).exists()


def test_controlled_variants_manifest_is_well_formed_and_effective():
    manifest = yaml.safe_load((ROOT / "experiments" / "controlled_violations" / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["policy"]["mutations_modify_active_dut_lines_only"] is True
    cases = manifest["cases"]
    assert 20 <= len(cases) <= 50
    assert len({case["parent_circuit_id"] for case in cases}) >= 10
    for case in cases:
        parent = ROOT / case["original_dut"]
        mutated = ROOT / case["mutated_netlist"]
        specification = ROOT / case["specification"]
        assert parent.exists() and mutated.exists() and specification.exists()
        assert case["effective_mutation"] is True
        assert hashlib.sha256(parent.read_bytes()).hexdigest() == case["original_sha256"]
        assert hashlib.sha256(mutated.read_bytes()).hexdigest() == case["mutated_sha256"]
        assert case["original_sha256"] != case["mutated_sha256"]
        active = [line.strip() for line in mutated.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("*")]
        assert case["line_after"] in active
