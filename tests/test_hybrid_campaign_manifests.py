from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_acp28_hybrid_manifest_covers_all_28_benchmark_circuits():
    path = ROOT / "experiments" / "hybrid_feedback" / "acp28_manifest.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["case_count"] == 28
    assert data["coverage_only"] is True
    cases = data["cases"]
    assert len(cases) == 28
    assert len({case["parent_circuit_id"] for case in cases}) == 28
    for case in cases:
        assert (ROOT / case["specification_file"]).exists()
        assert (ROOT / case["netlist_file"]).exists()
