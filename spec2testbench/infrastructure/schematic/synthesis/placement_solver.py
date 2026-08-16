from dataclasses import dataclass


@dataclass
class Placement:
    symbols: dict[str, tuple[float, float]]
    nets: dict[str, tuple[float, float]]


class PlacementSolver:
    def solve(self, topology, graph, constraints) -> Placement:
        family = topology.family

        if family == "rc_filter":
            return self._place_rc(graph)

        if family == "current_mirror":
            return self._place_current_mirror(graph)

        if family == "differential":
            return self._place_differential(graph)

        if family == "amplifier":
            return self._place_amplifier(graph)

        if family == "oscillator":
            return self._place_oscillator(graph)

        if family == "diode":
            return self._place_diode(graph)

        if family == "opamp_macro":
            return self._place_opamp_macro(graph)

        if family == "behavioral":
            return self._place_behavioral(graph)

        return self._place_generic(graph)

    def _first(self, graph, kind):
        items = graph.by_kind(kind)
        return items[0].name if items else None

    def _place_rc(self, graph):
        r = self._first(graph, "R") or "R1"
        c = self._first(graph, "C") or "C1"
        v = self._first(graph, "V") or "Vin"

        return Placement(
            symbols={
                v: (-6, 0),
                r: (-2, 0),
                c: (2, -2),
            },
            nets={
                "in": (-4, 0),
                "out": (2, 0),
                "0": (2, -4),
            },
        )

    def _place_current_mirror(self, graph):
        mos = graph.by_kind("M")
        i = self._first(graph, "I") or "Iref"

        return Placement(
            symbols={
                i: (-4, 2),
                mos[0].name if len(mos) > 0 else "M1": (-1, 0),
                mos[1].name if len(mos) > 1 else "M2": (3, 0),
            },
            nets={
                "ref": (-2, 0),
                "out": (4, 1),
                "0": (0, -3),
            },
        )

    def _place_differential(self, graph):
        mos = graph.by_kind("M")
        resistors = graph.by_kind("R")
        current = self._first(graph, "I") or "Itail"

        return Placement(
            symbols={
                mos[0].name if len(mos) > 0 else "M1": (-2, 0),
                mos[1].name if len(mos) > 1 else "M2": (2, 0),
                resistors[0].name if len(resistors) > 0 else "RD1": (-2, 3),
                resistors[1].name if len(resistors) > 1 else "RD2": (2, 3),
                current: (0, -3),
            },
            nets={
                "in_p": (-5, 0),
                "in_n": (5, 0),
                "out_p": (-2, 2),
                "out_n": (2, 2),
                "tail": (0, -1.5),
                "0": (0, -5),
                "vdd": (0, 5),
            },
        )

    def _place_amplifier(self, graph):
        m = self._first(graph, "M") or "M1"
        r = self._first(graph, "R") or "Load"

        return Placement(
            symbols={
                m: (0, 0),
                r: (0, 3),
            },
            nets={
                "in": (-4, 0),
                "out": (4, 0),
                "vdd": (0, 5),
                "0": (0, -3),
            },
        )

    def _place_oscillator(self, graph):
        return Placement(
            symbols={
                "CORE": (0, 0),
                "FEEDBACK": (0, -3),
            },
            nets={
                "out": (5, 0),
                "fb": (-3, -3),
            },
        )

    def _place_diode(self, graph):
        d = self._first(graph, "D") or "D1"
        r = self._first(graph, "R") or "Rload"
        c = self._first(graph, "C") or "C"

        return Placement(
            symbols={
                d: (-1, 0),
                r: (2, -2),
                c: (2, -1),
            },
            nets={
                "in": (-4, 0),
                "out": (2, 0),
                "0": (2, -4),
            },
        )

    def _place_opamp_macro(self, graph):
        return Placement(
            symbols={
                "OPAMP": (0, 0),
            },
            nets={
                "inp": (-4, 1),
                "inn": (-4, -1),
                "out": (4, 0),
            },
        )

    def _place_behavioral(self, graph):
        return Placement(
            symbols={
                "BLOCK": (0, 0),
            },
            nets={
                "in": (-4, 0),
                "out": (4, 0),
            },
        )

    def _place_generic(self, graph):
        symbols = {}
        nets = {}

        for idx, comp in enumerate(graph.components):
            symbols[comp.name] = ((idx % 5) * 3, -(idx // 5) * 3)

        for idx, net in enumerate(graph.nets):
            nets[net] = ((idx % 5) * 3, -6 - (idx // 5) * 2)

        return Placement(symbols=symbols, nets=nets)