import schemdraw
import schemdraw.elements as elm


def draw_lowpass_filter(output_path: str):
    d = schemdraw.Drawing(show=False)
    d.config(unit=3, fontsize=11)

    d += elm.SourceSin().up().label("Vin\nAC 1", loc="left")
    d += elm.Line().right()
    d += elm.Resistor().right().label("R1\n1k", loc="top")
    d += elm.Dot().label("out", loc="right")

    d.push()
    d += elm.Capacitor().down().label("C1", loc="right")
    d += elm.Ground()
    d.pop()

    d += elm.Line().right().label("Vout", loc="right")

    d.save(output_path, dpi=300)
    return output_path