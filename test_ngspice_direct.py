import subprocess
import tempfile
from pathlib import Path

ngspice_exe = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

# Creer une netlist simple
netlist = '''Simple RC Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.PRINT DC V(2)
.END
'''

with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
    f.write(netlist)
    netlist_path = Path(f.name)

print(f"Netlist: {netlist_path}")
print("\nExecution de ngspice...")

result = subprocess.run(
    [ngspice_exe, '-b', str(netlist_path)],
    capture_output=True,
    text=True,
    timeout=30
)

print("\n=== SORTIE NGSPICE ===")
print(result.stdout if result.stdout else result.stderr)

# Nettoyer
netlist_path.unlink()
print("\n✅ Test termine")
