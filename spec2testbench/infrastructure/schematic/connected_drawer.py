from pathlib import Path
import schemdraw
import schemdraw.elements as elm

from .netlist_parser import NetlistParser


def _is_ground(net: str) -> bool:
    return net.lower() in ["0", "gnd", "ground"]


def _is_input(net: str) -> bool:
    return "in" in net.lower()


def _is_output(net: str) -> bool:
    return "out" in net.lower()


def _node_position(net: str, index: int) -> tuple[float, float]:
    if _is_ground(net):
        return (0, -3)

    if net.lower() in ["vdd", "vcc", "v+"] or "vdd" in net.lower():
        return (0, 3)

    if _is_input(net):
        return (-5, 0)

    if _is_output(net):
        return (5, 0)

    return (index * 2.5, 0)


def _element_between(component):
    t = component.type.upper()
    label = component.name

    if component.value:
        label += f"\n{component.value}"

    if t == "R":
        return elm.Resistor().label(label)
    if t == "C":
        return elm.Capacitor().label(label)
    if t == "L":
        return elm.Inductor().label(label)
    if t == "V":
        return elm.SourceV().label(label)
    if t == "I":
        return elm.SourceI().label(label)
    if t == "D":
        return elm.Diode().label(label)

    return None


def netlist_to_connected_schematic(netlist: str, output_path: str) -> str:
    graph = NetlistParser().parse(netlist)

    if not graph.components:
        raise ValueError("No components parsed from netlist.")

    nets = []
    for comp in graph.components:
        for net in comp.nodes:
            if net not in nets:
                nets.append(net)

    node_positions = {
        net: _node_position(net, i)
        for i, net in enumerate(nets)
    }

    d = schemdraw.Drawing(show=False)
    d.config(unit=2.5, fontsize=10)

    for net, pos in node_positions.items():
        x, y = pos

        if _is_ground(net):
            d += elm.Ground().at((x, y))
            d += elm.Label().label(net, fontsize=8).at((x + 0.2, y - 0.3))
        else:
            d += elm.Dot().at((x, y))
            d += elm.Label().label(net, fontsize=8).at((x + 0.2, y + 0.2))

    offset = 0

    for comp in graph.components:
        if len(comp.nodes) != 2:
            continue

        elem = _element_between(comp)

        if elem is None:
            continue

        n1, n2 = comp.nodes
        x1, y1 = node_positions[n1]
        x2, y2 = node_positions[n2]

        if abs(x1 - x2) >= abs(y1 - y2):
            mid_y = y1 + offset
            d += elm.Line().at((x1, y1)).to((x1, mid_y))
            d += elem.at((x1, mid_y)).to((x2, mid_y))
            d += elm.Line().at((x2, mid_y)).to((x2, y2))
        else:
            mid_x = x1 + offset
            d += elm.Line().at((x1, y1)).to((mid_x, y1))
            d += elem.at((mid_x, y1)).down().to((mid_x, y2))
            d += elm.Line().at((mid_x, y2)).to((x2, y2))

        offset += 0.4

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    d.save(str(out), dpi=300)
    return str(out)

def draw_lowpass_filter(output_path: str):
    import schemdraw
    import schemdraw.elements as elm

    d = schemdraw.Drawing(show=False)
    d.config(unit=3, fontsize=11)

    d += elm.SourceSin().up().label("Vin\nAC 1", loc="left")
    d += elm.Line().right()
    d += elm.Resistor().right().label("R1\n1k", loc="top")
    d += elm.Dot().label("out", loc="right")

    d.push()
    d += elm.Capacitor().down().label("C1\n159n", loc="right")
    d += elm.Ground()
    d.pop()

    d += elm.Line().right().label("Vout", loc="right")

    d.save(output_path, dpi=300)