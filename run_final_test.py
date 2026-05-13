#!/usr/bin/env python3
"""Test final du simulateur ngspice"""

from spec2testbench.infrastructure.simulator.ngspice_simulator import NgspiceSimulator
from pathlib import Path

def main():
    print("=" * 50)
    print("TEST FINAL DU SIMULATEUR NGSPICE")
    print("=" * 50)
    
    # Netlist avec DC sweep
    netlist = '''Final Simulation Test
V1 1 0 DC 5
R1 1 2 1k
C1 2 0 1n
.DC V1 0 5 0.5
.PRINT DC V(2)
.END
'''
    
    netlist_path = Path("test_final.cir")
    netlist_path.write_text(netlist)
    
    print(f"\n1. Netlist creee: {netlist_path}")
    print("   Contenu de la netlist:")
    for line in netlist.strip().split('\n'):
        print(f"     {line}")
    
    print("\n2. Initialisation du simulateur...")
    sim = NgspiceSimulator()
    print(f"   Simulateur disponible: {sim.is_available}")
    
    print("\n3. Execution de la simulation...")
    result = sim.run(netlist_path)
    
    print(f"\n4. Resultat:")
    print(f"   Success: {result.get('success')}")
    print(f"   Metrics: {result.get('metrics')}")
    
    if result.get('metrics', {}).get('vout'):
        vout = result['metrics']['vout']
        print(f"\n   ✅ TENSION EXTRAITE: V(2) = {vout:.3f} V")
        print("\n🎉 SIMULATION REUSSIE !")
    else:
        print("\n   ⚠️ Aucune tension extraite")
        if result.get('raw_output'):
            print("\n   Raw output (debogage):")
            print("   " + "-" * 40)
            for line in result['raw_output'].split('\n')[:20]:
                print(f"   {line}")
            print("   " + "-" * 40)
    
    # Nettoyer
    netlist_path.unlink()
    print(f"\n5. Nettoyage: {netlist_path} supprime")

if __name__ == "__main__":
    main()
