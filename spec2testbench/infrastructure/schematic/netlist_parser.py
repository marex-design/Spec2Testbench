"""Parse SPICE netlist to graph structure.

This is a corrected implementation. The previous version used a single
heuristic ("token contains a unit-like letter -> it's a value") to split
nodes from values, which mis-classified common node names like 'out',
'in', 'vdd' (any name containing one of k/M/u/n/p/m) as values and
discarded them.

The fix here uses the standard SPICE convention: for each element letter,
the number of node tokens is fixed and known:

    R, C, L, V, I, D : 2 nodes
    M (MOSFET)       : 4 nodes  + model name
    Q (BJT)          : 3 nodes  + model name
    J (JFET)         : 3 nodes  + model name

Everything after the expected nodes is treated as the value/parameter
string. This is robust and matches what ngspice / PySpice actually parse.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple


@dataclass
class Component:
    """Component in the circuit."""
    name: str
    type: str   # R, C, L, M, Q, V, I, D, J, ...
    nodes: List[str]
    value: Optional[str] = None
    model: Optional[str] = None


@dataclass
class NetlistGraph:
    """Graph representation of a netlist."""
    components: List[Component]
    nodes: Set[str]
    edges: List[Tuple[str, str, Component]]

    def get_connections(self, node: str) -> List[Component]:
        """Get all components connected to a node."""
        return [comp for comp in self.components if node in comp.nodes]

    def get_neighbors(self, node: str) -> Set[str]:
        """Get all nodes connected to a node."""
        neighbors: Set[str] = set()
        for comp in self.components:
            if node in comp.nodes:
                for n in comp.nodes:
                    if n != node:
                        neighbors.add(n)
        return neighbors


# Number of node terminals expected per SPICE element-type letter.
_NODE_COUNT = {
    "R": 2, "C": 2, "L": 2, "V": 2, "I": 2, "D": 2, "E": 4, "F": 2,
    "G": 4, "H": 2, "K": 0, "M": 4, "Q": 3, "J": 3, "S": 4, "W": 4,
    "X": None,  # subcircuit - variable number of nodes
}

# Element types whose token after the node list is a model name.
_HAS_MODEL = {"M", "Q", "J", "D"}


class NetlistParser:
    """Parse SPICE netlist into a structural graph."""

    _CONTROL_KEYWORDS = {"DC", "AC", "PULSE", "SIN", "EXP", "PWL", "SFFM", "TRAN"}

    def parse(self, netlist: str) -> NetlistGraph:
        components: List[Component] = []
        nodes: Set[str] = set()
        edges: List[Tuple[str, str, Component]] = []

        # Strip comments (* or ;) and dot-directives (.model, .end, ...)
        raw_lines = netlist.splitlines()
        merged = self._merge_continuation_lines(raw_lines)

        for line in merged:
            s = line.strip()
            if not s:
                continue
            if s.startswith("*") or s.startswith(";"):
                continue
            if s.startswith("."):
                continue
            if not s[0].isalpha():
                continue

            comp = self._parse_component(s)
            if comp is None:
                continue
            components.append(comp)
            for n in comp.nodes:
                nodes.add(n)
            # Build edges between every pair of nodes on this component
            for i in range(len(comp.nodes)):
                for j in range(i + 1, len(comp.nodes)):
                    edges.append((comp.nodes[i], comp.nodes[j], comp))

        return NetlistGraph(components=components, nodes=nodes, edges=edges)

    # ----- internals -----

    @staticmethod
    def _merge_continuation_lines(lines: List[str]) -> List[str]:
        """Honour SPICE '+' line-continuation."""
        merged: List[str] = []
        for ln in lines:
            if ln.startswith("+") and merged:
                merged[-1] = merged[-1].rstrip() + " " + ln[1:].strip()
            else:
                merged.append(ln)
        return merged

    def _parse_component(self, line: str) -> Optional[Component]:
        # Drop trailing comment after ';'
        if ";" in line:
            line = line.split(";", 1)[0]

        parts = line.split()
        if len(parts) < 3:
            return None

        name = parts[0]
        comp_type = name[0].upper()

        if comp_type == "X":
            # Subcircuit: nodes are everything up to (but not including) the
            # last token, which is the subcircuit name.
            if len(parts) < 4:
                return None
            nodes = parts[1:-1]
            model = parts[-1]
            return Component(name=name, type=comp_type, nodes=nodes, value=None, model=model)

        expected_nodes = _NODE_COUNT.get(comp_type)
        if expected_nodes is None or expected_nodes == 0:
            return None

        # For MOSFETs: SPICE allows 3- or 4-terminal forms. Detect by checking
        # whether parts[5] (the would-be model) exists; if there are only
        # 5 tokens total (name + 3 nodes + model), it's a 3-terminal device.
        if comp_type == "M":
            # name + 4 nodes + model + maybe params -> 6+ tokens
            # name + 3 nodes + model + maybe params -> 5+ tokens
            # We pick whichever fits.
            if len(parts) >= 6:
                nodes = parts[1:5]
                rest = parts[5:]
            else:
                nodes = parts[1:4]
                rest = parts[4:] if len(parts) >= 5 else []
        else:
            if len(parts) < 1 + expected_nodes:
                # Not enough tokens for the declared element type
                return None
            nodes = parts[1 : 1 + expected_nodes]
            rest = parts[1 + expected_nodes :]

        model: Optional[str] = None
        value: Optional[str] = None

        if comp_type in _HAS_MODEL and rest:
            # First token after nodes is the model name (must look like an identifier)
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rest[0]):
                model = rest[0]
                rest = rest[1:]

        if rest:
            # Skip leading control keyword (DC/AC/PULSE/SIN/...) when present
            if rest[0].upper() in self._CONTROL_KEYWORDS:
                value = " ".join(rest)
            else:
                value = " ".join(rest)

        return Component(name=name, type=comp_type, nodes=nodes, value=value, model=model)
