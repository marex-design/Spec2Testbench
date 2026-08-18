"""Small, deterministic SPICE netlist parser used by the validator and simulator."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import re

@dataclass
class Component:
    name: str
    type: str
    nodes: List[str]
    value: Optional[str] = None
    parameters: Dict[str, str] = field(default_factory=dict)
    model: Optional[str] = None

@dataclass
class NetlistInfo:
    components: List[Component]
    nodes: List[str]
    models: Dict[str, Dict]
    subcircuits: Dict[str, List[Component]]
    top_level: bool = True

class NetlistParser:
    MODEL_PATTERN = re.compile(r"^\s*\.model\s+(\S+)\s+(\S+)\s*(.*)$", re.I)
    SUBCKT_START = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.I)
    SUBCKT_END = re.compile(r"^\s*\.ends\b", re.I)

    def parse(self, netlist_path: Path) -> NetlistInfo:
        return self.parse_content(Path(netlist_path).read_text(encoding="utf-8", errors="replace"))

    def parse_content(self, content: str) -> NetlistInfo:
        physical=[]
        buf=""
        for raw in content.splitlines():
            s=raw.strip()
            if not s or s.startswith("*"):
                continue
            if s.startswith("+") and buf:
                buf += " " + s[1:].strip()
            else:
                if buf: physical.append(buf)
                buf=s
        if buf: physical.append(buf)

        components=[]; models={}; subcircuits={}; current=None; subcomps=[]
        for line in physical:
            m=self.SUBCKT_START.match(line)
            if m:
                current=m.group(1); subcomps=[]; continue
            if self.SUBCKT_END.match(line):
                if current: subcircuits[current]=subcomps
                current=None; subcomps=[]; continue
            m=self.MODEL_PATTERN.match(line)
            if m:
                models[m.group(1)]={"type":m.group(2),"params":self._params(m.group(3))}; continue
            if line.startswith("."): continue
            comp=self._parse_component(line)
            if comp:
                (subcomps if current else components).append(comp)
        nodes=set()
        for comp in components + [c for xs in subcircuits.values() for c in xs]:
            nodes.update(n for n in comp.nodes if n != "0" and "=" not in n)
        return NetlistInfo(components=components,nodes=sorted(nodes),models=models,subcircuits=subcircuits)

    def _parse_component(self,line:str)->Optional[Component]:
        p=line.split()
        if not p or not p[0][0].isalpha(): return None
        name=p[0]; kind=name[0].upper()
        if kind=="M" and len(p)>=6:
            return Component(name,kind,p[1:5],None,self._kv(p[6:]),p[5])
        if kind=="Q" and len(p)>=5:
            return Component(name,kind,p[1:4],None,self._kv(p[5:]),p[4])
        if kind in {"R","C","L"} and len(p)>=4:
            return Component(name,kind,p[1:3],p[3],self._kv(p[4:]))
        if kind in {"V","I"} and len(p)>=4:
            return Component(name,kind,p[1:3]," ".join(p[3:]),{})
        if kind=="D" and len(p)>=4:
            return Component(name,kind,p[1:3],None,self._kv(p[4:]),p[3])
        if kind=="X" and len(p)>=3:
            # Last non-parameter token is subckt model, preceding tokens are terminals.
            non=[x for x in p[1:] if "=" not in x]
            model=non[-1] if non else None
            return Component(name,kind,non[:-1],None,self._kv(p[1:]),model)
        # conservative two-terminal fallback
        return Component(name,kind,p[1:3] if len(p)>=3 else p[1:], p[3] if len(p)>=4 else None,self._kv(p[4:]))

    @staticmethod
    def _kv(tokens):
        out={}
        for tok in tokens:
            if "=" in tok:
                k,v=tok.split("=",1); out[k.upper()]=v
        return out
    @staticmethod
    def _params(s): return NetlistParser._kv(re.findall(r"[A-Za-z][\w]*\s*=\s*[^\s()]+",s.replace(" =","=")))

    def get_components_by_type(self, netlist, comp_type):
        return [c for c in netlist.components if c.type.upper()==comp_type.upper()]
    def get_node_connections(self, netlist):
        out={}
        for c in netlist.components:
            for n in c.nodes: out.setdefault(n,[]).append(c.name)
        return out

def nodes_for_type(comp_type: str) -> int | None:
    return {"R":2,"C":2,"L":2,"V":2,"I":2,"D":2,"Q":3,"M":4,"J":3,"Z":3,"X":None}.get(comp_type.upper(),2)
