from pathlib import Path
import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.graph.networkx_drawer import draw_networkx_graph


class RenderEngine:
    def render(self, topology, graph, placement, routes, output_path: str) -> str:
        family = topology.family

        if family == "rc_filter":
            return self._render_rc_filter(graph, output_path)

        if family == "current_mirror":
            return self._render_current_mirror(graph, output_path)

        if family == "differential":
            return self._render_differential(graph, output_path)

        if family == "amplifier":
            return self._render_amplifier(graph, output_path)

        if family == "oscillator":
            return self._render_oscillator(graph, output_path)

        if family == "diode":
            return self._render_diode(graph, output_path)

        if family == "opamp_macro":
            return self._render_opamp_macro(graph, output_path)

        if family == "behavioral":
            return self._render_behavioral(graph, output_path)

        raw_netlist = getattr(graph, "raw_netlist", "")
        return draw_networkx_graph(raw_netlist, output_path)

    def _save(self, d, output_path):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        d.save(str(out), dpi=300)
        return str(out)

    def _render_rc_filter(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.SourceSin().up().label("Vin")
        d += elm.Line().right()
        d += elm.Resistor().right().label("R1", loc="top")
        d += elm.Dot().label("Vout", loc="right", ofst=(0.3, 0.2))

        d.push()
        d += elm.Capacitor().down().label("C1", loc="top")
        d += elm.Ground()
        d.pop()

        return self._save(d, output_path)

    def _render_current_mirror(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.SourceI().down().label("Iref")
        d += elm.Dot().label("ref", loc="left")
        d += elm.Line().right()
        d += elm.NFet().label("M1")
        d += elm.Line().right()
        d += elm.NFet().label("M2")
        d += elm.Line().up().label("out", loc="right")
        d += elm.Ground().at((0, -3))

        return self._save(d, output_path)

    def _render_differential(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.NFet().at((-2, 0)).label("M1")
        d += elm.NFet().at((2, 0)).label("M2")

        d += elm.Line().at((-2, -1)).to((0, -2))
        d += elm.Line().at((2, -1)).to((0, -2))

        d += elm.SourceI().at((0, -2)).down().label("Itail")
        d += elm.Ground()

        d += elm.Resistor().at((-2, 2)).up().label("RD1")
        d += elm.Resistor().at((2, 2)).up().label("RD2")

        d += elm.Label().at((-5, 0)).label("Vin+")
        d += elm.Label().at((5, 0)).label("Vin-")
        d += elm.Label().at((-2, 3.5)).label("Vout+")
        d += elm.Label().at((2, 3.5)).label("Vout-")

        return self._save(d, output_path)

    def _render_amplifier(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Label().at((-4, 0)).label("Vin")
        d += elm.Line().at((-3, 0)).right().length(2)
        d += elm.NFet().label("Amplifier Core")
        d += elm.Line().right().length(3).label("Vout", loc="right")
        d += elm.Resistor().at((0, 3)).up().label("Load")
        d += elm.Ground().at((0, -3))

        return self._save(d, output_path)

    def _render_oscillator(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Opamp().label("Oscillator Core")
        d += elm.Line().right().length(3).label("Vout", loc="right")

        d.push()
        d += elm.Line().down().length(2)
        d += elm.Resistor().left().label("Feedback")
        d += elm.Capacitor().left().label("C")
        d += elm.Line().up().length(2)
        d.pop()

        return self._save(d, output_path)

    def _render_diode(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.SourceSin().up().label("Vin")
        d += elm.Line().right()
        d += elm.Diode().right().label("D1", loc="top")
        d += elm.Dot().label("Vout", loc="right")

        d.push()
        d += elm.Capacitor().down().label("C")
        d += elm.Resistor().down().label("Rload")
        d += elm.Ground()
        d.pop()

        return self._save(d, output_path)

    def _render_opamp_macro(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Opamp().label("Op-Amp Macro")
        d += elm.Line().right().length(3).label("Vout", loc="right")
        d += elm.Label().at((-2, 0.8)).label("Vin+")
        d += elm.Label().at((-2, -0.8)).label("Vin-")

        return self._save(d, output_path)

    def _render_behavioral(self, graph, output_path):
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Line().right()
        d += elm.RBox().right().label("Behavioral Block")
        d += elm.Line().right().label("Output", loc="right")
        d += elm.Label().at((-1, 0)).label("Input")

        return self._save(d, output_path)