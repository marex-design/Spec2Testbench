from pathlib import Path

from spec2testbench.infrastructure.simulator.netlist_parser import NetlistParser


def test_mos_instance_parameters_are_not_nodes():
    parsed = NetlistParser().parse_content(
        "M1 d g s b nmos W=10u L=1u\n.MODEL nmos NMOS (LEVEL=1)\n"
    )
    mos = parsed.components[0]
    assert mos.nodes == ["d", "g", "s", "b"]
    assert mos.model == "nmos"
    assert mos.parameters == {"W": "10u", "L": "1u"}
    assert all("=" not in node for node in parsed.nodes)


def test_mos_numeric_ground_nodes_are_preserved_as_terminals():
    parsed = NetlistParser().parse_content(
        "M1 out in 0 0 nmos W=10u L=1u\n.MODEL nmos NMOS (LEVEL=1)\n"
    )
    mos = parsed.components[0]
    assert mos.nodes == ["out", "in", "0", "0"]
    assert mos.model == "nmos"
    assert mos.parameters == {"W": "10u", "L": "1u"}
    assert "0" not in parsed.nodes


def test_acp_p07_node_whitelist_contains_no_instance_parameters():
    parsed = NetlistParser().parse(Path("benchmark/analogcoder_pro/p07_inverter.cir"))
    assert "Vout" in parsed.nodes
    assert "Vin" in parsed.nodes
    assert all("=" not in node for node in parsed.nodes)
