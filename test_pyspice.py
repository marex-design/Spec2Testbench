from PySpice.Spice.Netlist import Circuit

print("=== TEST PySpice + NGSPICE ===\n")

# Creer un circuit simple
circuit = Circuit('Test RC')
circuit.V('1', '1', circuit.gnd, 5)
circuit.R('1', '1', '2', 1e3)
circuit.C('1', '2', circuit.gnd, 1e-9)

print("1. Circuit cree avec succes")

# Creer le simulateur
simulator = circuit.simulator()

print("2. Simulateur initialise")

# Tester une simulation DC
print("\n3. Lancement simulation DC...")
analysis = simulator.operating_point()

print("4. Simulation DC reussie !")
node_voltage = float(analysis.nodes["2"])
print(f"   Tension au noeud 2: {node_voltage:.3f} V")

print("\n✅ PySpice + ngspice fonctionnent !")
