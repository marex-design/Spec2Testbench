from dataclasses import dataclass, field
from spec2testbench.infrastructure.schematic.netlist_parser import NetlistParser


@dataclass
class CircuitComponent:
    name: str
    kind: str
    nodes: list[str]
    value: str | None = None
    model: str | None = None


@dataclass
class CircuitGraph:
    components: list[CircuitComponent] = field(default_factory=list)
    nets: dict[str, list[str]] = field(default_factory=dict)

    def add_component(self, component: CircuitComponent):
        self.components.append(component)

        for net in component.nodes:
            self.nets.setdefault(net, []).append(component.name)

    def by_kind(self, kind: str):
        return [c for c in self.components if c.kind.upper() == kind.upper()]

    def has_net(self, net: str):
        return net in self.nets


class GraphBuilder:
    def build(self, netlist: str) -> CircuitGraph:
        parsed = NetlistParser().parse(netlist)
        graph = CircuitGraph()

        for comp in parsed.components:
            graph.add_component(
                CircuitComponent(
                    name=comp.name,
                    kind=comp.type.upper(),
                    nodes=comp.nodes,
                    value=comp.value,
                    model=getattr(comp, "model", None),
                )
            )

        return graph