from pathlib import Path
import schemdraw
import schemdraw.elements as elm

from spec2testbench.infrastructure.schematic.graph.graph_builder import GraphBuilder


def is_ground(net: str) -> bool:
    return net.lower() in ["0", "gnd", "ground"]


def is_supply(net: str) -> bool:
    return net.lower() in ["vdd", "vcc", "v+", "vss", "vee", "v-"]


def is_input(net: str) -> bool:
    return "in" in net.lower() or "vin" in net.lower()


def is_output(net: str) -> bool:
    return "out" in net.lower() or "vout" in net.lower()


def choose_element(component):
    label = component.name

    if component.value:
        label += f"\n{component.value}"

    t = component.type.upper()

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
    if t == "M":
        if component.model and "p" in component.model.lower():
            return elm.PFet().label(label)
        return elm.NFet().label(label)

    return elm.RBox().label(label)


def assign_net_positions(graph):
    positions = {}

    left_y = 0
    right_y = 0
    middle_x = 0

    for net in graph.nets:
        if is_ground(net):
            positions[net] = (0, -4)
        elif is_supply(net):
            positions[net] = (0, 4)
        elif is_input(net):
            positions[net] = (-6, left_y)
            left_y -= 2
        elif is_output(net):
            positions[net] = (6, right_y)
            right_y -= 2
        else:
            positions[net] = (middle_x, 0)
            middle_x += 2

    return positions


def draw_component_between(d, component, p1, p2):
    x1, y1 = p1
    x2, y2 = p2

    element = choose_element(component)

    if abs(x2 - x1) >= abs(y2 - y1):
        d += elm.Line().at((x1, y1)).to((x1 + 0.5, y1))
        d += element.at((x1 + 0.5, y1)).to((x2 - 0.5, y2))
        d += elm.Line().at((x2 - 0.5, y2)).to((x2, y2))
    else:
        d += elm.Line().at((x1, y1)).to((x1, y1 - 0.5))
        d += element.down().at((x1, y1 - 0.5)).to((x2, y2 + 0.5))
        d += elm.Line().at((x2, y2 + 0.5)).to((x2, y2))


def draw_graph_schematic(netlist: str, output_path: str) -> str:
    graph = GraphBuilder().build_from_netlist(netlist)

    if graph.component_count() == 0:
        raise ValueError("No components found in netlist.")

    positions = assign_net_positions(graph)

    d = schemdraw.Drawing(show=False)
    d.config(unit=2.5, fontsize=10)

    for net, pos in positions.items():
        if is_ground(net):
            d += elm.Ground().at(pos)
            d += elm.Label().label("0", fontsize=8).at((pos[0] + 0.3, pos[1] - 0.3))
        else:
            d += elm.Dot().at(pos)
            d += elm.Label().label(net, fontsize=8).at((pos[0] + 0.2, pos[1] + 0.2))

    for component in graph.components:
        if len(component.nodes) < 2:
            continue

        n1 = component.nodes[0]
        n2 = component.nodes[1]

        if n1 not in positions or n2 not in positions:
            continue

        draw_component_between(
            d,
            component,
            positions[n1],
            positions[n2],
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out), dpi=300)

    return str(out)