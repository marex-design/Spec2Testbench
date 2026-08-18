from spec2testbench.infrastructure.schematic.netlist_parser import NetlistParser
from spec2testbench.infrastructure.schematic.graph.electrical_graph import (
    ElectricalGraph,
    GraphComponent,
)


class GraphBuilder:
    def build_from_netlist(self, netlist: str) -> ElectricalGraph:
        parsed = NetlistParser().parse(netlist)

        graph = ElectricalGraph()

        for comp in parsed.components:
            graph.add_component(
                GraphComponent(
                    name=comp.name,
                    type=comp.type,
                    nodes=comp.nodes,
                    value=comp.value,
                    model=getattr(comp, "model", None),
                )
            )

        return graph