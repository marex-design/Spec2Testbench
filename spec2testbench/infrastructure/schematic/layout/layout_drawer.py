import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.layout.placement_engine import PlacementEngine


class LayoutDrawer:

    def draw_lowpass(self, output_path: str):
        positions = PlacementEngine().place_lowpass()

        d = schemdraw.Drawing(show=False)
        d.config(unit=3, fontsize=11)

        vin = positions["Vin"]

        d += elm.SourceSin().at(vin).up().label("Vin")
        d += elm.Line().right()
        d += elm.Resistor().right().label("R1", loc="top")

        d += elm.Dot().label(
            "Vout",
            loc="right",
            ofst=(0.3, 0.2),
        )

        d.push()

        d += elm.Capacitor().down().label(
            "C1",
            loc="top",
        )

        d += elm.Ground()

        d.pop()

        d.save(output_path, dpi=300)

        return output_path