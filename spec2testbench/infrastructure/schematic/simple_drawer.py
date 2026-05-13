"""Simple and reliable circuit drawer."""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
import math


class SimpleDrawer:
    """Draw circuit with fixed positions."""
    
    # Composants standard
    COMPONENTS = [
        {'name': 'VDD', 'type': 'source', 'pos': (-3, 2), 'nodes': ['vdd', '1']},
        {'name': 'VIN', 'type': 'source', 'pos': (-3, 0), 'nodes': ['vin', '2']},
        {'name': 'M1', 'type': 'mosfet', 'pos': (0, 0), 'nodes': ['2', '3', '0', '0']},
        {'name': 'R1', 'type': 'resistor', 'pos': (2, 1), 'nodes': ['3', 'vdd']},
        {'name': 'OUT', 'type': 'out', 'pos': (3, 0), 'nodes': ['3']},
        {'name': 'GND', 'type': 'ground', 'pos': (0, -2), 'nodes': ['0']},
    ]
    
    def draw(self, output_path: str = "circuit.png") -> Path:
        """Draw the circuit."""
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.set_xlim(-4, 4)
        ax.set_ylim(-3, 3)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title("Circuit Schematic", fontsize=14, fontweight='bold')
        
        # 1. Draw connections (wires)
        self._draw_wires(ax)
        
        # 2. Draw components
        for comp in self.COMPONENTS:
            self._draw_component(ax, comp)
        
        # 3. Draw labels
        self._draw_labels(ax)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return Path(output_path)
    
    def _draw_wires(self, ax):
        """Draw connections between components."""
        # Main horizontal line
        ax.plot([-2, 2.5], [0, 0], 'k-', lw=1.5)
        # VDD vertical
        ax.plot([-2, -2], [1, 2], 'k-', lw=1.5)
        # Output vertical
        ax.plot([2.5, 2.5], [-0.5, 0.5], 'k-', lw=1.5)
        # GND vertical
        ax.plot([0, 0], [-1.5, -0.2], 'k-', lw=1.5)
        # VIN connection
        ax.plot([-2, -2], [-0.2, 0.2], 'k-', lw=1.5)
    
    def _draw_component(self, ax, comp):
        """Draw a component."""
        x, y = comp['pos']
        t = comp['type']
        
        if t == 'source':
            # Voltage source (circle)
            circle = patches.Circle((x, y), 0.25, fill=False, ec='black', lw=2)
            ax.add_patch(circle)
            ax.annotate('+', xy=(x-0.1, y+0.05), fontsize=12)
            ax.annotate('-', xy=(x-0.1, y-0.15), fontsize=12)
        
        elif t == 'resistor':
            # Resistor (zigzag)
            points = []
            for i in range(-3, 4):
                px = x + i * 0.2
                if i % 2 == 0:
                    py = y + 0.15
                else:
                    py = y - 0.15
                points.append((px, py))
            xs, ys = zip(*points)
            ax.plot(xs, ys, 'k-', lw=2)
        
        elif t == 'mosfet':
            # MOSFET
            ax.plot([x-0.4, x+0.4], [y, y], 'k-', lw=1)
            ax.plot([x, x], [y+0.4, y-0.4], 'k-', lw=2)
            ax.plot([x-0.3, x], [y+0.2, y+0.2], 'k-', lw=1)
            ax.plot([x-0.3, x], [y-0.2, y-0.2], 'k-', lw=1)
            # Arrow
            ax.annotate('', xy=(x+0.1, y-0.2), xytext=(x+0.1, y+0.2),
                       arrowprops=dict(arrowstyle='->', lw=1))
        
        elif t == 'out':
            # Output node
            ax.plot(x, y, 'ko', markersize=6)
        
        elif t == 'ground':
            # Ground symbol
            ax.plot([x-0.3, x+0.3], [y, y], 'k-', lw=2)
            ax.plot([x-0.2, x+0.2], [y-0.1, y-0.1], 'k-', lw=1.5)
            ax.plot([x-0.1, x+0.1], [y-0.2, y-0.2], 'k-', lw=1)
    
    def _draw_labels(self, ax):
        """Draw text labels."""
        labels = [
            ('VDD', (-3, 2.35), 'right'),
            ('VIN', (-3, -0.35), 'right'),
            ('M1', (0, 0.7), 'center'),
            ('R1', (2, 1.35), 'center'),
            ('OUT', (3, 0), 'left'),
            ('GND', (0, -2.3), 'center'),
        ]
        
        for text, pos, ha in labels:
            ax.annotate(text, xy=pos, fontsize=10, fontweight='bold', ha=ha)


def netlist_to_schematic(netlist: str, output_path: str = "schematic.png") -> str:
    """Generate schematic from netlist."""
    drawer = SimpleDrawer()
    result = drawer.draw(output_path)
    return str(result)
