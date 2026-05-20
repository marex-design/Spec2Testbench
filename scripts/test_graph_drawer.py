from pathlib import Path
from spec2testbench.infrastructure.schematic.graph.graph_drawer import draw_graph_schematic

netlist_path = Path("benchmark_netlists/lowpass_filter.cir")
netlist = netlist_path.read_text()

draw_graph_schematic(netlist, "results/graph_lowpass_filter.png")

print("Graph-based schematic generated.")