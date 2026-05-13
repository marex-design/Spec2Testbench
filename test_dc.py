import subprocess
import tempfile
import re
from pathlib import Path

ngspice_exe = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

# Creer une netlist avec analyse DC (produit une sortie)
netlist = '''Simple DC Sweep Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.DC V1 0 5 0.1
.PRINT DC V(2)
.END
'''

netlist_path = Path("test_dc_circuit.cir")
netlist_path.write_text(netlist)

print(f"Netlist: {netlist_path.absolute()}")
print("Contenu de la netlist:")
print(netlist)
print("\nExecution de ngspice...")

# Executer ngspice
result = subprocess.run(
    [ngspice_exe, '-b', str(netlist_path.absolute())],
    capture_output=True,
    text=True
)

print("\n=== SORTIE STANDARD ===")
print(result.stdout if result.stdout else "(vide)")

print("\n=== SORTIE ERREUR ===")
print(result.stderr if result.stderr else "(vide)")

print(f"\nCode de retour: {result.returncode}")

netlist_path.unlink()
