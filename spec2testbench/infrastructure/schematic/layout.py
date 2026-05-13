"""Automatic component placement using graph layout."""

import networkx as nx
import numpy as np
from typing import Dict, Tuple, List, Optional
from .netlist_parser import NetlistGraph


class CircuitLayout:
    """Generate positions for circuit components."""
    
    # Preferred positions for special nodes
    SPECIAL_POSITIONS = {
        '0': (0, -2),      # GND at bottom
        'vdd': (0, 2),     # VDD at top
        'vcc': (0, 2),
        'vin': (-2, 0),    # Input on left
        'in': (-2, 0),
        'vout': (2, 0),    # Output on right
        'out': (2, 0),
    }
    
    def __init__(self, graph: NetlistGraph):
        self.graph = graph
        self.G = nx.Graph()
        self._build_graph()
    
    def _build_graph(self):
        """Build NetworkX graph from netlist."""
        for node in self.graph.nodes:
            self.G.add_node(node)
        
        for node1, node2, comp in self.graph.edges:
            self.G.add_edge(node1, node2, component=comp)
    
    def compute_positions(self) -> Dict[str, Tuple[float, float]]:
        """Compute positions for all nodes."""
        if len(self.G.nodes) == 0:
            return {}
        
        # Start with spring layout
        pos = nx.spring_layout(self.G, seed=42, k=2, iterations=50)
        
        # Adjust for special nodes
        for node, fixed_pos in self.SPECIAL_POSITIONS.items():
            if node in pos:
                # Blend with fixed position
                pos[node] = (pos[node][0] * 0.5 + fixed_pos[0] * 0.5,
                            pos[node][1] * 0.5 + fixed_pos[1] * 0.5)
        
        # Scale positions
        for node in pos:
            pos[node] = (pos[node][0] * 5, pos[node][1] * 3)
        
        return pos
    
    def get_component_positions(self, node_positions: Dict[str, Tuple[float, float]]) -> Dict[str, Tuple[float, float]]:
        """Calculate positions for components (center of connected nodes)."""
        comp_positions = {}
        
        for comp in self.graph.components:
            if len(comp.nodes) >= 2:
                # Position component at midpoint of its nodes
                positions = [node_positions.get(n, (0, 0)) for n in comp.nodes[:2]]
                comp_positions[comp.name] = (
                    (positions[0][0] + positions[1][0]) / 2,
                    (positions[0][1] + positions[1][1]) / 2
                )
        
        return comp_positions
