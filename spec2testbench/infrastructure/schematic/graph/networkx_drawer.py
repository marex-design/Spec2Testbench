from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

from spec2testbench.infrastructure.schematic.graph.networkx_builder import NetworkXBuilder


def draw_networkx_graph(netlist: str, output_path: str) -> str:
    graph = NetworkXBuilder().build(netlist)

    if graph.number_of_nodes() == 0:
        raise ValueError("Empty graph")

    pos = nx.spring_layout(graph, seed=42, k=1.4)

    component_nodes = [
        node for node, data in graph.nodes(data=True)
        if data.get("kind") == "component"
    ]

    net_nodes = [
        node for node, data in graph.nodes(data=True)
        if data.get("kind") == "net"
    ]

    labels = {
        node: graph.nodes[node].get("name", node)
        for node in graph.nodes
    }

    plt.figure(figsize=(12, 8))

    nx.draw_networkx_edges(graph, pos, width=1.5)

    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=component_nodes,
        node_shape="s",
        node_size=1400,
    )

    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=net_nodes,
        node_shape="o",
        node_size=700,
    )

    nx.draw_networkx_labels(
        graph,
        pos,
        labels=labels,
        font_size=8,
    )

    plt.axis("off")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    return str(out)