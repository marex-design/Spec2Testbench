from dataclasses import dataclass, field


@dataclass
class GraphComponent:
    name: str
    type: str
    nodes: list[str]
    value: str | None = None
    model: str | None = None


@dataclass
class ElectricalGraph:
    components: list[GraphComponent] = field(default_factory=list)
    nets: dict[str, list[str]] = field(default_factory=dict)

    def add_component(self, component: GraphComponent):
        self.components.append(component)

        for node in component.nodes:
            if node not in self.nets:
                self.nets[node] = []
            self.nets[node].append(component.name)

    def component_count(self) -> int:
        return len(self.components)

    def net_count(self) -> int:
        return len(self.nets)