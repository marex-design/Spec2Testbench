import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class OscillatorRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Opamp().label("Oscillator Core")
        d += elm.Line().right().label("Vout", loc="right")

        d.push()
        d += elm.Line().down().length(2)
        d += elm.Resistor().left().label("Feedback")
        d += elm.Capacitor().left().label("C")
        d += elm.Line().up().length(2)
        d.pop()

        d.save(output_path, dpi=300)
        return output_path