import json
from pathlib import Path

import pytest

from spec2testbench.infrastructure.schematic.hierarchical_parser import (
    HierarchicalNetlistParser,
)
from spec2testbench.infrastructure.schematic.publication_renderer import (
    AnalogTopologyRecognizer,
    ConnectivityValidator,
    ConstrainedAnalogPlacer,
    OrthogonalRouter,
    PublicationSchematicGenerator,
)


ROOT = Path(__file__).resolve().parents[1]
ACP_DIR = ROOT / "benchmark" / "analogcoder_pro"


def test_resolves_include_and_expands_subcircuit(tmp_path):
    library = tmp_path / "library.spice"
    library.write_text(
        ".subckt gain in out\nRinside in local 1k\nCinside local out 1n\n.ends gain\n",
        encoding="utf-8",
    )
    circuit = tmp_path / "circuit.cir"
    circuit.write_text(
        '.include "library.spice"\nVin in 0 1\nXstage in out gain scale=2\nRload out 0 10k\n.end\n',
        encoding="utf-8",
    )

    graph = HierarchicalNetlistParser().parse_path(circuit)

    assert graph.diagnostics.resolved_includes == [str(library.resolve())]
    assert graph.diagnostics.expanded_instances == ["Xstage"]
    assert not graph.diagnostics.unresolved_includes
    assert not graph.diagnostics.unresolved_instances
    assert {component.component_id for component in graph.components} == {
        "Vin",
        "Xstage/Rinside",
        "Xstage/Cinside",
        "Rload",
    }
    assert "Xstage:local" in graph.nets
    assert {pin.component_id for pin in graph.nets["in"]} == {"Vin", "Xstage/Rinside"}


def test_local_opamp_subcircuit_is_flattened():
    graph = HierarchicalNetlistParser().parse_path(ACP_DIR / "p24_integrator.cir")

    assert graph.diagnostics.expanded_instances == ["Xop"]
    assert not graph.diagnostics.unresolved_instances
    assert "Xop/M1" in {component.component_id for component in graph.components}
    assert "Vinn" in graph.nets


@pytest.mark.parametrize("netlist_path", sorted(ACP_DIR.glob("*.cir")), ids=lambda path: path.stem)
def test_acp28_normalized_connectivity_is_fully_routed(netlist_path):
    graph = HierarchicalNetlistParser().parse_path(netlist_path)
    topology = AnalogTopologyRecognizer().recognize(graph, source_name=str(netlist_path))
    placement = ConstrainedAnalogPlacer().place(graph, topology)
    routes = OrthogonalRouter().route(graph, placement)
    validation = ConnectivityValidator().validate(graph, placement, routes)

    assert validation.status == "VALID"
    assert validation.expected_component_count == validation.rendered_component_count
    assert validation.expected_pin_count == validation.routed_pin_count
    assert validation.expected_net_count == validation.routed_net_count
    assert all(
        x1 == pytest.approx(x2) or y1 == pytest.approx(y2)
        for route in routes
        for (x1, y1), (x2, y2) in route.segments
    )


def test_publication_outputs_and_report_are_created(tmp_path):
    result = PublicationSchematicGenerator().generate_from_path(
        ACP_DIR / "p04_amplifier.cir",
        tmp_path / "p04.svg",
    )

    assert result.validation.status == "VALID"
    for output in (result.svg_path, result.pdf_path, result.png_path, result.report_path):
        path = Path(output)
        assert path.exists()
        assert path.stat().st_size > 0

    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["framework"] == "Spec2Testbench"
    assert report["validation"]["status"] == "VALID"
    assert report["validation"]["scope"].startswith("structural connectivity only")
    assert report["routing"]["style"] == "orthogonal Manhattan routing"
    assert report["rendering"]["visual_scope"].startswith("topological abstraction")
    assert report["rendering"]["source_representation"].startswith(
        "ground-referenced supplies and external input voltage sources"
    )


@pytest.mark.parametrize(
    ("circuit_id", "expected_family"),
    [
        ("p07_inverter", "inverter"),
        ("p08_currentmirror", "current_source"),
        ("p17_currentmirror", "current_mirror"),
        ("p19_mixer", "gilbert_mixer"),
        ("p20_opamp", "two_stage_opamp"),
        ("p21_opamp", "telescopic_cascode"),
    ],
)
def test_acp_complex_families_select_specialized_layout(circuit_id, expected_family):
    graph = HierarchicalNetlistParser().parse_path(ACP_DIR / f"{circuit_id}.cir")

    topology = AnalogTopologyRecognizer().recognize(
        graph,
        source_name=str(ACP_DIR / f"{circuit_id}.cir"),
    )

    assert topology.family == expected_family


def test_unresolved_include_prevents_valid_connectivity_claim(tmp_path):
    netlist = tmp_path / "missing_include.cir"
    netlist.write_text(
        ".include unavailable.spice\nV1 in 0 1\nR1 in out 1k\n.end\n",
        encoding="utf-8",
    )
    graph = HierarchicalNetlistParser().parse_path(netlist)
    topology = AnalogTopologyRecognizer().recognize(graph, source_name=str(netlist))
    placement = ConstrainedAnalogPlacer().place(graph, topology)
    routes = OrthogonalRouter().route(graph, placement)

    validation = ConnectivityValidator().validate(graph, placement, routes)

    assert validation.status == "INVALID"
    assert validation.unresolved_includes == [str((tmp_path / "unavailable.spice").resolve())]


def test_curated_layout_registry_covers_all_acp28_circuits():
    expected = {path.stem for path in ACP_DIR.glob("*.cir")}

    assert set(ConstrainedAnalogPlacer.CURATED_POSITIONS) == expected


def test_appendix_profile_records_component_parameters(tmp_path):
    result = PublicationSchematicGenerator(view="appendix").generate_from_path(
        ACP_DIR / "p01_amplifier.cir",
        tmp_path / "p01.svg",
    )

    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    mos = next(component for component in report["graph"]["components"] if component["kind"] == "M")
    assert report["rendering"]["view"] == "appendix"
    assert report["rendering"]["visual_scope"].startswith("component-level connectivity")
    assert "W=" in mos["value"]
