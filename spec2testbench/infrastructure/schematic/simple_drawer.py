"""
Real netlist-driven schematic drawer.

Replaces the previous hardcoded SimpleDrawer that ignored its netlist argument
and always drew the same six components (VDD, VIN, M1, R1, OUT, GND).

This implementation:
  1. Parses the actual SPICE netlist via NetlistParser.
  2. Places one component per grid cell, choosing an element shape from the
     SPICE letter prefix (R, C, L, V, I, D, M, Q).
  3. Annotates each terminal with its net name so connectivity is visible.
  4. Adds a ground reference if node "0" is present.
  5. Renders via SchemDraw -> PNG.

The contract is simple: different netlists MUST produce different figures.
"""

from pathlib import Path
import schemdraw
import schemdraw.elements as elm

from .netlist_parser import NetlistParser, Component


# Grid spacing between component cells (SchemDraw units)
DX = 5.5
DY = 4.0


def _element_for(comp: Component):
    """Return an unplaced SchemDraw element matching the SPICE component type."""
    t = comp.type.upper()
    if comp.value:
        label = f"{comp.name}\n{comp.value}"
    else:
        label = comp.name

    if t == "R":
        return elm.Resistor().label(label, loc="bottom")
    if t == "C":
        return elm.Capacitor().label(label, loc="bottom")
    if t == "L":
        return elm.Inductor().label(label, loc="bottom")
    if t == "V":
        return elm.SourceV().label(label, loc="left")
    if t == "I":
        return elm.SourceI().label(label, loc="left")
    if t == "D":
        return elm.Diode().label(label, loc="bottom")
    if t == "M":
        is_pmos = bool(comp.model) and "p" in comp.model.lower()
        elem = elm.PFet() if is_pmos else elm.NFet()
        return elem.label(label)
    if t == "Q":
        return elm.BjtNpn().label(label)
    # Fallback: a labeled box so unknown components still appear
    return elm.RBox().label(label)


def _terminal_names(comp: Component):
    """Human-readable terminal labels per SPICE component type."""
    t = comp.type.upper()
    if t == "M":
        # SPICE order: drain gate source body
        return ["D", "G", "S", "B"][: len(comp.nodes)]
    if t == "Q":
        return ["C", "B", "E"][: len(comp.nodes)]
    if t in ("R", "C", "L", "V", "I", "D"):
        return ["+", "-"][: len(comp.nodes)]
    return [str(i + 1) for i in range(len(comp.nodes))]


def netlist_to_schematic(netlist: str, output_path: str = "schematic.png") -> str:
    """Render a netlist to a PNG schematic.

    Args:
        netlist: Raw SPICE netlist text.
        output_path: Where to write the PNG.

    Returns:
        The output path as a string.

    Raises:
        ValueError: If the netlist contains no parseable components.
    """
    graph = NetlistParser().parse(netlist)
    if not graph.components:
        raise ValueError(
            "No components could be parsed from the netlist. "
            "Check that the file contains SPICE element lines."
        )

    # Lay out components in an approximately square grid
    n = len(graph.components)
    cols = max(1, int(n ** 0.5) + (1 if n ** 0.5 != int(n ** 0.5) else 0))

    d = schemdraw.Drawing(show=False)
    d.config(unit=2.5, fontsize=10)

    placed = {}  # comp.name -> (x, y)
    for idx, comp in enumerate(graph.components):
        row, col = divmod(idx, cols)
        x, y = col * DX, -row * DY
        placed[comp.name] = (x, y)

        elem = _element_for(comp).at((x, y))
        d += elem

        # Annotate each terminal with its net name (column to the right of cell)
        tnames = _terminal_names(comp)
        for k, (net, tname) in enumerate(zip(comp.nodes, tnames)):
            tx = x + 2.0
            ty = y + 1.0 - 0.45 * k
            d += elm.Dot(radius=0.06).at((tx, ty))
            d += elm.Label().label(f"  {tname}={net}", loc="right", fontsize=8).at((tx, ty))

    # Net summary panel: which nets exist, and how many pins each has
    net_pins: dict[str, int] = {}
    for c in graph.components:
        for net in c.nodes:
            net_pins[net] = net_pins.get(net, 0) + 1

    summary_lines = [f"  {net}: {p} pin{'s' if p != 1 else ''}" for net, p in sorted(net_pins.items())]
    summary = "Nets in this circuit:\n" + "\n".join(summary_lines)
    panel_x = cols * DX + 1.5
    panel_y = -DY * (max(n - 1, 0) // cols) / 2
    d += elm.Label().label(summary, loc="right", fontsize=9, halign="left").at((panel_x, panel_y))

    # Ground reference if net 0 is present
    if "0" in net_pins:
        gnd_x = cols * DX / 2
        gnd_y = -DY * ((n - 1) // cols) - 2
        d += elm.Line().at((gnd_x, gnd_y + 1)).to((gnd_x, gnd_y))
        d += elm.GroundChassis().at((gnd_x, gnd_y))
        d += elm.Label().label("GND (net 0)", loc="bottom", fontsize=9).at((gnd_x, gnd_y))

    out = Path(output_path)
    if out.parent and str(out.parent) != ".":
        out.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out), dpi=150)
    return str(out)
