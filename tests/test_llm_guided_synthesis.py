from pathlib import Path

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench import NetlistInspector, TestBenchGenerator as FrameworkTestBenchGenerator


P01_NETLIST = """* AnalogCoder-Pro p1
.MODEL nmos_model NMOS (LEVEL=1 KP=0.0001 VTO=0.5)
Vdd Vdd 0 5
Vin Vin 0 DC 1.0 AC 1n
Rload Vout Vdd 10k
M1 Vout Vin 0 0 nmos_model W=5e-05 L=1e-06
.OP
.AC DEC 100 1 1G
.END
"""


def test_netlist_inspector_detects_existing_source_and_analyses(tmp_path):
    netlist_path = tmp_path / "p01.cir"
    netlist_path.write_text(P01_NETLIST, encoding="utf-8")

    inspection = NetlistInspector.inspect(netlist_path)

    assert [source.name for source in inspection.sources] == ["dd", "in"]
    assert "op" in inspection.analyses
    assert "ac" in inspection.analyses


def test_guided_plan_attaches_to_testbench_and_consolidates_input_source(tmp_path):
    netlist_path = tmp_path / "p01.cir"
    netlist_path.write_text(P01_NETLIST, encoding="utf-8")
    specification = Specification.from_yaml(Path("examples/benchmark_specs/p01_amplifier.yaml"))

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification, netlist_path=netlist_path)
    plan = testbench.metadata["llm_guided_plan"]

    assert len(plan["source_actions"]) == 1
    assert plan["source_actions"][0]["new_source"]["node_positive"] == "Vin"
    assert plan["reuse_policy"]["allow_source_duplication_on_same_node"] is False


def test_guided_spice_deck_does_not_add_duplicate_vin_source(tmp_path):
    netlist_path = tmp_path / "p01.cir"
    netlist_path.write_text(P01_NETLIST, encoding="utf-8")
    specification = Specification.from_yaml(Path("examples/benchmark_specs/p01_amplifier.yaml"))

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification, netlist_path=netlist_path)
    deck = PySpiceSimulator(allow_mock=False)._generate_spice_deck(netlist_path, testbench)

    assert deck.count("\nVin Vin 0") == 1
    assert "\nVvin Vin 0 2.5" not in deck
    assert ".AC dec 10 1 1000000000.0" in deck
