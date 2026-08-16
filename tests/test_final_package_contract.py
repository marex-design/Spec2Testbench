from __future__ import annotations

from pathlib import Path

import yaml

from spec2testbench import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_final_package_keeps_only_analogcoder_pro_benchmark():
    benchmark_root = ROOT / "benchmark"
    directories = sorted(path.name for path in benchmark_root.iterdir() if path.is_dir())
    assert directories == ["analogcoder_pro"]


def test_acp28_has_exactly_28_duts_and_28_canonical_v2_specs():
    acp = ROOT / "benchmark" / "analogcoder_pro"
    duts = sorted(acp.glob("p*.cir"))
    specs = sorted((acp / "specs").glob("p*.yaml"))
    assert len(duts) == 28
    assert len(specs) == 28
    for spec_path in specs:
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "2.0"


def test_legacy_duplicate_benchmark_spec_dialect_is_absent():
    assert not (ROOT / "examples" / "benchmark_specs").exists()


def test_primary_ground_truth_references_existing_artifacts():
    manifest = yaml.safe_load(
        (ROOT / "experiments" / "ground_truth" / "ground_truth_manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["cases"]
    for case in manifest["cases"]:
        for field in ("specification_file", "netlist_file", "oracle_reference"):
            path = ROOT / case[field]
            assert path.exists(), f"Missing {field} for {case['case_id']}: {path}"


def test_final_package_version():
    assert __version__ == "0.5.0"
