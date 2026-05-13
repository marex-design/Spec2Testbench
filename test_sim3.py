from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
from pathlib import Path

netlist = '''RC Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.END
'''

netlist_path = Path("test.cir")
netlist_path.write_text(netlist)

sim = NgspiceSimulator()
print(f"Simulateur disponible: {sim.is_available}")

result = sim.run(netlist_path)

print(f"Success: {result.get('success')}")
print(f"Metrics: {result.get('metrics')}")

netlist_path.unlink()
