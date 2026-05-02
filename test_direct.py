import os
import subprocess

# Test direct
ngspice_path = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

print("=== TEST DIRECT NGSPICE ===\n")

# Test 1: Vérifier que le fichier existe
print(f"1. Fichier existe: {os.path.exists(ngspice_path)}")

# Test 2: Exécuter ngspice --version
try:
    result = subprocess.run([ngspice_path, "--version"], capture_output=True, text=True, timeout=5)
    output = result.stdout or result.stderr
    print(f"2. Version: {output.splitlines()[0] if output else 'unknown'}")
    print(f"   Return code: {result.returncode}")
except Exception as e:
    print(f"2. Erreur: {e}")

# Test 3: Importer et utiliser le simulateur
print("\n3. Test du simulateur PySpiceSimulator:")
from spec2testbench.infrastructure.simulator import PySpiceSimulator
sim = PySpiceSimulator(ngspice_path=ngspice_path)
info = sim.get_simulator_info()
print(f"   Status: {info['status']}")
print(f"   Available: {sim.is_available}")
