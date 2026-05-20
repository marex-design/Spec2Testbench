import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class CurrentMirrorRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
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

        d.save(output_path, dpi=300)
        return output_path