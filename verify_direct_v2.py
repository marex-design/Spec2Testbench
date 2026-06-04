#!/usr/bin/env python3
"""Vérification directe des circuits SPICE"""

import subprocess
import re
import yaml
import sys
from pathlib import Path

def verify_circuit(spec_file, netlist_file):
    # Lire les specs
    with open(spec_file) as f:
        specs = yaml.safe_load(f)
    
    # Lire la netlist
    netlist_content = Path(netlist_file).read_text()
    
    # Exécuter la simulation
    result = subprocess.run(['ngspice', '-b', netlist_file], 
                           capture_output=True, text=True)
    output = result.stdout + result.stderr
    
    # Extraire les mesures
    measurements = {}
    for match in re.finditer(r'([a-z_]+)\s*=\s*([0-9.e+-]+)', output, re.I):
        name = match.group(1).lower()
        value = float(match.group(2))
        if name not in ['temp', 'tnom', 'available', 'size', 'pages', 'stack']:
            if 'attenuation' in name and value < 0:
                value = abs(value)
            measurements[name] = value
    
    print(f"\n{'='*50}")
    print(f"Vérification: {specs.get('name', 'circuit')}")
    print(f"{'='*50}")
    
    passed = 0
    total = len(specs['performance_targets'])
    
    for metric, spec in specs['performance_targets'].items():
        if metric in measurements:
            value = measurements[metric]
            min_val = spec.get('min')
            max_val = spec.get('max')
            
            if min_val is not None and max_val is not None:
                if min_val <= value <= max_val:
                    print(f"  ✅ {metric}: {value:.2e} (OK - [{min_val}, {max_val}])")
                    passed += 1
                else:
                    print(f"  ❌ {metric}: {value:.2e} (HORS - [{min_val}, {max_val}])")
            elif min_val is not None:
                if value >= min_val:
                    print(f"  ✅ {metric}: {value:.2e} (OK - >= {min_val})")
                    passed += 1
                else:
                    print(f"  ❌ {metric}: {value:.2e} (HORS - < {min_val})")
            elif max_val is not None:
                if value <= max_val:
                    print(f"  ✅ {metric}: {value:.2e} (OK - <= {max_val})")
                    passed += 1
                else:
                    print(f"  ❌ {metric}: {value:.2e} (HORS - > {max_val})")
        else:
            print(f"  ⚠️ {metric}: non trouvé")
    
    print(f"\nRésultat: {passed}/{total} OK")
    print(f"{'='*50}\n")
    return passed == total

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python verify_direct_v2.py <spec.yaml> <netlist.spice>")
        sys.exit(1)
    success = verify_circuit(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
