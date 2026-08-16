from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from spec2testbench.domain.specification_schema_v2 import load_acp_yaml_v2


ROOT = Path(__file__).resolve().parents[1]
ACP = ROOT / "benchmark" / "analogcoder_pro"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_acp28_manifest_and_uniform_specs_are_complete_and_hash_locked():
    manifest = yaml.safe_load((ACP / "acp28_manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 28
    assert len(manifest["cases"]) == 28
    assert [case["task_id"] for case in manifest["cases"]] == list(range(1, 29))

    specs = sorted((ACP / "specs").glob("*.yaml"))
    assert len(specs) == 28

    for case in manifest["cases"]:
        spec_path = ROOT / case["spec"]
        dut_path = ROOT / case["netlist"]
        model = load_acp_yaml_v2(spec_path)
        assert model.schema_version == "2.0"
        assert model.provenance.benchmark == "AnalogCoder-Pro"
        assert model.provenance.benchmark_subset == "ACP-28"
        assert model.provenance.upstream_task_id == case["task_id"]
        assert model.verification.immutable_dut is True
        assert model.verification.require_full_contract_for_compliance is True
        assert model.functional_requirements
        assert model.analyses
        assert model.provenance.dut.topology_and_values_preserved is True
        digest = _sha256(dut_path)
        assert digest == case["netlist_sha256"]
        assert digest == model.provenance.dut.sha256


def test_lowpass_contract_is_not_the_old_permissive_cutoff_only_spec():
    model = load_acp_yaml_v2(ACP / "specs" / "p10_lowpass.yaml")
    reqs = {r.id: r for r in model.functional_requirements}
    assert reqs["ACP_LP_ATTEN"].threshold == 2.0
    assert reqs["ACP_LP_ATTEN"].implementation_status == "executable"
    assert reqs["ACP_LP_MONO"].threshold == 90.0
    assert "lowpass_attenuation_db" in model.performance_targets
    assert "lowpass_monotonicity_percent" in model.performance_targets


def test_schmitt_and_oscillator_contracts_encode_functional_behavior():
    schmitt = load_acp_yaml_v2(ACP / "specs" / "p28_schmitt.yaml")
    sch_req = {r.id: r for r in schmitt.functional_requirements}
    assert sch_req["ACP_SCH_HYST"].threshold == 0.01
    assert sch_req["ACP_SCH_SWING"].threshold == 2.5

    osc = load_acp_yaml_v2(ACP / "specs" / "p22_oscillator.yaml")
    osc_req = {r.id: r for r in osc.functional_requirements}
    assert osc_req["ACP_OSC_CYCLES"].threshold == 3.0
    assert osc_req["ACP_OSC_PERIOD_CV"].threshold == 0.2
    assert osc_req["ACP_OSC_SWING"].threshold == 5e-6


def test_metadata_only_requirements_are_explicit_not_silently_passed():
    specs = sorted((ACP / "specs").glob("*.yaml"))
    metadata_only = []
    for path in specs:
        model = load_acp_yaml_v2(path)
        metadata_only.extend(
            (model.case_id, req.id)
            for req in model.functional_requirements
            if req.mandatory and req.implementation_status == "metadata_only"
        )
    assert metadata_only, "The schema should explicitly preserve currently unsupported upstream criteria."


def test_original_acp_source_bias_is_explicitly_restored_into_v2_stimulus_metadata():
    amp = load_acp_yaml_v2(ACP / "specs" / "p01_amplifier.yaml")
    assert amp.input_conditions["vcm"] == 1.0
    assert amp.input_conditions["original_source_dc_values"]["vin"] == 1.0
    assert amp.stimuli[0].parameters["dc_value"] == 1.0

    common_gate = load_acp_yaml_v2(ACP / "specs" / "p04_amplifier.yaml")
    assert common_gate.input_conditions["vcm"] == 0.5
    assert common_gate.stimuli[0].parameters["dc_value"] == 0.5
