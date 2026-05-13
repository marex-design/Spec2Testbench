print('=== SPEC2TESTBENCH - VERIFICATION FINALE ===\n')

# 1. Domain
from spec2testbench.domain.value_objects.circuit_type import CircuitType
print(f'1. Domain: {len(CircuitType.all_circuit_types())} types de circuits')

# 2. TestBenchGen
from spec2testbench.infrastructure.testbench import TestBenchGenerator
gen = TestBenchGenerator(use_llm=False)
print('2. TestBenchGen: OK')

# 3. Simulateur
from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
sim = NgspiceSimulator()
print(f'3. Simulateur NGSPICE: {"OK" if sim.is_available else "NON"}')

print('\n✅ Framework pret a l\'emploi!')
