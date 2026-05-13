import subprocess
import tempfile
import re
from pathlib import Path

ngspice_exe = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

# Creer une netlist simple (sans .CONTROL)
netlist = '''Simple RC Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.END
'''

# Creer un fichier temporaire
netlist_path = Path(tempfile.mktemp(suffix='.cir'))
netlist_path.write_text(netlist)

# Creer un fichier de sortie
output_path = Path(tempfile.mktemp(suffix='.out'))

print(f"Netlist: {netlist_path}")
print(f"Output: {output_path}")

# Executer ngspice avec redirection de sortie
cmd = f'{ngspice_exe} -b "{netlist_path}" > "{output_path}" 2>&1'
print(f"\nCommande: {cmd}")

result = subprocess.run(
    cmd,
    shell=True,
    capture_output=True,
    text=True,
    timeout=30
)

# Lire le fichier de sortie
if output_path.exists():
    output = output_path.read_text()
    print("\n=== RESULTATS NGSPICE ===")
    print(output[:1000])  # Afficher les 1000 premiers caracteres
    
    # Extraire les tensions
    for line in output.splitlines():
        # Format: v(2) = 5.000000e+00
        match = re.search(r'v\((\d+)\)\s*=\s*([-\d.e]+)', line, re.IGNORECASE)
        if match:
            node = match.group(1)
            voltage = float(match.group(2))
            print(f"Tension au noeud {node}: {voltage:.3f} V")

# Nettoyer
netlist_path.unlink()
output_path.unlink()

print("\n✅ Test termine")
