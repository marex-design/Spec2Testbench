"""Circuit drawing with Matplotlib only - no external dependencies."""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math


class MatplotlibDrawer:
    """Draw circuit using only Matplotlib."""
    
    def __init__(self):
        self.fig = None
        self.ax = None
    
    def draw_from_netlist(self, netlist: str, output_path: str = "circuit.png") -> Path:
        """Draw circuit from netlist."""
        components = self._parse_netlist(netlist)
        return self._draw_circuit(components, output_path)
    
    def _parse_netlist(self, netlist: str) -> List[Dict]:
        """Parse netlist to extract components."""
        components = []
        y = 2
        x = -2
        
        for line in netlist.split('\n'):
            line = line.strip()
            if not line or line.startswith('*') or line.startswith('.'):
                continue
            
            parts = line.split()
            if len(parts) < 2:
                continue
            
            name = parts[0]
            comp_type = name[0]
            
            # Extract nodes
            nodes = []
            for i in range(1, min(len(parts), 4)):
                p = parts[i]
                if p[0].isdigit() or p in ['0', 'gnd', 'vdd', 'in', 'out']:
                    nodes.append(p)
                else:
                    break
            
            if nodes:
                components.append({
                    'name': name,
                    'type': comp_type,
                    'nodes': nodes,
                    'value': parts[-1] if len(parts) > len(nodes)+1 else None,
                    'pos': (x, y)
                })
                x += 2
                if x > 3:
                    x = -2
                    y -= 2
        
        return components
    
    def _draw_circuit(self, components: List[Dict], output_path: str) -> Path:
        """Draw circuit with components."""
        self.fig, self.ax = plt.subplots(figsize=(12, 8))
        self.ax.set_xlim(-5, 5)
        self.ax.set_ylim(-4, 4)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        self.ax.set_title("Circuit Schematic", fontsize=14, fontweight='bold')
        
        # First pass: draw components
        for comp in components:
            self._draw_component(comp, comp['pos'])
        
        # Second pass: draw connections
        self._draw_connections(components)
        
        # Draw power and ground symbols
        self._draw_power_symbols()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return Path(output_path)
    
    def _draw_component(self, comp: Dict, pos: Tuple[float, float]):
        """Draw a single component."""
        x, y = pos
        comp_type = comp['type']
        name = comp['name']
        value = comp.get('value', '')
        
        self.ax.plot([x-0.6, x+0.6], [y, y], 'k-', lw=1, alpha=0.3)
        
        if comp_type == 'V':
            # Voltage source
            circle = patches.Circle((x, y), 0.3, fill=False, ec='black', lw=2)
            self.ax.add_patch(circle)
            self.ax.annotate('+', xy=(x-0.12, y+0.1), fontsize=14)
            self.ax.annotate('-', xy=(x-0.12, y-0.2), fontsize=14)
            self.ax.annotate(name, xy=(x, y-0.6), fontsize=9, ha='center')
        
        elif comp_type == 'R':
            # Resistor (zigzag)
            points = []
            for i in range(-5, 6):
                px = x + i * 0.12
                if abs(i) % 2 == 0:
                    py = y + 0.12
                else:
                    py = y - 0.12
                points.append((px, py))
            xs, ys = zip(*points)
            self.ax.plot(xs, ys, 'k-', lw=2)
            self.ax.annotate(name, xy=(x, y-0.6), fontsize=9, ha='center')
            if value:
                self.ax.annotate(value, xy=(x, y+0.5), fontsize=8, ha='center')
        
        elif comp_type == 'C':
            # Capacitor
            self.ax.plot([x-0.4, x-0.1], [y, y], 'k-', lw=2)
            self.ax.plot([x+0.1, x+0.4], [y, y], 'k-', lw=2)
            self.ax.plot([x-0.1, x-0.1], [y-0.25, y+0.25], 'k-', lw=2)
            self.ax.plot([x+0.1, x+0.1], [y-0.25, y+0.25], 'k-', lw=2)
            self.ax.annotate(name, xy=(x, y-0.6), fontsize=9, ha='center')
            if value:
                self.ax.annotate(value, xy=(x, y+0.5), fontsize=8, ha='center')
        
        elif comp_type == 'M':
            # MOSFET
            self.ax.plot([x-0.5, x+0.5], [y, y], 'k-', lw=1.5)
            self.ax.plot([x, x], [y+0.5, y-0.5], 'k-', lw=2.5)
            self.ax.plot([x-0.3, x], [y+0.25, y+0.25], 'k-', lw=1.5)
            self.ax.plot([x-0.3, x], [y-0.25, y-0.25], 'k-', lw=1.5)
            self.ax.annotate(name, xy=(x+0.6, y), fontsize=9, va='center')
        
        else:
            # Generic box
            rect = patches.Rectangle((x-0.35, y-0.25), 0.7, 0.5, fill=False, ec='black', lw=1.5)
            self.ax.add_patch(rect)
            self.ax.annotate(name, xy=(x, y-0.6), fontsize=9, ha='center')
    
    def _draw_connections(self, components: List[Dict]):
        """Draw connections between components."""
        # Simplified connections - connect in sequence
        for i in range(len(components)-1):
            c1 = components[i]
            c2 = components[i+1]
            x1, y1 = c1['pos']
            x2, y2 = c2['pos']
            self.ax.plot([x1+0.6, x2-0.6], [y1, y2], 'k-', lw=1, alpha=0.6)
    
    def _draw_power_symbols(self):
        """Draw VDD and GND symbols."""
        self.ax.annotate('VDD', xy=(-4, 3.5), fontsize=12, fontweight='bold')
        self.ax.annotate('VDD', xy=(4, 3.5), fontsize=12, fontweight='bold')
        self.ax.annotate('GND', xy=(-4, -3.5), fontsize=10)
        self.ax.annotate('GND', xy=(4, -3.5), fontsize=10)


def netlist_to_schematic(netlist: str, output_path: str = "schematic.png") -> str:
    """Convert netlist to schematic PNG."""
    drawer = MatplotlibDrawer()
    result = drawer.draw_from_netlist(netlist, output_path)
    return str(result)
