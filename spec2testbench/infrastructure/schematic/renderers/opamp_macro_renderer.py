import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer


class OpampMacroRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        d += elm.Opamp().label("Op-Amp Macro")
        d += elm.Line().right().label("Vout", loc="right")
        d += elm.Label().at((-2, 0.8)).label("Vin+")
        d += elm.Label().at((-2, -0.8)).label("Vin-")

        d.save(output_path, dpi=300)
        return output_path