import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class BehavioralRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.RBox().label("Behavioral Block")
        d += elm.Line().left().label("Input", loc="left")
        d += elm.Line().right().at((2, 0)).label("Output", loc="right")

        d.save(output_path, dpi=300)
        return output_path