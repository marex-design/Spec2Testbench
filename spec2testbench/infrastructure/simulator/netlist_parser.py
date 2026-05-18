# spec2testbench/infrastructure/simulator/netlist_parser.py

"""
Parser for SPICE netlist files.
Extracts components, nodes, and parameters.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class Component:
    """SPICE component."""
    name: str
    type: str  # R, C, L, V, I, Q, M, etc.
    nodes: List[str]
    value: Optional[str] = None
    parameters: Dict[str, str] = field(default_factory=dict)
    model: Optional[str] = None


@dataclass
class NetlistInfo:
    """Parsed netlist information."""
    components: List[Component]
    nodes: List[str]
    models: Dict[str, Dict]
    subcircuits: Dict[str, List[Component]]
    top_level: bool = True


class NetlistParser:
    """
    Parse SPICE netlist files.
    """
    
    # Regular expressions for parsing
    COMPONENT_PATTERN = re.compile(
        r'^(?P<name>[A-Za-z][A-Za-z0-9_]*)\s+(?P<nodes>[\d\w\s\.]+?)\s*(?P<value>\S+)?\s*(?P<params>.*)$'
    )
    
    MODEL_PATTERN = re.compile(r'\.MODEL\s+(?P<name>\S+)\s+(?P<type>\S+)\s*(?P<params>.*)')
    
    SUBCKT_START = re.compile(r'\.SUBCKT\s+(?P<name>\S+)\s+(?P<nodes>.*)')
    SUBCKT_END = re.compile(r'\.ENDS\s*')
    
    VALUE_WITH_UNIT = re.compile(r'^(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([a-zA-Z]+)?$')
    
    def parse(self, netlist_path: Path) -> NetlistInfo:
        """
        Parse a SPICE netlist file.
        
        Args:
            netlist_path: Path to .cir or .spice file
            
        Returns:
            NetlistInfo with parsed components
        """
        if not netlist_path.exists():
            raise FileNotFoundError(f"Netlist not found: {netlist_path}")
        
        content = netlist_path.read_text(encoding='utf-8', errors='ignore')
        return self.parse_content(content)
    
    def parse_content(self, content: str) -> NetlistInfo:
        """
        Parse SPICE content string.
        
        Args:
            content: SPICE netlist content
            
        Returns:
            NetlistInfo with parsed components
        """
        lines = [line.strip() for line in content.splitlines()]
        
        components = []
        models = {}
        subcircuits = {}
        current_subcircuit = None
        subcircuit_components = []
        
        for line in lines:
            if not line or line.startswith('*'):
                continue
            
            # Check for subcircuit start
            sub_match = self.SUBCKT_START.match(line)
            if sub_match:
                current_subcircuit = sub_match.group('name')
                subcircuit_components = []
                continue
            
            # Check for subcircuit end
            if self.SUBCKT_END.match(line):
                if current_subcircuit:
                    subcircuits[current_subcircuit] = subcircuit_components
                    current_subcircuit = None
                    subcircuit_components = []
                continue
            
            # Check for model
            model_match = self.MODEL_PATTERN.match(line)
            if model_match:
                models[model_match.group('name')] = {
                    'type': model_match.group('type'),
                    'params': self._parse_model_params(model_match.group('params'))
                }
                continue
            
            # Parse component
            comp = self._parse_component(line)
            if comp:
                if current_subcircuit:
                    subcircuit_components.append(comp)
                else:
                    components.append(comp)
        
        # Collect all nodes
        all_components = components + subcircuit_components
        nodes = set()
        for comp in all_components:
            for node in comp.nodes:
                if node != '0':
                    nodes.add(node)
        
        return NetlistInfo(
            components=components,
            nodes=sorted(nodes),
            models=models,
            subcircuits=subcircuits
        )
    
    def _parse_component(self, line: str) -> Optional[Component]:
        """Parse a single component line."""
        # Identify component type by first character
        if not line or not line[0].isalpha():
            return None
        
        parts = line.split()
        if len(parts) < 2:
            return None
        
        name = parts[0]
        comp_type = name[0]
        
        # Extract nodes (until a value is found)
        nodes = []
        value = None
        params = {}
        model = None
        
        for i in range(1, len(parts)):
            part = parts[i]
            if part.startswith('+'):
                continue
            if part.startswith('='):
                # Parameter
                continue
            if part.upper() in ['DC', 'AC', 'PULSE', 'SIN', 'PWL', 'EXP', 'SFFM']:
                # Source function
                value = ' '.join(parts[i:])
                break
            if self._is_value(part):
                value = part
                break
            # It's a node or model name
            nodes.append(part)
        
        # Check for model (for transistors)
        if comp_type in ['Q', 'M', 'J', 'D', 'Z'] and len(nodes) > 1:
            # Last node might be model name
            if len(nodes) > len(nodes_for_type(comp_type)):
                model = nodes[-1]
                nodes = nodes[:-1]
        
        return Component(
            name=name,
            type=comp_type,
            nodes=nodes,
            value=value,
            parameters=params,
            model=model
        )
    
    def _is_value(self, token: str) -> bool:
        """Check if token looks like a SPICE value."""
        # Check for numeric values with optional units
        if self.VALUE_WITH_UNIT.match(token):
            return True
        # Check for expressions
        if token[0].isdigit() or token[0] in '+-.':
            return True
        return False
    
    def _parse_model_params(self, params_str: str) -> Dict[str, str]:
        """Parse model parameters."""
        params = {}
        # Simple parser for key=value pairs
        parts = params_str.split()
        for part in parts:
            if '=' in part:
                key, val = part.split('=', 1)
                params[key.upper()] = val
        return params
    
    def get_components_by_type(self, netlist: NetlistInfo, comp_type: str) -> List[Component]:
        """Get all components of a specific type."""
        return [c for c in netlist.components if c.type == comp_type]
    
    def get_node_connections(self, netlist: NetlistInfo) -> Dict[str, List[str]]:
        """Get all components connected to each node."""
        connections = {}
        
        for comp in netlist.components:
            for node in comp.nodes:
                if node not in connections:
                    connections[node] = []
                connections[node].append(comp.name)
        
        return connections


def nodes_for_type(comp_type: str) -> int:
    """Number of nodes for a component type."""
    node_counts = {
        'R': 2, 'C': 2, 'L': 2,  # Passive
        'V': 2, 'I': 2,  # Sources
        'D': 2,  # Diode
        'Q': 3,  # BJT (collector, base, emitter)
        'M': 4,  # MOSFET (drain, gate, source, bulk)
        'J': 3,  # JFET
        'Z': 3,  # MESFET
        'X': None,  # Subcircuit - variable
    }
    return node_counts.get(comp_type, 2)