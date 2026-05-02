import os

# Forcer le chemin ngspice
os.environ['NGSPICE_PATH'] = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

from spec2testbench.infrastructure.simulator import PySpiceSimulator
from spec2testbench.domain.entities.testbench import TestBench, Stimulus, AnalysisConfig, Measurement, AnalysisType
from pathlib import Path

# Créer une netlist
netlist = """Simple RC Circuit
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.END
"""
netlist_path = Path("test_rc.cir")
netlist_path.write_text(netlist)

# Créer un testbench
tb = TestBench(
    name="rc_dc_test",
    category="dc",
    circuit_name="RC_Circuit"
)

# Initialiser le simulateur
sim = PySpiceSimulator()

print("=== SIMULATION AVEC NGSPICE ===\n")
print(f"Simulateur disponible: {sim.is_available}")
print(f"Chemin: {sim.ngspice_path}\n")

# Exécuter la simulation
results = sim.run(netlist_path, tb)

print(f"Succès: {results.get('success', False)}")
print(f"Logs: {results.get('logs', [])[:5]}")

# Nettoyer
netlist_path.unlink()
