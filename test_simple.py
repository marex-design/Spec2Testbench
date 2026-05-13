import subprocess
from pathlib import Path

ngspice = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

netlist = '''Test circuit
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.OP
.END
'''

netlist_path = Path("test.cir")
netlist_path.write_text(netlist)

result = subprocess.run([ngspice, "-b", str(netlist_path)], capture_output=True, text=True)

print("=== SORTIE ===")
print(result.stderr if result.stderr else result.stdout)

netlist_path.unlink()
