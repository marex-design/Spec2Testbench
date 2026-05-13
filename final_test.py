from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
from pathlib import Path

# Netlist avec DC sweep (format qui donne des resultats)
netlist = '''Final Simulation Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.DC V1 0 5 0.5
.PRINT DC V(2)
.END
'''

netlist_path = Path("final_sim.cir")
netlist_path.write_text(netlist)

sim = NgspiceSimulator()
print("=" * 50)
print("TEST FINAL DU SIMULATEUR")
print("=" * 50)
print(f"\nSimulateur disponible: {sim.is_available}")

result = sim.run(netlist_path)
print(f"Success: {result.get('success')}")
print(f"Metrics: {result.get('metrics')}")

if result.get('metrics', {}).get('vout'):
    print(f"\n✅ TENSION EXTRAITE: V(2) = {result['metrics']['vout']:.3f} V")
    print("\n🎉 SIMULATION REUSSIE !")
else:
    print("\n⚠️ Aucune tension extraite, verification du parsing...")

netlist_path.unlink()
