from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
from pathlib import Path

# Utiliser DC sweep au lieu de .OP
netlist = '''DC Sweep Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.DC V1 0 5 0.1
.PRINT DC V(2)
.END
'''

netlist_path = Path("test_dc_final.cir")
netlist_path.write_text(netlist)

sim = NgspiceSimulator()
print(f"Simulateur disponible: {sim.is_available}")

result = sim.run(netlist_path)
print(f"Success: {result.get('success')}")
print(f"Metrics: {result.get('metrics')}")
print(f"Tension V(2): {result.get('metrics', {}).get('v2', 'N/A')} V")

netlist_path.unlink()
