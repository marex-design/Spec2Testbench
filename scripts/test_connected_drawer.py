from pathlib import Path
from spec2testbench.infrastructure.schematic.connected_drawer import netlist_to_connected_schematic

netlist_path = Path("benchmark_netlists/lowpass_filter.cir")
netlist = netlist_path.read_text()

netlist_to_connected_schematic(
    netlist,
    "results/connected_lowpass_filter.png"
)

print("Connected schematic generated.")