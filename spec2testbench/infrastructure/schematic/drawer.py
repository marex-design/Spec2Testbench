"""Draw circuit schematic from layout."""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path as MPath
import numpy as np
from typing import Dict, Tuple, Optional
from pathlib import Path

from .netlist_parser import NetlistGraph, Component
from .layout import CircuitLayout


class CircuitDrawer:
    """Draw circuit schematic using Matplotlib."""
    
    # Component shapes
    def __init__(self, figsize: Tuple[int, int] = (12, 8)):
        self.figsize = figsize
        self.fig = None
        self.ax = None
    
    def draw(self, graph: NetlistGraph, output_path: Optional[Path] = None, show: bool = False) -> Optional[Path]:
        """Draw the circuit and save or show."""
        self.fig, self.ax = plt.subplots(figsize=self.figsize)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        self.ax.set_title("Circuit Schematic", fontsize=14)
        
        # Compute layout
        layout = CircuitLayout(graph)
        node_positions = layout.compute_positions()
        comp_positions = layout.get_component_positions(node_positions)
        
        # Draw wires (edges)
        for node1, node2, comp in graph.edges:
            if node1 in node_positions and node2 in node_positions:
                self._draw_wire(node_positions[node1], node_positions[node2])
        
        # Draw components
        for comp in graph.components:
            if comp.name in comp_positions:
                self._draw_component(comp, comp_positions[comp.name])
        
        # Draw node labels
        for node, pos in node_positions.items():
            if node not in ['0']:  # Skip ground
                self.ax.annotate(node, xy=pos, fontsize=8, ha='center', va='bottom')
        
        # Add ground symbol
        if '0' in node_positions:
            self._draw_ground(node_positions['0'])
        
        self.ax.set_xlim(-8, 8)
        self.ax.set_ylim(-6, 6)
        self.ax.grid(True, alpha=0.2)
        
        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            return output_path
        elif show:
            plt.show()
            return None
        else:
            plt.close()
            return None
    
    def _draw_wire(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        """Draw a wire between two points."""
        self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 'k-', linewidth=1, alpha=0.7)
    
    def _draw_component(self, comp: Component, pos: Tuple[float, float]):
        """Draw a component at given position."""
        x, y = pos
        size = 0.5
        
        if comp.type == 'R':
            # Resistor: zigzag
            self._draw_resistor(x, y)
            self.ax.annotate(comp.value or comp.name, xy=(x, y-0.4), fontsize=8, ha='center')
        
        elif comp.type == 'C':
            # Capacitor: two parallel lines
            self._draw_capacitor(x, y)
            self.ax.annotate(comp.value or comp.name, xy=(x, y-0.4), fontsize=8, ha='center')
        
        elif comp.type == 'M':
            # MOSFET
            self._draw_mosfet(x, y, comp.name)
        
        elif comp.type == 'V':
            # Voltage source: circle with +/-
            self._draw_voltage_source(x, y)
            self.ax.annotate(comp.name, xy=(x, y-0.5), fontsize=8, ha='center')
        
        else:
            # Default: draw a box
            self._draw_box(x, y, comp.type)
            self.ax.annotate(comp.name, xy=(x, y-0.3), fontsize=7, ha='center')
    
    def _draw_resistor(self, x: float, y: float):
        """Draw resistor symbol."""
        segs = [(x-0.6, y), (x-0.4, y), (x-0.3, y+0.15), (x-0.1, y-0.15),
                (x+0.1, y+0.15), (x+0.3, y-0.15), (x+0.4, y), (x+0.6, y)]
        xs, ys = zip(*segs)
        self.ax.plot(xs, ys, 'k-', linewidth=1.5)
        self.ax.plot([x-0.6, x+0.6], [y, y], 'k-', linewidth=0.5, alpha=0.5)
    
    def _draw_capacitor(self, x: float, y: float):
        """Draw capacitor symbol."""
        self.ax.plot([x-0.55, x-0.15], [y, y], 'k-', linewidth=1)
        self.ax.plot([x+0.15, x+0.55], [y, y], 'k-', linewidth=1)
        self.ax.plot([x-0.15, x-0.15], [y-0.2, y+0.2], 'k-', linewidth=1.5)
        self.ax.plot([x+0.15, x+0.15], [y-0.2, y+0.2], 'k-', linewidth=1.5)
    
    def _draw_mosfet(self, x: float, y: float, name: str):
        """Draw MOSFET symbol."""
        # Gate
        self.ax.plot([x-0.5, x-0.1], [y, y], 'k-', linewidth=1)
        # Drain-Source line
        self.ax.plot([x, x], [y+0.4, y-0.4], 'k-', linewidth=1.5)
        # Gate vertical
        self.ax.plot([x-0.1, x-0.1], [y-0.2, y+0.2], 'k-', linewidth=1)
        # Substrate arrow
        self.ax.annotate('', xy=(x+0.1, y-0.2), xytext=(x+0.1, y+0.2),
                        arrowprops=dict(arrowstyle='->', lw=1))
        self.ax.annotate(name, xy=(x+0.3, y), fontsize=8, ha='center')
    
    def _draw_voltage_source(self, x: float, y: float):
        """Draw voltage source symbol."""
        circle = patches.Circle((x, y), 0.3, fill=False, ec='black', lw=1.5)
        self.ax.add_patch(circle)
        self.ax.annotate('+', xy=(x-0.15, y+0.15), fontsize=10, ha='center')
        self.ax.annotate('-', xy=(x-0.15, y-0.15), fontsize=10, ha='center')
    
    def _draw_box(self, x: float, y: float, label: str):
        """Draw a generic box."""
        rect = patches.Rectangle((x-0.4, y-0.3), 0.8, 0.6, fill=False, ec='black', lw=1)
        self.ax.add_patch(rect)
        self.ax.annotate(label, xy=(x, y), fontsize=8, ha='center', va='center')
    
    def _draw_ground(self, pos: Tuple[float, float]):
        """Draw ground symbol."""
        x, y = pos
        self.ax.plot([x-0.3, x+0.3], [y, y], 'k-', linewidth=1.5)
        self.ax.plot([x-0.2, x+0.2], [y-0.1, y-0.1], 'k-', linewidth=1)
        self.ax.plot([x-0.1, x+0.1], [y-0.2, y-0.2], 'k-', linewidth=0.8)
        self.ax.annotate('GND', xy=(x+0.3, y-0.2), fontsize=8)
