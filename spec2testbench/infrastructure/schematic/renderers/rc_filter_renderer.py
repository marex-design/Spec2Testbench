import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class RCFilterRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.SourceSin().up().label("Vin")
        d += elm.Line().right()
        d += elm.Resistor().right().label("R1", loc="top")

        d += elm.Dot().label(
            "Vout",
            loc="right",
            ofst=(0.3, 0.2),
        )

        d.push()
        d += elm.Capacitor().down().label("C1", loc="top")
        d += elm.Ground()
        d.pop()

        d.save(output_path, dpi=300)

        return output_path