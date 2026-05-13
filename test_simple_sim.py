from spec2testbench.infrastructure.simulator.simple_simulator import SimpleSimulator

sim = SimpleSimulator()
print(f"Simulateur disponible: {sim.is_available}")

# Netlist simple
netlist = '''Test DC
V1 1 0 DC 5
R1 1 2 1k
.OP
.END
'''

result = sim.run(netlist)
print(f"Success: {result.get('success')}")
print(f"Metrics: {result.get('metrics')}")

if result.get('metrics'):
    for name, value in result['metrics'].items():
        print(f"  {name} = {value:.3f}")
