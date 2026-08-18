import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class AmplifierRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.NFet().label("Amplifier Core")
        d += elm.Line().right().label("Vout", loc="right")
        d += elm.Line().at((-2, 0)).left().label("Vin", loc="left")
        d += elm.Resistor().at((0, 2)).up().label("Load")
        d += elm.Ground().at((0, -2))

        d.save(output_path, dpi=300)
        return output_path