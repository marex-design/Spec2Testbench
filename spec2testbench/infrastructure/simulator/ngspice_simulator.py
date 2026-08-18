# spec2testbench/infrastructure/simulator/ngspice_simulator.py

import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, Any, Optional

class NgspiceSimulator:
    def __init__(self):
        self.ngspice_path = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe"
        self._available = self._check()
    
    def _check(self) -> bool:
        try:
            result = subprocess.run([self.ngspice_path, '--version'], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def run(self, netlist_path: Path, testbench=None) -> Dict[str, Any]:
        if not self._available:
            return {'success': False, 'error': 'Ngspice not available', 'metrics': {}}
        
        output_file = Path(tempfile.mktemp(suffix='.txt'))
        
        # Executer ngspice avec redirection
        cmd = f'"{self.ngspice_path}" -b "{netlist_path}" > "{output_file}" 2>&1'
        
        try:
            subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
            
            metrics = {}
            if output_file.exists():
                content = output_file.read_text(encoding='utf-8', errors='ignore')
                
                # Extraire la derniere valeur de v(2) (pour DC sweep)
                matches = re.findall(r'\d+\s+([-\d.e]+)\s+([-\d.e]+)', content)
                if matches:
                    # Prendre la derniere valeur (fin du sweep)
                    vin, vout = matches[-1]
                    metrics['vin'] = float(vin)
                    metrics['vout'] = float(vout)
                    metrics['v2'] = float(vout)
                
                # Alternative: chercher format v(2) = valeur
                if not metrics:
                    match = re.search(r'v\(2\)\s*=\s*([-\d.e]+)', content, re.IGNORECASE)
                    if match:
                        metrics['vout'] = float(match.group(1))
                        metrics['v2'] = float(match.group(1))
            
            return {
                'success': True,
                'metrics': metrics,
                'raw_output': content[:500] if output_file.exists() else ""
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'metrics': {}}
        finally:
            output_file.unlink(missing_ok=True)
    
    def extract_metrics(self, results: Dict, testbench=None) -> Dict[str, float]:
        return results.get('metrics', {})
    
    def get_simulator_info(self) -> Dict[str, str]:
        return {'name': 'Ngspice', 'available': str(self._available)}
    
    def supports_pvt_analysis(self) -> bool:
        return True
