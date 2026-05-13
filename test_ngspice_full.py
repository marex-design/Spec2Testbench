import subprocess
import tempfile
import re
from pathlib import Path

ngspice_exe = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

# Creer une netlist avec sortie
netlist = '''Simple RC Circuit Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n

* DC analysis
.DC V1 0 5 0.1

* Control section for output
.CONTROL
run
print v(2)
.ENDC
.END
'''

with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
    f.write(netlist)
    netlist_path = Path(f.name)

print(f"Netlist: {netlist_path}")

# Executer ngspice
result = subprocess.run(
    [ngspice_exe, '-b', str(netlist_path)],
    capture_output=True,
    text=True,
    timeout=30
)

print("\n=== RESULTATS NGSPICE ===")
output = result.stdout or result.stderr
print(output)

# Extraire les tensions
voltages = []
for line in output.splitlines():
    # Chercher les lignes comme "v(2) = 2.500000e+00"
    match = re.search(r'v\(2\)\s*=\s*([-\d.e]+)', line, re.IGNORECASE)
    if match:
        voltages.append(float(match.group(1)))
        print(f"Tension extraite: {voltages[-1]:.3f} V")

# Nettoyer
netlist_path.unlink()

print(f"\n✅ Test termine. {len(voltages)} tensions extraites.")
