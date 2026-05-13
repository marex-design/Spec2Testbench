"""Parse SPICE netlist to graph structure."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class Component:
    """Component in the circuit."""
    name: str
    type: str  # R, C, L, M, Q, V, I
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
        neighbors = set()
        for comp in self.components:
            if node in comp.nodes:
                for n in comp.nodes:
                    if n != node:
                        neighbors.add(n)
        return neighbors


class NetlistParser:
    """Parse SPICE netlist to graph."""
    
    # Component type patterns
    COMPONENT_PATTERN = re.compile(
        r'^(?P<name>[A-Za-z][A-Za-z0-9_]*)\s+(?P<nodes>[\d\w\s\.]+?)\s*(?P<value>\S+)?'
    )
    
    def parse(self, netlist: str) -> NetlistGraph:
        """Parse netlist string to graph."""
        components = []
        nodes = set()
        edges = []
        
        lines = [l.strip() for l in netlist.split('\n') 
                 if l.strip() and not l.strip().startswith('*')]
        
        for line in lines:
            comp = self._parse_component(line)
            if comp:
                components.append(comp)
                for node in comp.nodes:
                    if node.isdigit() or node.replace('.', '').isdigit():
                        nodes.add(node)
                # Add edges between nodes connected by this component
                if len(comp.nodes) >= 2:
                    for i in range(len(comp.nodes)-1):
                        for j in range(i+1, len(comp.nodes)):
                            edges.append((comp.nodes[i], comp.nodes[j], comp))
        
        return NetlistGraph(
            components=components,
            nodes=nodes,
            edges=edges
        )
    
    def _parse_component(self, line: str) -> Optional[Component]:
        """Parse a single component line."""
        if not line or not line[0].isalpha():
            return None
        
        parts = line.split()
        if len(parts) < 2:
            return None
        
        name = parts[0]
        comp_type = name[0].upper()
        
        # Find nodes (nodes are numbers or names starting with letters)
        nodes = []
        value = None
        model = None
        
        for i in range(1, len(parts)):
            part = parts[i]
            if part.startswith('.'):
                break
            # Check if this is a value (starts with digit or has unit)
            if part[0].isdigit() or any(u in part for u in ['k', 'M', 'u', 'n', 'p', 'm']):
                if not value:
                    value = part
            elif part.upper() in ['DC', 'AC', 'PULSE', 'SIN']:
                break
            else:
                nodes.append(part)
        
        # For MOSFETs, the last node might be a model
        if comp_type in ['M', 'Q', 'D'] and len(nodes) > 2:
            model = nodes[-1]
            nodes = nodes[:-1]
        
        return Component(
            name=name,
            type=comp_type,
            nodes=nodes,
            value=value,
            model=model
        )
