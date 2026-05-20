import schemdraw
import schemdraw.elements as elm


def draw_current_mirror(output_path: str):
    d = schemdraw.Drawing(show=False)
    d.config(unit=3, fontsize=11)

    d += elm.SourceI().down().label("Iref", loc="left")
    d += elm.Line().down()
    d += elm.Dot().label("ref", loc="left")

    d.push()
    d += elm.Line().right()
    d += elm.NFet().anchor("gate").label("M1")
    d.pop()

    d += elm.Line().right().length(3)
    d += elm.NFet().anchor("gate").label("M2")
    d += elm.Line().up().label("out", loc="right")

    d += elm.Ground().at((0, -5))

    d.save(output_path, dpi=300)
    return output_path