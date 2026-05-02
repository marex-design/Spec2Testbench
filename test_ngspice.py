import os
os.environ['NGSPICE_PATH'] = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"

from spec2testbench.infrastructure.simulator import PySpiceSimulator

sim = PySpiceSimulator()
info = sim.get_simulator_info()

print("=== TEST SIMULATEUR ===\n")
print(f'Status: {info["status"]}')
print(f'Path: {info["path"]}')
print(f'Available: {sim.is_available}')
