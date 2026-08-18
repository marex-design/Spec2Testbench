import networkx as nx

from spec2testbench.infrastructure.schematic.netlist_parser import NetlistParser


class NetworkXBuilder:
    def build(self, netlist: str) -> nx.Graph:
        parsed = NetlistParser().parse(netlist)

        graph = nx.Graph()

        for comp in parsed.components:
            comp_node = f"COMP:{comp.name}"
            graph.add_node(
                comp_node,
                kind="component",
                name=comp.name,
                type=comp.type,
                value=comp.value,
                model=getattr(comp, "model", None),
            )

            for net in comp.nodes:
                net_node = f"NET:{net}"
                graph.add_node(
                    net_node,
                    kind="net",
                    name=net,
                )

                graph.add_edge(comp_node, net_node)

        return graph