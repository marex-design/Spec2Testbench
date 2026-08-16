import schemdraw
import schemdraw.elements as elm


def draw_differential_pair(output_path: str):
    d = schemdraw.Drawing(show=False)
    d.config(unit=3, fontsize=11)

    d += elm.NFet().at((-2, 0)).label("M1")
    d += elm.Label().at((-4, 0)).label("Vin+")
    d += elm.Line().at((-2, -1)).to((0, -2))

    d += elm.NFet().at((2, 0)).label("M2")
    d += elm.Label().at((4, 0)).label("Vin-")
    d += elm.Line().at((2, -1)).to((0, -2))

    d += elm.SourceI().at((0, -2)).down().label("Itail")
    d += elm.Ground()

    d += elm.Resistor().at((-2, 2)).up().label("RD1")
    d += elm.Resistor().at((2, 2)).up().label("RD2")

    d += elm.Label().at((-2, 3.5)).label("Vout+")
    d += elm.Label().at((2, 3.5)).label("Vout-")

    d.save(output_path, dpi=300)
    return output_path