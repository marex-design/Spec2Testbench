from pathlib import Path

from spec2testbench.infrastructure.schematic.graph.networkx_drawer import draw_networkx_graph

netlist_path = Path("benchmark_netlists/lowpass_filter.cir")
netlist = netlist_path.read_text()

draw_networkx_graph(
    netlist,
    "results/networkx_lowpass_filter.png",
)

print("NetworkX graph generated.")