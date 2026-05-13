from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
from pathlib import Path

# Creer une netlist simple
netlist = '''RC Circuit Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.END
'''

netlist_path = Path("test_sim.cir")
netlist_path.write_text(netlist)

# Simuler
sim = NgspiceSimulator()
print("Simulation en cours...")
result = sim.run(netlist_path, None)

print(f"Succes: {result.get('success')}")
print(f"Resultats: {result.get('metrics')}")
if 'vout' in result.get('metrics', {}):
    print(f"Tension V(2): {result['metrics']['vout']:.3f} V")

netlist_path.unlink()
