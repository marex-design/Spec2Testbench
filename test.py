# test.py
"""
Test the real SPICE simulator with Ngspice.
"""

from pathlib import Path
from spec2testbench.infrastructure.simulator import PySpiceSimulator
from spec2testbench.domain.entities.testbench import (
    TestBench, Stimulus, AnalysisConfig, Measurement, AnalysisType
)

print("=== TEST SIMULATEUR RÉEL AVEC NGSPICE ===\n")

# Créer un fichier netlist simple pour tester
netlist_content = """Simple RC Circuit
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.END
"""

netlist_path = Path("test_rc.cir")
netlist_path.write_text(netlist_content)

# Créer un testbench simple
testbench = TestBench(
    name="rc_test",
    category="dc",
    circuit_name="RC Circuit",
    stimuli=[
        Stimulus(name="V1", type="dc", parameters={"value": 5}, node_positive="1", node_negative="0")
    ],
    analyses=[
        AnalysisConfig(type=AnalysisType.DC, parameters={"source": "V1", "start": 0, "stop": 5, "step": 0.1}),
        AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={"step_time": "1n", "end_time": "100n"})
    ],
    measurements=[
        Measurement(name="vout_dc", expression="V(2)", node="2")
    ]
)

# Initialiser le simulateur
print("Initialisation du simulateur...")
simulator = PySpiceSimulator()

# Afficher les infos
info = simulator.get_simulator_info()
print(f"\nSimulator Info:")
print(f"  Name: {info['name']}")
print(f"  Version: {info['version']}")
print(f"  Status: {info['status']}")
print(f"  Path: {info['path']}")
print(f"  Available: {simulator.is_available}")

# Exécuter la simulation
print("\n" + "="*50)
print("Exécution de la simulation...")
print("="*50)

results = simulator.run(netlist_path, testbench)

print(f"\nRésultats:")
print(f"  Success: {results.get('success', False)}")
print(f"  Metrics: {results.get('metrics', {})}")
print(f"  Logs: {len(results.get('logs', []))} lines")
print(f"  Errors: {len(results.get('errors', []))} lines")

if results.get('errors'):
    print("\n  Errors details:")
    for err in results['errors'][:5]:
        print(f"    - {err}")

# Nettoyer
netlist_path.unlink(missing_ok=True)

print("\n✅ Test terminé")