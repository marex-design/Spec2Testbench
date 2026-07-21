from __future__ import annotations

from pathlib import Path

import pytest

from spec2testbench.application.services.canonical_harness import (
    build_case_analysis_testbenches,
    load_normalized_harness_context,
)
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, TestBench
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


ROOT = Path(__file__).resolve().parents[1]


def _builds(case_id: str):
    spec = Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / f"{case_id}.yaml")
    spec.case_id = case_id
    return build_case_analysis_testbenches(spec)


def _build_by_key(case_id: str, analysis_key: str):
    return next(build for build in _builds(case_id) if build.analysis_key == analysis_key)


def test_ac_harness_preserves_original_dc_bias():
    build = _build_by_key("p04_amplifier", "ac_gain")
    stimulus = build.testbench.stimuli[0]

    assert stimulus.type == "ac"
    assert stimulus.parameters["dc_value"] == 0.5
    assert "DC 0.5 AC 1.0" in stimulus.to_spice()


def test_ac_harness_does_not_include_pulse():
    build = _build_by_key("p04_amplifier", "ac_gain")

    assert build.testbench.category == "ac"
    assert all(stimulus.type != "pulse" for stimulus in build.testbench.stimuli)
    assert all("PULSE" not in stimulus.to_spice().upper() for stimulus in build.testbench.stimuli)


def test_ac_harness_may_normalize_ac_magnitude():
    build = _build_by_key("p04_amplifier", "ac_gain")
    source_policy = next(item for item in build.source_policies if item.source_name == "Vin")
    stimulus = build.testbench.stimuli[0]

    assert source_policy.original_ac_magnitude == 1e-9
    assert stimulus.parameters["magnitude"] == 1.0
    assert build.audit_row["harness_difference_class"] == "AUTHORIZED_AC_MAGNITUDE_NORMALIZATION"


def test_transient_harness_does_not_modify_bias_source():
    build = _build_by_key("p09_comparator", "transient_delay")
    bias_nodes = {item.positive_node for item in build.source_policies if item.source_role == "BIAS_SOURCE"}

    assert bias_nodes
    assert all(stimulus.node_positive not in bias_nodes for stimulus in build.testbench.stimuli)


def test_supply_source_is_not_replaceable():
    build = _build_by_key("p04_amplifier", "ac_gain")
    supply = next(item for item in build.source_policies if item.source_role == "SUPPLY_SOURCE")

    assert supply.replaceable_by_testbench is False
    assert "dc_value" in supply.forbidden_overrides_by_analysis["ac_gain"]


def test_bias_source_is_not_replaceable():
    build = _build_by_key("p04_amplifier", "ac_gain")
    bias = next(item for item in build.source_policies if item.source_role == "BIAS_SOURCE")

    assert bias.replaceable_by_testbench is False
    assert "dc_value" in bias.forbidden_overrides_by_analysis["ac_gain"]


def test_internal_bias_source_is_not_replaceable():
    build = _build_by_key("p02_amplifier", "ac_gain")
    internal_bias = next(item for item in build.source_policies if item.source_role == "INTERNAL_BIAS_SOURCE")

    assert internal_bias.replaceable_by_testbench is False
    assert "ground_referencing" in internal_bias.forbidden_overrides_by_analysis["ac_gain"]


def test_signal_dc_override_requires_authority():
    spec = Specification(
        name="authority_case",
        case_id="p99_authority_case",
        circuit_type=Specification.from_yaml(ROOT / "examples" / "benchmark_specs" / "p04_amplifier.yaml").circuit_type,
        performance_targets={"dc_gain_db": {"min": 0.0, "unit": "dB"}},
        input_conditions={"input_nodes": "Vin", "output_nodes": "Vout"},
    )
    context = load_normalized_harness_context("p04_amplifier")
    build = _build_by_key("p04_amplifier", "ac_gain")
    source_policy = next(item for item in build.source_policies if item.source_name == "Vin")

    no_authority = source_policy.__class__(
        **{
            **source_policy.to_dict(),
            "original_dc_value": None,
            "manual_review_required": True,
        }
    )

    assert no_authority.original_dc_value is None
    assert no_authority.manual_review_required is True
    assert context.harness_metadata["sources"][2]["original_definition"].startswith("Vin Vin 0 DC 0.5")


def test_analysis_specific_decks_are_separate():
    builds = _builds("p04_amplifier")

    assert {build.analysis_key for build in builds} == {"op", "ac_gain"}
    assert all(len(build.testbench.analyses) == 1 for build in builds)
    assert len({build.deck_name for build in builds}) == len(builds)


def test_current_mirror_op_harness_uses_nominal_op_without_fake_dc_source():
    build = _build_by_key("p08_currentmirror", "op")

    assert build.testbench.stimuli == []
    assert build.testbench.analyses[0].to_spice() == ".OP"
    assert "force_sweep" not in build.testbench.analyses[0].parameters


def test_p4_canonical_ac_bias_is_provenanced():
    build = _build_by_key("p04_amplifier", "ac_gain")

    assert build.policy.provenance["decision_authority"] == "ORIGINAL_HARNESS_DC_VALUE"
    assert "Vin Vin 0 DC 0.5 AC 1n" in build.policy.provenance["decision_evidence"]
    assert build.policy.provenance["reviewer_status"] == "AUTO"


def test_executed_deck_matches_saved_deck(tmp_path):
    simulator = PySpiceSimulator(allow_mock=False)
    netlist = tmp_path / "demo.cir"
    netlist.write_text("Vdd Vdd 0 5\nR1 out 0 1k\n.end\n", encoding="utf-8")
    testbench = TestBench(
        name="demo",
        category="dc",
        circuit_name="demo",
        case_id="demo_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="operating point", unit="V", node="out")],
    )

    def fake_run_ngspice(spice_file, raw_file, timeout_override=None, cwd=None):
        raw_file.write_text("", encoding="utf-8")
        return {
            "success": True,
            "logs": [],
            "errors": [],
            "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
            "returncode": 0,
            "raw_result_file": str(raw_file),
            "raw_result_file_exists": True,
        }

    def fake_parse_results(raw_file, testbench, native_artifacts=None):
        return {"ac": {}, "tran": {}, "transient": {}, "dc": {}, "currents": {}, "fourier": {}}

    simulator._run_ngspice = fake_run_ngspice  # type: ignore[method-assign]
    simulator._parse_results = fake_parse_results  # type: ignore[method-assign]

    results = simulator.run(netlist, testbench, output_dir=tmp_path / "artifacts")
    executed_path = Path(results["ngspice_input_file_path"])
    generated_path = Path(results["generated_testbench_path"])

    assert executed_path.read_bytes() == generated_path.read_bytes()
    assert results["serialized_deck_sha256"] == results["executed_file_sha256"] == results["post_execution_file_sha256"]


def test_no_post_serialization_deck_mutation(tmp_path):
    simulator = PySpiceSimulator(allow_mock=False)
    netlist = tmp_path / "demo.cir"
    netlist.write_text("Vdd Vdd 0 5\nR1 out 0 1k\n.end\n", encoding="utf-8")
    testbench = TestBench(
        name="demo",
        category="dc",
        circuit_name="demo",
        case_id="demo_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="operating point", unit="V", node="out")],
    )

    simulator._run_ngspice = lambda spice_file, raw_file, timeout_override=None, cwd=None: {  # type: ignore[method-assign]
        "success": True,
        "logs": [],
        "errors": [],
        "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
        "returncode": 0,
        "raw_result_file": str(raw_file),
        "raw_result_file_exists": False,
    }
    simulator._parse_results = lambda raw_file, testbench, native_artifacts=None: {"ac": {}, "tran": {}, "transient": {}, "dc": {}, "currents": {}, "fourier": {}}  # type: ignore[method-assign]

    results = simulator.run(netlist, testbench, output_dir=tmp_path / "artifacts")

    assert results["post_serialization_deck_mutation"] is False


def test_ngspice_command_uses_saved_executed_deck(tmp_path):
    simulator = PySpiceSimulator(allow_mock=False)
    netlist = tmp_path / "demo.cir"
    netlist.write_text("Vdd Vdd 0 5\nR1 out 0 1k\n.end\n", encoding="utf-8")
    testbench = TestBench(
        name="demo",
        category="dc",
        circuit_name="demo",
        case_id="demo_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="operating point", unit="V", node="out")],
    )

    simulator._run_ngspice = lambda spice_file, raw_file, timeout_override=None, cwd=None: {  # type: ignore[method-assign]
        "success": True,
        "logs": [],
        "errors": [],
        "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
        "returncode": 0,
        "raw_result_file": str(raw_file),
        "raw_result_file_exists": False,
    }
    simulator._parse_results = lambda raw_file, testbench, native_artifacts=None: {"ac": {}, "tran": {}, "transient": {}, "dc": {}, "currents": {}, "fourier": {}}  # type: ignore[method-assign]

    results = simulator.run(netlist, testbench, output_dir=tmp_path / "artifacts")

    assert results["ngspice_command"][-1] == results["ngspice_input_file_path"]


def test_executed_deck_hash_is_stable(tmp_path):
    simulator = PySpiceSimulator(allow_mock=False)
    netlist = tmp_path / "demo.cir"
    netlist.write_text("Vdd Vdd 0 5\nR1 out 0 1k\n.end\n", encoding="utf-8")
    testbench = TestBench(
        name="demo",
        category="dc",
        circuit_name="demo",
        case_id="demo_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="operating point", unit="V", node="out")],
    )

    simulator._run_ngspice = lambda spice_file, raw_file, timeout_override=None, cwd=None: {  # type: ignore[method-assign]
        "success": True,
        "logs": [],
        "errors": [],
        "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
        "returncode": 0,
        "raw_result_file": str(raw_file),
        "raw_result_file_exists": False,
    }
    simulator._parse_results = lambda raw_file, testbench, native_artifacts=None: {"ac": {}, "tran": {}, "transient": {}, "dc": {}, "currents": {}, "fourier": {}}  # type: ignore[method-assign]

    results = simulator.run(netlist, testbench, output_dir=tmp_path / "artifacts")

    assert results["compiled_plan_sha256"]
    assert results["serialized_deck_sha256"] == results["executed_file_sha256"]
    assert results["executed_file_sha256"] == results["post_execution_file_sha256"]


def test_relative_output_dir_is_resolved_before_invoking_ngspice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    simulator = PySpiceSimulator(allow_mock=False)
    netlist = tmp_path / "demo.cir"
    netlist.write_text("Vdd Vdd 0 5\nR1 out 0 1k\n.end\n", encoding="utf-8")
    testbench = TestBench(
        name="demo",
        category="dc",
        circuit_name="demo",
        case_id="demo_case",
        analyses=[AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})],
        measurements=[Measurement(name="operating_point", expression="operating point", unit="V", node="out")],
    )

    def fake_run_ngspice(spice_file, raw_file, timeout_override=None, cwd=None):
        assert cwd is not None and cwd.is_absolute()
        assert spice_file.is_absolute()
        assert raw_file.is_absolute()
        raw_file.write_text("", encoding="utf-8")
        return {
            "success": True,
            "logs": [],
            "errors": [],
            "command": [simulator.ngspice_path, "-b", "-r", str(raw_file), str(spice_file)],
            "returncode": 0,
            "raw_result_file": str(raw_file),
            "raw_result_file_exists": True,
        }

    simulator._run_ngspice = fake_run_ngspice  # type: ignore[method-assign]
    simulator._parse_results = lambda raw_file, testbench, native_artifacts=None: {"ac": {}, "tran": {}, "transient": {}, "dc": {}, "currents": {}, "fourier": {}}  # type: ignore[method-assign]

    results = simulator.run(netlist, testbench, output_dir=Path("relative_artifacts"))

    assert Path(results["ngspice_input_file_path"]).is_absolute()


def test_wrdata_only_transient_still_applies_oscillation_guard(tmp_path):
    simulator = PySpiceSimulator(allow_mock=False)
    vectors = tmp_path / "vectors.dat"
    vectors.write_text(
        "\n".join(
            [
                "0.0 2.5",
                "1.0 2.5000001",
                "2.0 2.5",
                "3.0 2.4999999",
                "4.0 2.5",
                "5.0 2.5000001",
                "6.0 2.5",
                "7.0 2.4999999",
                "8.0 2.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    measures = tmp_path / "measures.txt"
    vectors_csv = tmp_path / "vectors.csv"
    vector_metadata = tmp_path / "vector_metadata.json"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    measures.write_text("", encoding="utf-8")
    vector_metadata.write_text("{}", encoding="utf-8")

    testbench = TestBench(
        name="oscillator",
        category="transient",
        circuit_name="oscillator",
        analyses=[AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={})],
        measurements=[
            Measurement(name="oscillator_frequency", expression="frequency", unit="Hz", node="Vout"),
            Measurement(name="startup_amplitude", expression="amplitude", unit="V", node="Vout"),
        ],
        metadata={
            "oscillation_amplitude_threshold": 1e-6,
            "measurement_requests": [
                {"name": "oscillator_frequency", "preferred_backend": "NGSPICE_WRDATA", "unit": "Hz", "time_column": 0, "value_column": 1},
                {"name": "startup_amplitude", "preferred_backend": "NGSPICE_WRDATA", "unit": "V", "time_column": 0, "value_column": 1},
            ],
        },
    )
    native_artifacts = {
        "artifacts": {
            "stdout": str(stdout),
            "stderr": str(stderr),
            "measures": str(measures),
            "vectors": str(vectors),
            "vectors_csv": str(vectors_csv),
            "vector_metadata": str(vector_metadata),
        }
    }

    results = simulator._parse_results(tmp_path / "missing.raw", testbench, native_artifacts=native_artifacts)
    metrics = simulator.extract_metrics(results, testbench)

    assert results["transient"]["time"]
    assert results["oscillation_validation"]["status"] == "AMPLITUDE_TOO_LOW"
    assert "oscillator_frequency" not in metrics
    assert "oscillator_frequency" not in results["native_metrics"]
    assert results["native_extractions"]["oscillator_frequency"]["status"] == "NOT_EVALUATED"
