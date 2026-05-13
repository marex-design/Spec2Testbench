import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, Any


class WSLSimulator:
    def __init__(self):
        self._available = self._check()
    
    def _check(self) -> bool:
        try:
            result = subprocess.run(["ngspice", "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def run(self, netlist: str) -> Dict[str, Any]:
        if not self._available:
            return {"success": False, "error": "ngspice not available", "metrics": {}}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
            f.write(netlist)
            netlist_path = Path(f.name)
        
        output_path = netlist_path.with_suffix('.out')
        
        try:
            cmd = f'ngspice -b "{netlist_path}" > "{output_path}" 2>&1'
            subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
            
            metrics = {}
            if output_path.exists():
                content = output_path.read_text(encoding='utf-8', errors='ignore')
                
                # Regex plus flexible pour capturer le nombre complet
                # Format: V(2)                             5.000000e+00
                for line in content.split('\n'):
                    # Chercher V(1), V(2), etc. avec n'importe quel format de nombre
                    match = re.search(r'V\((\d+)\)\s+([-\d.e+]+)', line)
                    if match:
                        node = match.group(1)
                        value_str = match.group(2)
                        # Nettoyer la valeur
                        value_str = value_str.strip()
                        try:
                            metrics[f'v{node}'] = float(value_str)
                            print(f"✓ Tension v{node} = {value_str}")
                        except ValueError:
                            # Essayer de parser sans le dernier caractère
                            try:
                                metrics[f'v{node}'] = float(value_str[:-1])
                                print(f"✓ Tension v{node} = {value_str[:-1]}")
                            except:
                                print(f"Warning: could not convert '{value_str}'")
            
            return {"success": True, "metrics": metrics}
        except Exception as e:
            return {"success": False, "error": str(e), "metrics": {}}
        finally:
            netlist_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


NgspiceSimulator = WSLSimulator
