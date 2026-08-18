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
        """
        Exécute une simulation SPICE et retourne les métriques.
        Compatible avec le format attendu par VerificationPipeline.
        """
        if not self._available:
            return {"success": False, "error": "ngspice not available", "metrics": {}}
        
        # Créer un fichier temporaire pour la netlist
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
            f.write(netlist)
            netlist_path = Path(f.name)
        
        output_path = netlist_path.with_suffix('.out')
        
        try:
            # Exécuter ngspice
            cmd = f'ngspice -b "{netlist_path}" > "{output_path}" 2>&1'
            subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
            
            metrics = {}
            if output_path.exists():
                content = output_path.read_text(encoding='utf-8', errors='ignore')
                
                # Extraire les mesures .meas (format: nom_mesure = valeur)
                meas_pattern = r'([a-z_]+)\s*=\s*([0-9.e+-]+)'
                matches = re.findall(meas_pattern, content, re.IGNORECASE)
                
                for name, value_str in matches:
                    name = name.strip().lower()
                    try:
                        value = float(value_str.strip())
                        # Exclure les métriques système
                        if name not in ['temp', 'tnom', 'available', 'size', 'pages', 'stack', 'time']:
                            # Pour l'atténuation, prendre la valeur absolue
                            if 'attenuation' in name and value < 0:
                                value = abs(value)
                            metrics[name] = value
                    except ValueError:
                        pass
                
                # Si pas de mesures, essayer le format de tension
                if not metrics:
                    node_pattern = r'V\((\d+)\)\s+([-\d.e+]+)'
                    for match in re.finditer(node_pattern, content):
                        node = match.group(1)
                        try:
                            value = float(match.group(2).strip())
                            metrics[f'v{node}'] = value
                        except ValueError:
                            pass
            
            return {"success": True, "metrics": metrics}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Simulation timeout (30s)", "metrics": {}}
        except Exception as e:
            return {"success": False, "error": str(e), "metrics": {}}
        finally:
            # Nettoyer les fichiers temporaires
            netlist_path.unlink(missing_ok=True)
            if output_path.exists():
                output_path.unlink(missing_ok=True)


NgspiceSimulator = WSLSimulator
