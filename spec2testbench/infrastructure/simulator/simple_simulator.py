"""
Simulateur SPICE simple utilisant ngspice en mode fichier.
"""

import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, Any, Optional


class SimpleSimulator:
    """Simulateur SPICE simple et fiable."""
    
    def __init__(self, ngspice_path: Optional[str] = None):
        self.ngspice_path = ngspice_path or r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"
        self._available = self._check()
    
    def _check(self) -> bool:
        """Vérifie si ngspice est disponible."""
        try:
            result = subprocess.run([self.ngspice_path, "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def run(self, netlist: str) -> Dict[str, Any]:
        """
        Exécute une simulation SPICE.
        
        Args:
            netlist: Contenu de la netlist SPICE
            
        Returns:
            Dictionnaire avec les résultats
        """
        if not self._available:
            return {"success": False, "error": "Ngspice not available"}
        
        # Créer un fichier temporaire pour la netlist
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
            f.write(netlist)
            netlist_path = Path(f.name)
        
        # Créer un fichier pour la sortie
        output_path = netlist_path.with_suffix('.out')
        
        try:
            # Exécuter ngspice avec redirection de sortie
            cmd = f'"{self.ngspice_path}" -b "{netlist_path}" > "{output_path}" 2>&1'
            subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
            
            # Lire la sortie
            output = ""
            if output_path.exists():
                output = output_path.read_text(encoding='utf-8', errors='ignore')
            
            # Extraire les résultats
            results = self._parse_output(output)
            results["success"] = True
            results["raw_output"] = output[:1000]
            
            return results
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # Nettoyer
            netlist_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
    
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse la sortie de ngspice pour extraire les tensions."""
        metrics = {}
        
        # Chercher les tensions au format v(2) = 5.000000e+00
        matches = re.findall(r'v\((\d+)\)\s*=\s*([-\d.e]+)', output, re.IGNORECASE)
        for node, value in matches:
            metrics[f'v{node}'] = float(value)
        
        # Chercher les courants
        matches = re.findall(r'i\((\w+)\)\s*=\s*([-\d.e]+)', output, re.IGNORECASE)
        for source, value in matches:
            metrics[f'i{source}'] = float(value)
        
        return {"metrics": metrics}
    
    def run_netlist_file(self, netlist_path: Path) -> Dict[str, Any]:
        """Exécute une simulation à partir d'un fichier netlist."""
        with open(netlist_path, 'r', encoding='utf-8') as f:
            netlist = f.read()
        return self.run(netlist)
