"""Connectivity-preserving publication schematic synthesis.

This module produces vector figures from a normalized electrical graph.  Its
validation is deliberately structural: it proves that every parsed terminal
is represented on the rendered net, not that the circuit is functionally or
specification compliant.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Circle, Polygon, Rectangle

from .hierarchical_parser import (
    HierarchicalNetlistParser,
    NormalizedCircuitGraph,
    NormalizedComponent,
    PinRef,
)


Point = tuple[float, float]
Segment = tuple[Point, Point]


@dataclass
class TopologyRecognition:
    family: str
    evidence: list[str]
    circuit_id: str | None = None


@dataclass
class ComponentPlacement:
    component_id: str
    center: Point
    orientation: str
    pin_positions: dict[int, Point]


@dataclass
class PlacementResult:
    components: dict[str, ComponentPlacement]
    input_nets: list[str]
    output_nets: list[str]
    supply_nets: list[str]
    ground_nets: list[str]


@dataclass
class NetRoute:
    net: str
    segments: list[Segment]
    junctions: list[Point]
    label_position: Point
    routed_pins: list[PinRef]
    style: str = "wire"


@dataclass
class ConnectivityValidation:
    status: str
    scope: str
    expected_component_count: int
    rendered_component_count: int
    expected_pin_count: int
    routed_pin_count: int
    expected_net_count: int
    routed_net_count: int
    missing_components: list[str] = field(default_factory=list)
    missing_pins: list[str] = field(default_factory=list)
    missing_nets: list[str] = field(default_factory=list)
    extra_pins: list[str] = field(default_factory=list)
    unresolved_includes: list[str] = field(default_factory=list)
    unresolved_instances: list[str] = field(default_factory=list)


@dataclass
class PublicationSchematicResult:
    svg_path: str
    pdf_path: str
    png_path: str
    report_path: str
    validation: ConnectivityValidation
    topology: TopologyRecognition


class AnalogTopologyRecognizer:
    """Recognize broad analog families without changing circuit semantics."""

    def recognize(
        self, graph: NormalizedCircuitGraph, source_name: str | None = None
    ) -> TopologyRecognition:
        stem = Path(source_name).stem.lower() if source_name else ""
        mos = graph.by_kind("M")
        resistors = graph.by_kind("R")
        capacitors = graph.by_kind("C")
        evidence: list[str] = []

        if "currentmirror" in stem:
            if len(mos) == 1:
                return TopologyRecognition(
                    "current_source",
                    ["benchmark family name and one biased MOS output branch"],
                )
            return TopologyRecognition(
                "current_mirror",
                [f"benchmark family name and {len(mos)} MOS devices"],
            )
        if "inverter" in stem:
            return TopologyRecognition("inverter", ["benchmark family name: inverter"])
        if "mixer" in stem:
            return TopologyRecognition("gilbert_mixer", ["benchmark family name: mixer"])
        if stem.startswith("p20_"):
            return TopologyRecognition("two_stage_opamp", ["ACP-28 p20 two-stage opamp netlist"])
        if stem.startswith("p21_"):
            return TopologyRecognition("telescopic_cascode", ["ACP-28 p21 telescopic-cascode netlist"])
        if any(word in stem for word in ("oscillator", "ring", "vco")):
            return TopologyRecognition("oscillator", [f"source name: {stem}"])

        differential_pairs = self._differential_pairs(mos)
        if differential_pairs:
            evidence.append(
                "MOS pair with a shared source net and distinct gate nets: "
                + ", ".join(f"{left}/{right}" for left, right in differential_pairs)
            )
            return TopologyRecognition("differential", evidence)

        mirror_pairs = self._current_mirror_pairs(mos)
        if mirror_pairs:
            evidence.append(
                "MOS pair with a shared gate and one diode-connected device: "
                + ", ".join(f"{left}/{right}" for left, right in mirror_pairs)
            )
            return TopologyRecognition("current_mirror", evidence)

        macros = graph.by_kind("X")
        if any((component.model or "").lower().startswith("opamp") for component in macros):
            return TopologyRecognition(
                "opamp_macro",
                ["resolved three-terminal opamp subcircuit represented hierarchically"],
            )
        if macros:
            return TopologyRecognition("hierarchical_macro", ["resolved subcircuit instance present"])

        if resistors and capacitors and not mos:
            evidence.append(
                f"passive RC network ({len(resistors)} resistor(s), {len(capacitors)} capacitor(s))"
            )
            return TopologyRecognition("rc_network", evidence)

        if mos:
            evidence.append(f"transistor-level circuit with {len(mos)} MOS device(s)")
            family = "opamp" if "opamp" in stem else "amplifier"
            return TopologyRecognition(family, evidence)

        return TopologyRecognition("generic", ["no stronger topology signature detected"])

    @staticmethod
    def _differential_pairs(mos: list[NormalizedComponent]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for index, left in enumerate(mos):
            if len(left.nodes) < 3:
                continue
            for right in mos[index + 1 :]:
                if len(right.nodes) < 3:
                    continue
                if (
                    left.variant == right.variant
                    and left.nodes[2] == right.nodes[2]
                    and left.nodes[1] != right.nodes[1]
                    and left.nodes[0] != left.nodes[1]
                    and right.nodes[0] != right.nodes[1]
                ):
                    pairs.append((left.component_id, right.component_id))
        return pairs

    @staticmethod
    def _current_mirror_pairs(mos: list[NormalizedComponent]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for index, left in enumerate(mos):
            if len(left.nodes) < 3:
                continue
            for right in mos[index + 1 :]:
                if len(right.nodes) < 3 or left.variant != right.variant:
                    continue
                same_gate = left.nodes[1] == right.nodes[1]
                diode_connected = left.nodes[0] == left.nodes[1] or right.nodes[0] == right.nodes[1]
                if same_gate and diode_connected:
                    pairs.append((left.component_id, right.component_id))
        return pairs


class ConstrainedAnalogPlacer:
    """Place real components using signal flow and analog device conventions."""

    GROUND_NAMES = {"0", "gnd", "vss", "vee"}
    CURATED_POSITIONS: dict[str, dict[str, Point]] = {
        "p01_amplifier": {"Rload": (6, 2.2), "M1": (6, -1)},
        "p02_amplifier": {
            "M1": (4, -1), "R1": (4, 2.2), "M2": (7, -1),
            "R2": (7, 2.2), "M3": (10, -1), "R3": (10, 2.2),
            "Vbias_M2_gate": (5.5, 0.5),
        },
        "p03_amplifier": {"M1": (6, 1.2), "Rload": (6, -2)},
        "p04_amplifier": {"M1": (6, -0.5), "Rload": (6, 2.5)},
        "p05_amplifier": {"M1": (6, -2.2), "M2": (6, 0.5), "Rload": (6, 3.4)},
        "p06_inverter": {"M1": (6, -1), "Rload": (6, 2.2)},
        "p07_inverter": {"M_N": (6, -1.5), "M_P": (6, 1.5)},
        "p08_currentmirror": {"M1": (6, -1), "Rload": (6, 2.2)},
        "p09_comparator": {"Xcmp": (8, 0)},
        "p10_lowpass": {"R1": (4, 0), "C1": (7, -2)},
        "p11_highpass": {"C1": (4, 0), "R1": (7, -2)},
        "p12_bandpass": {"C1": (3, 0), "R1": (6, -2), "R2": (8, 0), "C2": (11, -2)},
        "p13_bandstop": {"R1": (4, 0), "L1": (7, 0), "C1": (10, -2)},
        "p14_amplifier": {
            "M1": (4, -1), "M2": (4, 2), "M3": (8, -1),
            "Rload": (8, 2), "Cmiller": (6, 0.5),
        },
        "p15_amplifier": {"M1": (6, -1.5), "M2": (6, 1.5)},
        "p16_opamp": {"M1": (6, 0), "M2": (9, 0), "Mtail": (7.5, -3.2), "M3": (6, 3.3), "M4": (9, 3.3)},
        "p17_currentmirror": {"M1": (5.5, -1.5), "M2": (5.5, 1.2), "M3": (9, -1.5), "M4": (9, 1.2), "R1": (9, 4), "Iref": (5.5, 4)},
        "p18_opamp": {"M1": (5, 0), "M2": (8, 0), "Mtail": (6.5, -3), "R1": (5, 3), "R2": (8, 3)},
        "p19_mixer": {"M7": (8, -4), "M1": (6, -1.3), "M2": (10, -1.3), "M3": (5, 1.5), "M5": (7, 1.5), "M4": (9, 1.5), "M6": (11, 1.5), "RL1": (6, 4.3), "RL2": (10, 4.3)},
        "p20_opamp": {"M1": (5, 0), "M2": (8, 0), "M3": (6.5, -3), "M4": (5, 3), "M5": (8, 3), "M6": (12, -1.2), "M7": (12, 2), "M8": (15, 2), "Rb": (15, -1.2)},
        "p21_opamp": {"M9": (8, -4), "M1": (6, -1.3), "M2": (10, -1.3), "M3": (6, 1.2), "M4": (10, 1.2), "M5": (6, 3.7), "M6": (10, 3.7), "M7": (6, 6.2), "M8": (10, 6.2)},
        "p22_oscillator": {"R3": (3, 1.8), "C3": (3, -1.5), "R2": (6, 1.8), "C2": (6, -1.5), "R1": (9, 1.8), "C1": (9, -1.5), "Rin": (8.5, -0.2), "Rf": (11, 3.8), "X1": (12, 0)},
        "p23_oscillator": {"R2": (4, -1.5), "C2": (6, -1.5), "C1": (7, 0.5), "R1": (9, 1.8), "Rf2": (9, -1), "Rf1": (11, 3.5), "X1": (12, 0)},
        "p24_integrator": {"R1": (4.5, -1.2), "Cf": (9, 2.8), "Xop": (9, 0)},
        "p25_differentiator": {"C1": (4, -1), "Rb": (6.5, -2.3), "Rf": (9, 2.8), "Xop": (9, 0)},
        "p26_adder": {"R1": (4, -0.8), "R2": (4, -2.6), "Rf": (9, 2.8), "Xop": (9, 0)},
        "p27_subtractor": {"R1": (4, -1.2), "R2": (9, 2.8), "R3": (4, 1.5), "R4": (7, 1.5), "Xop": (9, 0)},
        "p28_schmitt": {"R1": (4, 1), "R2": (8, 2.8), "R3": (5, -2), "Xop": (9, 0)},
    }

    def place(
        self, graph: NormalizedCircuitGraph, topology: TopologyRecognition
    ) -> PlacementResult:
        ground_nets = sorted(net for net in graph.nets if net.lower() in self.GROUND_NAMES)
        supply_nets = sorted(
            net
            for net in graph.nets
            if re.search(r"(^|[:/])(vdd|vcc|vdda|vddd)$", net, re.IGNORECASE)
        )
        input_nets = sorted(net for net in graph.nets if self._is_input(net))
        output_nets = sorted(net for net in graph.nets if self._is_output(net))
        excluded = set(ground_nets + supply_nets)
        layers = self._signal_layers(graph, input_nets, excluded)

        placements: dict[str, ComponentPlacement] = {}
        occupied: dict[tuple[int, int], int] = {}
        source_role_counts = {"supply": 0, "input": 0, "bias": 0, "other": 0}
        max_layer = max(layers.values(), default=1)

        for index, component in enumerate(graph.components):
            layer = layers.get(component.component_id, max_layer + 1)
            x = layer * 3.6
            y = self._preferred_y(component, topology)

            if component.kind in {"V", "I"} and any(net in ground_nets for net in component.nodes):
                role = self._source_role(component, input_nets, supply_nets)
                slot_index = source_role_counts[role]
                source_role_counts[role] += 1
                x = 0.0
                if role == "supply":
                    y = 4.2 + 2.3 * slot_index
                elif role == "bias":
                    y = 1.2 + 2.3 * slot_index
                elif role == "input":
                    y = -2.2 - 2.3 * slot_index
                else:
                    y = -5.0 - 2.3 * slot_index
            if any(net in output_nets for net in component.nodes):
                x = max(x, (max_layer + 1) * 3.6)

            slot = (round(x), round(y))
            collision = occupied.get(slot, 0)
            occupied[slot] = collision + 1
            if collision:
                y += 2.4 * collision * (1 if collision % 2 else -1)
                x += 0.45 * collision

            orientation = self._orientation(component, ground_nets, supply_nets)
            pin_positions = self._pin_positions(
                component,
                (x, y),
                orientation,
                ground_nets=ground_nets,
                supply_nets=supply_nets,
            )
            placements[component.component_id] = ComponentPlacement(
                component_id=component.component_id,
                center=(x, y),
                orientation=orientation,
                pin_positions=pin_positions,
            )

        self._apply_family_constraints(
            graph,
            topology,
            placements,
            ground_nets=ground_nets,
            supply_nets=supply_nets,
        )
        self._apply_curated_positions(
            graph,
            topology,
            placements,
            ground_nets=ground_nets,
            supply_nets=supply_nets,
        )
        self._align_boundary_voltage_sources(
            graph,
            placements,
            ground_nets=ground_nets,
            supply_nets=supply_nets,
        )

        return PlacementResult(
            components=placements,
            input_nets=input_nets,
            output_nets=output_nets,
            supply_nets=supply_nets,
            ground_nets=ground_nets,
        )

    def _apply_curated_positions(
        self,
        graph: NormalizedCircuitGraph,
        topology: TopologyRecognition,
        placements: dict[str, ComponentPlacement],
        *,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        hints = self.CURATED_POSITIONS.get(topology.circuit_id or "", {})
        by_name = {component.name: component for component in graph.components}
        for name, center in hints.items():
            component = by_name.get(name)
            if component is not None:
                self._move_component(component, center, placements, ground_nets, supply_nets)

    def _align_boundary_voltage_sources(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        *,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        used_y: list[float] = []
        for component in graph.by_kind("V"):
            is_external_input = component.name.lower().startswith("vin")
            if not set(component.nodes) & set(ground_nets) and not is_external_input:
                continue
            signal_pins = [pin for pin in component.pins if pin.net not in ground_nets]
            if is_external_input and component.pins:
                signal_pins = [component.pins[0]]
            if not signal_pins:
                continue
            signal_net = signal_pins[0].net
            targets: list[Point] = []
            for pin in graph.nets.get(signal_net, []):
                if pin.component_id == component.component_id:
                    continue
                target_placement = placements.get(pin.component_id)
                if target_placement is not None:
                    targets.append(target_placement.pin_positions[pin.pin_index])
            desired_y = median(point[1] for point in targets) if targets else 0.0
            while any(abs(desired_y - occupied_y) < 1.1 for occupied_y in used_y):
                desired_y -= 1.25
            used_y.append(desired_y)
            target_min_x = min((point[0] for point in targets), default=4.0)
            center = (min(-0.5, target_min_x - 4.0), desired_y)
            placements[component.component_id] = ComponentPlacement(
                component_id=component.component_id,
                center=center,
                orientation="boundary",
                pin_positions=self._pin_positions(
                    component,
                    center,
                    "boundary",
                    ground_nets=ground_nets,
                    supply_nets=supply_nets,
                ),
            )

    def _apply_family_constraints(
        self,
        graph: NormalizedCircuitGraph,
        topology: TopologyRecognition,
        placements: dict[str, ComponentPlacement],
        *,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        specialized = {
            "inverter": self._place_inverter,
            "current_source": self._place_current_source,
            "current_mirror": self._place_current_mirror,
            "gilbert_mixer": self._place_gilbert_mixer,
            "two_stage_opamp": self._place_two_stage_opamp,
            "telescopic_cascode": self._place_telescopic_cascode,
        }.get(topology.family)
        if specialized is not None:
            specialized(graph, placements, ground_nets, supply_nets)
            return
        if topology.family == "opamp_macro":
            self._place_opamp_macro(
                graph,
                placements,
                ground_nets=ground_nets,
                supply_nets=supply_nets,
            )
            return
        if topology.family != "differential":
            return
        pairs = AnalogTopologyRecognizer._differential_pairs(graph.by_kind("M"))
        if not pairs:
            return
        by_id = {component.component_id: component for component in graph.components}
        left = by_id[pairs[0][0]]
        right = by_id[pairs[0][1]]
        self._move_component(left, (6.0, 0.0), placements, ground_nets, supply_nets)
        self._move_component(right, (9.0, 0.0), placements, ground_nets, supply_nets)

        shared_source = left.nodes[2]
        remaining_mos = [
            component
            for component in graph.by_kind("M")
            if component.component_id not in {left.component_id, right.component_id}
        ]
        tail = next(
            (
                component
                for component in remaining_mos
                if component.nodes and component.nodes[0] == shared_source
            ),
            None,
        )
        if tail is not None:
            self._move_component(tail, (7.5, -3.2), placements, ground_nets, supply_nets)

        pmos = [component for component in remaining_mos if component.variant == "pmos"]
        for index, component in enumerate(pmos[:2]):
            x = 6.0 if component.nodes[0] == left.nodes[0] else 9.0
            if index == 1 and x == 6.0:
                x = 9.0
            self._move_component(component, (x, 3.3), placements, ground_nets, supply_nets)

    def _place_inverter(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        nmos = [component for component in graph.by_kind("M") if component.variant != "pmos"]
        pmos = [component for component in graph.by_kind("M") if component.variant == "pmos"]
        if nmos:
            self._move_component(nmos[0], (7.0, -1.5), placements, ground_nets, supply_nets)
        if pmos:
            self._move_component(pmos[0], (7.0, 1.5), placements, ground_nets, supply_nets)

    def _place_current_source(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        mos = graph.by_kind("M")
        resistors = graph.by_kind("R")
        if mos:
            self._move_component(mos[0], (7.0, -1.0), placements, ground_nets, supply_nets)
        if resistors:
            self._move_component(resistors[0], (7.0, 2.2), placements, ground_nets, supply_nets)

    def _place_current_mirror(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        by_name = {component.name.upper(): component for component in graph.components}
        coordinates = {
            "M1": (5.5, -1.5),
            "M2": (5.5, 1.2),
            "M3": (9.0, -1.5),
            "M4": (9.0, 1.2),
            "R1": (9.0, 4.0),
            "IREF": (5.5, 4.0),
        }
        for name, center in coordinates.items():
            component = by_name.get(name)
            if component is not None:
                self._move_component(component, center, placements, ground_nets, supply_nets)

    def _place_gilbert_mixer(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        by_name = {component.name.upper(): component for component in graph.components}
        coordinates = {
            "M7": (8.0, -4.0),
            "M1": (6.0, -1.3),
            "M2": (10.0, -1.3),
            "M3": (5.0, 1.5),
            "M5": (7.0, 1.5),
            "M4": (9.0, 1.5),
            "M6": (11.0, 1.5),
            "RL1": (6.0, 4.3),
            "RL2": (10.0, 4.3),
        }
        for name, center in coordinates.items():
            component = by_name.get(name)
            if component is not None:
                self._move_component(component, center, placements, ground_nets, supply_nets)

    def _place_two_stage_opamp(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        by_name = {component.name.upper(): component for component in graph.components}
        coordinates = {
            "M1": (5.0, 0.0),
            "M2": (8.0, 0.0),
            "M3": (6.5, -3.0),
            "M4": (5.0, 3.0),
            "M5": (8.0, 3.0),
            "M6": (12.0, -1.2),
            "M7": (12.0, 2.0),
            "M8": (15.0, 2.0),
            "RB": (15.0, -1.2),
        }
        self._move_named(by_name, coordinates, placements, ground_nets, supply_nets)

    def _place_telescopic_cascode(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        by_name = {component.name.upper(): component for component in graph.components}
        coordinates = {
            "M9": (8.0, -4.0),
            "M1": (6.0, -1.3),
            "M2": (10.0, -1.3),
            "M3": (6.0, 1.2),
            "M4": (10.0, 1.2),
            "M5": (6.0, 3.7),
            "M6": (10.0, 3.7),
            "M7": (6.0, 6.2),
            "M8": (10.0, 6.2),
        }
        self._move_named(by_name, coordinates, placements, ground_nets, supply_nets)

    def _move_named(
        self,
        by_name: dict[str, NormalizedComponent],
        coordinates: dict[str, Point],
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        for name, center in coordinates.items():
            component = by_name.get(name)
            if component is not None:
                self._move_component(component, center, placements, ground_nets, supply_nets)

    def _place_opamp_macro(
        self,
        graph: NormalizedCircuitGraph,
        placements: dict[str, ComponentPlacement],
        *,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        macro = next((component for component in graph.by_kind("X") if len(component.nodes) == 3), None)
        if macro is None:
            return
        self._move_component(macro, (9.0, 0.0), placements, ground_nets, supply_nets)
        noninverting, inverting, output = macro.nodes
        input_index = 0
        feedback_index = 0
        for component in graph.components:
            if component.component_id == macro.component_id or len(component.nodes) != 2:
                continue
            node_set = set(component.nodes)
            if {inverting, output}.issubset(node_set):
                center = (9.0 + feedback_index * 1.8, 2.8)
                feedback_index += 1
                self._move_component(component, center, placements, ground_nets, supply_nets)
            elif inverting in node_set:
                center = (4.5, -1.2 - input_index * 1.5)
                input_index += 1
                self._move_component(component, center, placements, ground_nets, supply_nets)
            elif noninverting in node_set and component.kind not in {"V", "I"}:
                self._move_component(component, (5.5, 1.2), placements, ground_nets, supply_nets)

    def _move_component(
        self,
        component: NormalizedComponent,
        center: Point,
        placements: dict[str, ComponentPlacement],
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> None:
        orientation = placements[component.component_id].orientation
        placements[component.component_id] = ComponentPlacement(
            component_id=component.component_id,
            center=center,
            orientation=orientation,
            pin_positions=self._pin_positions(
                component,
                center,
                orientation,
                ground_nets=ground_nets,
                supply_nets=supply_nets,
            ),
        )

    def _signal_layers(
        self,
        graph: NormalizedCircuitGraph,
        input_nets: list[str],
        excluded_nets: set[str],
    ) -> dict[str, int]:
        known_nets = set(input_nets)
        if not known_nets:
            known_nets = {
                net
                for net, pins in graph.nets.items()
                if net not in excluded_nets and len(pins) == 1
            }
        layers: dict[str, int] = {}
        remaining = {component.component_id: component for component in graph.components}
        layer = 0
        while remaining and layer <= len(graph.components):
            selected = [
                component
                for component in remaining.values()
                if set(component.nodes) & known_nets
            ]
            if not selected:
                component = next(iter(remaining.values()))
                selected = [component]
            for component in selected:
                layers[component.component_id] = layer
                known_nets.update(net for net in component.nodes if net not in excluded_nets)
                remaining.pop(component.component_id, None)
            layer += 1
        return layers

    @staticmethod
    def _preferred_y(component: NormalizedComponent, topology: TopologyRecognition) -> float:
        if component.variant == "pmos":
            return 4.0
        if component.variant in {"nmos", "mos"}:
            return -2.0
        if component.kind in {"V", "I"}:
            return -5.0
        if component.kind in {"C", "L"}:
            return -0.8
        if component.kind == "R":
            return 1.5
        if topology.family == "oscillator":
            return 2.5 * math.sin(len(component.component_id))
        return 0.0

    @staticmethod
    def _source_role(
        component: NormalizedComponent,
        input_nets: list[str],
        supply_nets: list[str],
    ) -> str:
        non_ground = [
            net for net in component.nodes if net.lower() not in ConstrainedAnalogPlacer.GROUND_NAMES
        ]
        if any(net in supply_nets for net in non_ground):
            return "supply"
        if any(net in input_nets for net in non_ground):
            return "input"
        if any(re.search(r"(bias|ref)", net, re.IGNORECASE) for net in non_ground):
            return "bias"
        return "other"

    @staticmethod
    def _orientation(
        component: NormalizedComponent,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> str:
        if component.kind in {"M", "Q", "J", "V", "I", "E", "G"}:
            return "vertical"
        if len(component.nodes) == 2 and set(component.nodes) & set(ground_nets + supply_nets):
            return "vertical"
        return "horizontal"

    @staticmethod
    def _pin_positions(
        component: NormalizedComponent,
        center: Point,
        orientation: str,
        *,
        ground_nets: list[str],
        supply_nets: list[str],
    ) -> dict[int, Point]:
        x, y = center
        count = len(component.pins)
        if component.kind == "M":
            anchors = [(x, y + 1.0), (x - 1.0, y), (x, y - 1.0), (x + 1.0, y - 0.35)]
        elif component.kind in {"Q", "J"}:
            anchors = [(x, y + 1.0), (x - 1.0, y), (x, y - 1.0)]
        elif component.kind == "X" and count == 3:
            anchors = [(x - 1.2, y + 0.5), (x - 1.2, y - 0.5), (x + 1.2, y)]
        elif count == 2:
            if orientation == "boundary":
                anchors = [(x + 0.8, y), (x, y - 0.7)]
                if component.nodes[0] in ground_nets:
                    anchors.reverse()
            elif orientation == "vertical":
                anchors = [(x, y + 1.0), (x, y - 1.0)]
                first, second = component.nodes
                if first in ground_nets or second in supply_nets:
                    anchors.reverse()
            else:
                anchors = [(x - 1.0, y), (x + 1.0, y)]
        elif count == 4:
            anchors = [(x, y + 1.1), (x, y - 1.1), (x - 1.1, y), (x + 1.1, y)]
        else:
            left_count = math.ceil(count / 2)
            anchors = []
            for index in range(count):
                side = -1.2 if index < left_count else 1.2
                local = index if index < left_count else index - left_count
                side_count = left_count if index < left_count else count - left_count
                offset = (side_count - 1) / 2 - local
                anchors.append((x + side, y + offset * 0.65))
        return {index: anchors[index] for index in range(count)}

    @staticmethod
    def _is_input(net: str) -> bool:
        leaf = re.split(r"[:/]", net)[-1].lower()
        return bool(re.match(r"^(vin|inp|inn|input|rf|lo)", leaf))

    @staticmethod
    def _is_output(net: str) -> bool:
        leaf = re.split(r"[:/]", net)[-1].lower()
        return bool(re.match(r"^(v?out|output)", leaf))


class OrthogonalRouter:
    """Connect every terminal to a shared Manhattan route for its net."""

    def route(
        self, graph: NormalizedCircuitGraph, placement: PlacementResult
    ) -> list[NetRoute]:
        routes: list[NetRoute] = []
        ordinary_index = 0
        for net in sorted(graph.nets, key=self._net_sort_key):
            pins = graph.nets[net]
            points = [
                placement.components[pin.component_id].pin_positions[pin.pin_index]
                for pin in pins
            ]
            if net in placement.ground_nets:
                visible_points = [
                    point
                    for pin, point in zip(pins, points)
                    if placement.components[pin.component_id].orientation != "boundary"
                ]
                routes.append(
                    self._terminal_route(
                        net,
                        pins,
                        visible_points,
                        direction=-1,
                        style="ground",
                    )
                )
            elif net in placement.supply_nets:
                routes.append(self._terminal_route(net, pins, points, direction=1, style="supply"))
            else:
                routes.append(self._manhattan_route(net, pins, points, ordinary_index))
                ordinary_index += 1
        return routes

    @staticmethod
    def _terminal_route(
        net: str,
        pins: list[PinRef],
        points: list[Point],
        *,
        direction: int,
        style: str,
    ) -> NetRoute:
        segments = [((x, y), (x, y + direction * 0.65)) for x, y in points]
        label = (
            (points[0][0] + 0.2, points[0][1] + direction * 0.9)
            if points
            else (0.0, 0.0)
        )
        terminals = [(segment[1][0], segment[1][1]) for segment in segments]
        return NetRoute(net, segments, terminals, label, list(pins), style=style)

    @staticmethod
    def _manhattan_route(
        net: str, pins: list[PinRef], points: list[Point], route_index: int
    ) -> NetRoute:
        if len(points) == 1:
            x, y = points[0]
            end = (x + 0.8, y)
            return NetRoute(net, [((x, y), end)], [end], (end[0] + 0.1, end[1] + 0.15), list(pins))

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        offset = ((route_index % 5) - 2) * 0.22
        segments: list[Segment] = []
        junctions: list[Point] = []

        if max(xs) - min(xs) >= max(ys) - min(ys):
            trunk_y = median(ys) + offset
            segments.append(((min(xs), trunk_y), (max(xs), trunk_y)))
            for x, y in points:
                projection = (x, trunk_y)
                segments.append(((x, y), projection))
                junctions.append(projection)
            label = (max(xs) + 0.15, trunk_y + 0.15)
        else:
            trunk_x = median(xs) + offset
            segments.append(((trunk_x, min(ys)), (trunk_x, max(ys))))
            for x, y in points:
                projection = (trunk_x, y)
                segments.append(((x, y), projection))
                junctions.append(projection)
            label = (trunk_x + 0.15, max(ys) + 0.2)
        return NetRoute(net, segments, junctions, label, list(pins))

    @staticmethod
    def _net_sort_key(net: str) -> tuple[int, str]:
        lower = net.lower()
        if lower in ConstrainedAnalogPlacer.GROUND_NAMES:
            return (0, lower)
        if re.search(r"(^|[:/])(vdd|vcc|vdda|vddd)$", lower):
            return (1, lower)
        return (2, lower)


class ConnectivityValidator:
    """Compare normalized connectivity with rendered route membership."""

    def validate(
        self,
        graph: NormalizedCircuitGraph,
        placement: PlacementResult,
        routes: list[NetRoute],
    ) -> ConnectivityValidation:
        expected_components = {component.component_id for component in graph.components}
        rendered_components = set(placement.components)
        expected_pins = {self._pin_key(pin) for pins in graph.nets.values() for pin in pins}
        routed_pins = {self._pin_key(pin) for route in routes for pin in route.routed_pins}
        expected_nets = set(graph.nets)
        routed_nets = {route.net for route in routes}

        missing_components = sorted(expected_components - rendered_components)
        missing_pins = sorted(expected_pins - routed_pins)
        missing_nets = sorted(expected_nets - routed_nets)
        extra_pins = sorted(routed_pins - expected_pins)
        unresolved = bool(
            graph.diagnostics.unresolved_includes or graph.diagnostics.unresolved_instances
        )
        valid = not (missing_components or missing_pins or missing_nets or extra_pins or unresolved)
        return ConnectivityValidation(
            status="VALID" if valid else "INVALID",
            scope="structural connectivity only; not simulation, compliance, robustness, or scientific eligibility",
            expected_component_count=len(expected_components),
            rendered_component_count=len(rendered_components),
            expected_pin_count=len(expected_pins),
            routed_pin_count=len(routed_pins),
            expected_net_count=len(expected_nets),
            routed_net_count=len(routed_nets),
            missing_components=missing_components,
            missing_pins=missing_pins,
            missing_nets=missing_nets,
            extra_pins=extra_pins,
            unresolved_includes=list(graph.diagnostics.unresolved_includes),
            unresolved_instances=list(graph.diagnostics.unresolved_instances),
        )

    @staticmethod
    def _pin_key(pin: PinRef) -> str:
        return f"{pin.component_id}[{pin.pin_index}:{pin.pin_name}]={pin.net}"


class ManuscriptTopologyRenderer:
    """Render a compact functional view instead of a crowded device schematic."""

    STAGES: dict[str, list[str]] = {
        "amplifier": ["Input network", "Gain stage", "Output load"],
        "opamp": ["Differential input", "Gain stage", "Output"],
        "differential": ["Differential pair", "Active / resistive load", "Output"],
        "inverter": ["Input", "Inverting stage", "Output load"],
        "current_source": ["Bias", "MOS current source", "Output branch"],
        "current_mirror": ["Reference branch", "Mirror core", "Output branch"],
        "rc_network": ["Input", "Passive RC network", "Output"],
        "opamp_macro": ["Input network", "Opamp", "Feedback network"],
        "oscillator": ["Frequency network", "Amplifying element", "Output"],
        "gilbert_mixer": ["RF transconductor", "LO switching quad", "Differential loads"],
        "two_stage_opamp": ["Differential stage", "Active load", "Second gain stage", "Output"],
        "telescopic_cascode": ["Input pair", "Cascode stack", "Active loads", "Differential outputs"],
        "hierarchical_macro": ["Inputs", "Hierarchical circuit", "Outputs"],
        "generic": ["Inputs", "Circuit", "Outputs"],
    }

    def render(
        self,
        graph: NormalizedCircuitGraph,
        placement: PlacementResult,
        routes: list[NetRoute],
        svg_path: Path,
        pdf_path: Path,
        png_path: Path,
        title: str,
        topology: TopologyRecognition,
    ) -> None:
        del routes
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        stages = self.STAGES.get(topology.family, self.STAGES["generic"])
        fig, ax = plt.subplots(figsize=(8.8, 3.0 if len(stages) <= 3 else 3.4))
        ax.set_xlim(-1.8, len(stages) * 2.7 + 0.9)
        ax.set_ylim(-2.0, 2.0)
        ax.axis("off")

        centers = [0.5 + index * 2.7 for index in range(len(stages))]
        for index, (center, label) in enumerate(zip(centers, stages)):
            box = Rectangle(
                (center - 0.9, -0.55),
                1.8,
                1.1,
                facecolor="#f5f1e8",
                edgecolor="#173f46",
                linewidth=1.5,
                zorder=2,
            )
            ax.add_patch(box)
            ax.text(center, 0.0, label, ha="center", va="center", fontsize=8.5, color="#17292d")
            if index:
                ax.annotate(
                    "",
                    xy=(center - 0.9, 0.0),
                    xytext=(centers[index - 1] + 0.9, 0.0),
                    arrowprops={"arrowstyle": "->", "color": "#173f46", "linewidth": 1.35},
                )

        inputs = self._primary_inputs(graph, placement, topology)
        outputs = placement.output_nets or ["output"]
        self._draw_ports(ax, inputs[:4], centers[0] - 0.9, side="left")
        self._draw_ports(ax, outputs[:2], centers[-1] + 0.9, side="right")

        if topology.family == "oscillator":
            ax.annotate(
                "feedback",
                xy=(centers[0], -0.55),
                xytext=(centers[-1], -0.55),
                ha="center",
                va="top",
                fontsize=7,
                color="#0b6872",
                arrowprops={
                    "arrowstyle": "->",
                    "connectionstyle": "arc3,rad=-0.26",
                    "color": "#0b6872",
                    "linewidth": 1.2,
                },
            )

        ax.text(
            sum(centers) / len(centers),
            -1.78,
            "Topological abstraction - component-level schematic in appendix",
            ha="center",
            va="center",
            fontsize=7,
            color="#526166",
        )
        if title:
            ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
        fig.savefig(svg_path, format="svg", bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        fig.savefig(pdf_path, format="pdf", bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        fig.savefig(png_path, format="png", dpi=200, bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        plt.close(fig)

    @staticmethod
    def _primary_inputs(
        graph: NormalizedCircuitGraph,
        placement: PlacementResult,
        topology: TopologyRecognition,
    ) -> list[str]:
        if topology.family == "oscillator":
            return ["autonomous"]
        excluded = set(placement.supply_nets + placement.ground_nets)
        primary: list[str] = []
        for component in graph.components:
            if component.kind not in {"V", "I"} or not component.nodes:
                continue
            name = component.name.lower()
            if re.search(r"(dd|cc|ss|ee|bias|ref)", name):
                continue
            signal = next((net for net in component.nodes if net not in excluded), None)
            if signal and re.search(r"(bias|ref|vdd|vcc|vss|vee)", signal, re.IGNORECASE):
                continue
            if signal and signal not in primary:
                primary.append(signal)
        if topology.family == "current_mirror" and not primary:
            return ["Iref"]
        return primary or placement.input_nets or ["input"]

    @staticmethod
    def _draw_ports(ax: Axes, nets: list[str], x: float, *, side: str) -> None:
        offsets = [0.0] if len(nets) == 1 else [0.55 - index * 1.1 / (len(nets) - 1) for index in range(len(nets))]
        direction = -1 if side == "left" else 1
        for net, y in zip(nets, offsets):
            outer_x = x + direction * 1.0
            ax.plot([x, outer_x], [y, y], color="#173f46", linewidth=1.25)
            ax.text(
                outer_x + direction * 0.08,
                y + 0.08,
                net,
                ha="right" if side == "left" else "left",
                va="bottom",
                fontsize=7.5,
                color="#0b6872",
            )


class VectorSchematicRenderer:
    """Draw components and routed nets to SVG and PDF using Matplotlib."""

    def __init__(
        self,
        *,
        show_device_parameters: bool = False,
        use_net_labels: bool = False,
    ) -> None:
        self.show_device_parameters = show_device_parameters
        self.use_net_labels = use_net_labels

    def render(
        self,
        graph: NormalizedCircuitGraph,
        placement: PlacementResult,
        routes: list[NetRoute],
        svg_path: Path,
        pdf_path: Path,
        png_path: Path,
        title: str,
        topology: TopologyRecognition,
    ) -> None:
        del topology
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=self._figure_size(placement))
        ax.set_aspect("equal")
        ax.axis("off")

        dense = self.use_net_labels and len(graph.components) >= 8
        for route in routes:
            if dense and route.style == "wire" and self._should_label_route(route, placement):
                self._draw_labeled_route(ax, route, placement)
            else:
                self._draw_route(ax, route)
        for component in graph.components:
            self._draw_component(ax, component, placement.components[component.component_id])

        if title:
            ax.set_title(title, fontsize=11, fontweight="bold", pad=12)
        ax.autoscale_view()
        ax.margins(0.12)
        fig.savefig(svg_path, format="svg", bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        fig.savefig(pdf_path, format="pdf", bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        fig.savefig(png_path, format="png", dpi=200, bbox_inches="tight", metadata={"Creator": "Spec2Testbench"})
        plt.close(fig)

    @staticmethod
    def _should_label_route(route: NetRoute, placement: PlacementResult) -> bool:
        points = [
            placement.components[pin.component_id].pin_positions[pin.pin_index]
            for pin in route.routed_pins
        ]
        if not points:
            return False
        span = (max(x for x, _ in points) - min(x for x, _ in points)) + (
            max(y for _, y in points) - min(y for _, y in points)
        )
        return len(points) >= 3 or span > 4.5

    @staticmethod
    def _draw_labeled_route(
        ax: Axes,
        route: NetRoute,
        placement: PlacementResult,
    ) -> None:
        label = re.split(r"[:/]", route.net)[-1]
        for pin in route.routed_pins:
            component = placement.components[pin.component_id]
            x, y = component.pin_positions[pin.pin_index]
            cx, cy = component.center
            dx, dy = x - cx, y - cy
            if abs(dx) >= abs(dy):
                direction = 1 if dx >= 0 else -1
                end = (x + direction * 0.45, y)
                ha = "left" if direction > 0 else "right"
                text = (end[0] + direction * 0.06, end[1] + 0.08)
            else:
                direction = 1 if dy >= 0 else -1
                end = (x, y + direction * 0.45)
                ha = "center"
                text = (end[0], end[1] + direction * 0.08)
            ax.plot([x, end[0]], [y, end[1]], color="#263238", linewidth=1.2, zorder=1)
            ax.text(
                text[0],
                text[1],
                label,
                fontsize=5.5,
                color="#0b5d6b",
                ha=ha,
                va="bottom" if direction > 0 else "top",
                zorder=4,
            )

    def _draw_route(self, ax: Axes, route: NetRoute) -> None:
        for (x1, y1), (x2, y2) in route.segments:
            ax.plot([x1, x2], [y1, y2], color="#263238", linewidth=1.25, zorder=1)
        if route.style == "ground":
            for x, y in route.junctions:
                self._draw_ground(ax, (x, y))
        elif route.style == "supply":
            for x, y in route.junctions:
                ax.plot([x - 0.18, x, x + 0.18], [y - 0.18, y, y - 0.18], color="#263238", linewidth=1.1)
        else:
            if len(route.routed_pins) > 2:
                for x, y in set(route.junctions):
                    ax.add_patch(Circle((x, y), 0.07, color="#263238", zorder=2))
        net_leaf = re.split(r"[:/]", route.net)[-1]
        if route.style == "wire" and (
            re.match(r"^(v?out|output)", net_leaf, re.IGNORECASE)
            or len(route.routed_pins) == 1
        ):
            ax.text(
                route.label_position[0],
                route.label_position[1],
                route.net,
                fontsize=6.5,
                color="#0b5d6b",
                ha="left",
                va="bottom",
                zorder=4,
            )

    def _draw_component(
        self, ax: Axes, component: NormalizedComponent, placement: ComponentPlacement
    ) -> None:
        kind = component.kind
        if kind == "R":
            self._draw_resistor(ax, placement)
        elif kind == "C":
            self._draw_capacitor(ax, placement)
        elif kind == "L":
            self._draw_inductor(ax, placement)
        elif kind in {"V", "I"}:
            self._draw_source(ax, placement, kind, component)
        elif kind == "M":
            self._draw_mos(ax, placement, component.variant or "mos")
        elif kind == "D":
            self._draw_diode(ax, placement)
        elif kind == "X" and len(component.pins) == 3:
            self._draw_opamp(ax, placement)
        elif kind in {"E", "G"}:
            self._draw_diamond(ax, placement)
        else:
            self._draw_block(ax, placement, kind)

        x, y = placement.center
        label = component.name
        detail = component.value or component.model or ""
        if component.kind == "M" and not self.show_device_parameters:
            detail = ""
        if component.kind == "V" and placement.orientation == "boundary":
            return
        if component.kind in {"V", "I"}:
            ax.text(x + 0.72, y + 0.08, label, fontsize=7.5, fontweight="bold", ha="left", va="center", zorder=5)
            if detail:
                ax.text(x + 0.72, y - 0.22, detail, fontsize=5.7, ha="left", va="center", color="#455a64", zorder=5)
        else:
            ax.text(x, y - 1.35, label, fontsize=7.5, fontweight="bold", ha="center", va="top", zorder=5)
            if detail:
                ax.text(x, y - 1.62, detail, fontsize=5.7, ha="center", va="top", color="#455a64", zorder=5)

    @staticmethod
    def _draw_resistor(ax: Axes, placement: ComponentPlacement) -> None:
        first, second = placement.pin_positions[0], placement.pin_positions[1]
        if placement.orientation == "vertical":
            x, y = placement.center
            ys = [y + 0.65 - index * 0.1625 for index in range(9)]
            xs = [x] + [x + (0.22 if index % 2 else -0.22) for index in range(1, 8)] + [x]
        else:
            x, y = placement.center
            xs = [x - 0.65 + index * 0.1625 for index in range(9)]
            ys = [y] + [y + (0.22 if index % 2 else -0.22) for index in range(1, 8)] + [y]
        ax.plot([first[0], xs[0]], [first[1], ys[0]], color="#111", linewidth=1.25, zorder=3)
        ax.plot(xs, ys, color="#111", linewidth=1.25, zorder=3)
        ax.plot([xs[-1], second[0]], [ys[-1], second[1]], color="#111", linewidth=1.25, zorder=3)

    @staticmethod
    def _draw_capacitor(ax: Axes, placement: ComponentPlacement) -> None:
        first, second = placement.pin_positions[0], placement.pin_positions[1]
        x, y = placement.center
        if placement.orientation == "vertical":
            ax.plot([x - 0.42, x + 0.42], [y + 0.13, y + 0.13], color="#111", linewidth=1.5, zorder=3)
            ax.plot([x - 0.42, x + 0.42], [y - 0.13, y - 0.13], color="#111", linewidth=1.5, zorder=3)
            ax.plot([first[0], x], [first[1], y + 0.13], color="#111", linewidth=1.2, zorder=3)
            ax.plot([x, second[0]], [y - 0.13, second[1]], color="#111", linewidth=1.2, zorder=3)
        else:
            ax.plot([x - 0.13, x - 0.13], [y - 0.42, y + 0.42], color="#111", linewidth=1.5, zorder=3)
            ax.plot([x + 0.13, x + 0.13], [y - 0.42, y + 0.42], color="#111", linewidth=1.5, zorder=3)
            ax.plot([first[0], x - 0.13], [first[1], y], color="#111", linewidth=1.2, zorder=3)
            ax.plot([x + 0.13, second[0]], [y, second[1]], color="#111", linewidth=1.2, zorder=3)

    @staticmethod
    def _draw_inductor(ax: Axes, placement: ComponentPlacement) -> None:
        first, second = placement.pin_positions[0], placement.pin_positions[1]
        x, y = placement.center
        if placement.orientation == "vertical":
            theta = [math.pi * index / 20 for index in range(41)]
            xs = [x + 0.22 * math.sin(value * 4) for value in theta]
            ys = [y + 0.65 - 1.3 * index / 40 for index in range(41)]
        else:
            theta = [math.pi * index / 20 for index in range(41)]
            xs = [x - 0.65 + 1.3 * index / 40 for index in range(41)]
            ys = [y + 0.22 * abs(math.sin(value * 4)) for value in theta]
        ax.plot([first[0], xs[0]], [first[1], ys[0]], color="#111", linewidth=1.2, zorder=3)
        ax.plot(xs, ys, color="#111", linewidth=1.2, zorder=3)
        ax.plot([xs[-1], second[0]], [ys[-1], second[1]], color="#111", linewidth=1.2, zorder=3)

    @staticmethod
    def _draw_source(
        ax: Axes,
        placement: ComponentPlacement,
        kind: str,
        component: NormalizedComponent,
    ) -> None:
        x, y = placement.center
        if kind == "V" and placement.orientation == "boundary":
            signal_index = next(
                (
                    pin.pin_index
                    for pin in component.pins
                    if pin.net.lower() not in ConstrainedAnalogPlacer.GROUND_NAMES
                ),
                0,
            )
            signal = placement.pin_positions[signal_index]
            ax.plot([x, signal[0]], [y, signal[1]], color="#111", linewidth=1.2, zorder=3)
            ax.add_patch(Circle(signal, 0.07, color="#111", zorder=4))
            value = component.value or ""
            signal_name = component.pins[signal_index].net
            reference_nets = [
                pin.net for pin in component.pins if pin.pin_index != signal_index
            ]
            reference = reference_nets[0] if reference_nets else ""
            reference_suffix = f" (ref {reference})" if reference not in {"", "0"} else ""
            text = (
                f"{signal_name} = {value}{reference_suffix}"
                if value
                else f"{signal_name}{reference_suffix}"
            )
            ax.text(x - 0.15, y, text, fontsize=7.2, fontweight="bold", ha="right", va="center", zorder=5)
            return
        ax.add_patch(Circle((x, y), 0.52, fill=False, linewidth=1.3, edgecolor="#111", zorder=3))
        for index, point in placement.pin_positions.items():
            edge_y = y + (0.52 if index == 0 else -0.52)
            ax.plot([point[0], x], [point[1], edge_y], color="#111", linewidth=1.2, zorder=3)
        if kind == "V":
            ax.text(x, y + 0.18, "+", fontsize=9, ha="center", va="center", zorder=4)
            ax.text(x, y - 0.2, "-", fontsize=10, ha="center", va="center", zorder=4)
        else:
            ax.annotate("", xy=(x, y - 0.3), xytext=(x, y + 0.3), arrowprops={"arrowstyle": "->", "lw": 1.1})

    @staticmethod
    def _draw_mos(ax: Axes, placement: ComponentPlacement, variant: str) -> None:
        x, y = placement.center
        pins = placement.pin_positions
        ax.plot([x - 0.25, x - 0.25], [y - 0.55, y + 0.55], color="#111", linewidth=1.5, zorder=3)
        ax.plot([x + 0.12, x + 0.12], [y - 0.48, y + 0.48], color="#111", linewidth=1.5, zorder=3)
        ax.plot([pins[0][0], x + 0.12], [pins[0][1], y + 0.48], color="#111", linewidth=1.2, zorder=3)
        ax.plot([pins[1][0], x - 0.25], [pins[1][1], y], color="#111", linewidth=1.2, zorder=3)
        ax.plot([pins[2][0], x + 0.12], [pins[2][1], y - 0.48], color="#111", linewidth=1.2, zorder=3)
        if 3 in pins:
            ax.plot([pins[3][0], x + 0.12], [pins[3][1], y - 0.2], color="#111", linewidth=1.0, zorder=3)
        if variant == "pmos":
            ax.add_patch(Circle((x - 0.35, y), 0.09, fill=False, linewidth=1.1, edgecolor="#111", zorder=4))
        ax.text(x + 0.38, y + 0.35, "P" if variant == "pmos" else "N", fontsize=6, color="#455a64")

    @staticmethod
    def _draw_diode(ax: Axes, placement: ComponentPlacement) -> None:
        x, y = placement.center
        first, second = placement.pin_positions[0], placement.pin_positions[1]
        if placement.orientation == "vertical":
            triangle = Polygon([(x - 0.35, y + 0.25), (x + 0.35, y + 0.25), (x, y - 0.2)], fill=False, edgecolor="#111")
            ax.add_patch(triangle)
            ax.plot([x - 0.38, x + 0.38], [y - 0.25, y - 0.25], color="#111", linewidth=1.4)
        else:
            triangle = Polygon([(x - 0.25, y - 0.35), (x - 0.25, y + 0.35), (x + 0.2, y)], fill=False, edgecolor="#111")
            ax.add_patch(triangle)
            ax.plot([x + 0.25, x + 0.25], [y - 0.38, y + 0.38], color="#111", linewidth=1.4)
        ax.plot([first[0], x], [first[1], y], color="#111", linewidth=1.2)
        ax.plot([x, second[0]], [y, second[1]], color="#111", linewidth=1.2)

    @staticmethod
    def _draw_opamp(ax: Axes, placement: ComponentPlacement) -> None:
        x, y = placement.center
        triangle = Polygon([(x - 0.75, y - 0.8), (x - 0.75, y + 0.8), (x + 0.75, y)], fill=False, edgecolor="#111", linewidth=1.3, zorder=3)
        ax.add_patch(triangle)
        for index, point in placement.pin_positions.items():
            target = (x - 0.75, y + (0.4 if index == 0 else -0.4)) if index < 2 else (x + 0.75, y)
            ax.plot([point[0], target[0]], [point[1], target[1]], color="#111", linewidth=1.2, zorder=3)
        ax.text(x - 0.52, y + 0.35, "+", fontsize=8)
        ax.text(x - 0.52, y - 0.45, "-", fontsize=8)

    @staticmethod
    def _draw_diamond(ax: Axes, placement: ComponentPlacement) -> None:
        x, y = placement.center
        ax.add_patch(Polygon([(x, y + 0.7), (x + 0.55, y), (x, y - 0.7), (x - 0.55, y)], fill=False, edgecolor="#111", linewidth=1.3, zorder=3))
        for point in placement.pin_positions.values():
            ax.plot([point[0], x], [point[1], y], color="#111", linewidth=1.0, zorder=3)

    @staticmethod
    def _draw_block(ax: Axes, placement: ComponentPlacement, kind: str) -> None:
        x, y = placement.center
        ax.add_patch(Rectangle((x - 0.65, y - 0.65), 1.3, 1.3, fill=False, edgecolor="#111", linewidth=1.3, zorder=3))
        ax.text(x, y, kind, fontsize=8, ha="center", va="center", zorder=4)
        for point in placement.pin_positions.values():
            edge_x = x - 0.65 if point[0] < x else x + 0.65
            edge_y = min(max(point[1], y - 0.55), y + 0.55)
            ax.plot([point[0], edge_x], [point[1], edge_y], color="#111", linewidth=1.0, zorder=3)

    @staticmethod
    def _draw_ground(ax: Axes, point: Point) -> None:
        x, y = point
        ax.plot([x - 0.32, x + 0.32], [y, y], color="#263238", linewidth=1.15)
        ax.plot([x - 0.22, x + 0.22], [y - 0.12, y - 0.12], color="#263238", linewidth=1.05)
        ax.plot([x - 0.1, x + 0.1], [y - 0.24, y - 0.24], color="#263238", linewidth=1.0)

    @staticmethod
    def _figure_size(placement: PlacementResult) -> tuple[float, float]:
        if not placement.components:
            return (7.0, 4.0)
        xs = [item.center[0] for item in placement.components.values()]
        ys = [item.center[1] for item in placement.components.values()]
        width = min(16.0, max(7.0, (max(xs) - min(xs) + 5.0) * 0.65))
        height = min(12.0, max(4.5, (max(ys) - min(ys) + 5.0) * 0.65))
        return (width, height)


class PublicationSchematicGenerator:
    """Orchestrate parsing, recognition, placement, routing, and evidence."""

    def __init__(self, *, view: str = "manuscript", include_title: bool = False) -> None:
        if view not in {"manuscript", "appendix"}:
            raise ValueError("view must be 'manuscript' or 'appendix'")
        self.view = view
        self.include_title = include_title
        self.parser = HierarchicalNetlistParser()
        self.recognizer = AnalogTopologyRecognizer()
        self.placer = ConstrainedAnalogPlacer()
        self.router = OrthogonalRouter()
        self.validator = ConnectivityValidator()
        self.renderer = (
            ManuscriptTopologyRenderer()
            if view == "manuscript"
            else VectorSchematicRenderer(show_device_parameters=True, use_net_labels=True)
        )

    def generate_from_path(
        self,
        netlist_path: Path,
        output: Path,
        report_path: Path | None = None,
    ) -> PublicationSchematicResult:
        graph = self.parser.parse_path(netlist_path, flatten_subcircuits=False)
        return self._generate(
            graph,
            output,
            report_path=report_path,
            source_name=str(netlist_path),
            title=netlist_path.stem if self.include_title else "",
        )

    def generate_from_text(
        self,
        netlist: str,
        output: Path,
        *,
        base_dir: Path | None = None,
        source_name: str | None = None,
        report_path: Path | None = None,
    ) -> PublicationSchematicResult:
        graph = self.parser.parse_text(
            netlist,
            base_dir=base_dir,
            source_name=source_name,
            flatten_subcircuits=False,
        )
        return self._generate(
            graph,
            output,
            report_path=report_path,
            source_name=source_name,
            title=(Path(source_name).stem if source_name else "Circuit schematic") if self.include_title else "",
        )

    def _generate(
        self,
        graph: NormalizedCircuitGraph,
        output: Path,
        *,
        report_path: Path | None,
        source_name: str | None,
        title: str,
    ) -> PublicationSchematicResult:
        if not graph.components:
            raise ValueError("No components were found after include/subcircuit resolution")
        svg_path, pdf_path, png_path = self._output_paths(output)
        report_path = report_path or output.with_suffix(".json")
        topology = self.recognizer.recognize(graph, source_name=source_name)
        topology.circuit_id = Path(source_name).stem if source_name else None
        placement = self.placer.place(graph, topology)
        routes = self.router.route(graph, placement)
        validation = self.validator.validate(graph, placement, routes)
        self.renderer.render(
            graph,
            placement,
            routes,
            svg_path,
            pdf_path,
            png_path,
            title,
            topology,
        )

        report = {
            "framework": "Spec2Testbench",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": graph.diagnostics.source_file,
            "validation": asdict(validation),
            "topology": asdict(topology),
            "graph": {
                "component_count": len(graph.components),
                "pin_count": graph.pin_count,
                "net_count": len(graph.nets),
                "components": [
                    {
                        "component_id": component.component_id,
                        "name": component.name,
                        "kind": component.kind,
                        "variant": component.variant,
                        "model": component.model,
                        "value": component.value,
                        "pins": [asdict(pin) for pin in component.pins],
                    }
                    for component in graph.components
                ],
            },
            "hierarchy": asdict(graph.diagnostics),
            "routing": {
                "style": "orthogonal Manhattan routing",
                "route_count": len(routes),
                "routes": [
                    {
                        "net": route.net,
                        "style": route.style,
                        "segment_count": len(route.segments),
                        "routed_pin_count": len(route.routed_pins),
                    }
                    for route in routes
                ],
            },
            "rendering": {
                "view": self.view,
                "visual_scope": (
                    "topological abstraction; not a one-to-one component drawing"
                    if self.view == "manuscript"
                    else "component-level connectivity; long nets may use repeated net labels"
                ),
                "source_representation": (
                    "ground-referenced supplies and external input voltage sources are "
                    "labeled boundary ports; non-ground references are explicit"
                ),
                "abstracted_voltage_sources": [
                    component.component_id
                    for component in graph.by_kind("V")
                    if "0" in component.nodes
                    or component.name.lower().startswith("vin")
                ],
            },
            "outputs": {"svg": str(svg_path), "pdf": str(pdf_path), "png": str(png_path)},
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        return PublicationSchematicResult(
            svg_path=str(svg_path),
            pdf_path=str(pdf_path),
            png_path=str(png_path),
            report_path=str(report_path),
            validation=validation,
            topology=topology,
        )

    @staticmethod
    def _output_paths(output: Path) -> tuple[Path, Path, Path]:
        suffix = output.suffix.lower()
        if suffix in {".svg", ".pdf"}:
            stem = output.with_suffix("")
        else:
            stem = output
        return stem.with_suffix(".svg"), stem.with_suffix(".pdf"), stem.with_suffix(".png")
