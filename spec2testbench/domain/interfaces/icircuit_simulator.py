# spec2testbench/domain/interfaces/icircuit_simulator.py

"""
Interface pour le simulateur de circuits SPICE.
Définit le contrat que doit respecter toute implémentation de simulateur.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..entities.testbench import TestBench


class ICircuitSimulator(ABC):
    """
    Interface pour la simulation de circuits SPICE.
    
    Cette interface est implémentée par:
    - PySpiceSimulator: utilise Ngspice via PySpice
    - XyceSimulator: utilise Sandia Xyce
    - SpectreSimulator: utilise Cadence Spectre
    - HSPICESimulator: utilise Synopsys HSPICE
    
    Le Domain Layer ne sait pas quel simulateur est utilisé.
    """
    
    @abstractmethod
    def run(self,
            netlist_path: Path,
            testbench: TestBench,
            output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Exécute une simulation selon le testbench.
        
        Args:
            netlist_path: Chemin vers le fichier netlist SPICE
            testbench: TestBench avec la configuration de simulation
            output_dir: Répertoire de sortie pour les résultats (optionnel)
            
        Returns:
            Dictionnaire contenant:
                - 'metrics': métriques extraites
                - 'waveforms': données des formes d'onde
                - 'logs': logs de simulation
                - 'success': booléen de succès
        """
        pass
    
    @abstractmethod
    def extract_metrics(self, 
                        raw_results: Any,
                        testbench: TestBench) -> Dict[str, float]:
        """
        Extrait les métriques des résultats bruts.
        
        Args:
            raw_results: Résultats bruts du simulateur
            testbench: TestBench contenant la liste des mesures à extraire
            
        Returns:
            Dictionnaire {nom_metrique: valeur}
        """
        pass
    
    @abstractmethod
    def get_waveform(self, 
                     results: Any,
                     node: str,
                     analysis_type: str = "tran") -> Dict[str, list]:
        """
        Récupère les données d'une forme d'onde.
        
        Args:
            results: Résultats de la simulation
            node: Nom du noeud (ex: 'Vout')
            analysis_type: Type d'analyse ('tran', 'ac', 'dc')
            
        Returns:
            Dictionnaire avec 'time'/'frequency' et 'voltage'/'magnitude'
        """
        pass
    
    @abstractmethod
    def check_convergence(self, logs: str) -> bool:
        """
        Vérifie si la simulation a convergé.
        
        Args:
            logs: Logs de la simulation
            
        Returns:
            True si la simulation a convergé
        """
        pass
    
    @abstractmethod
    def get_simulator_info(self) -> Dict[str, str]:
        """
        Retourne des informations sur le simulateur.
        
        Returns:
            Dictionnaire avec 'name', 'version', 'backend'
        """
        pass
    
    @abstractmethod
    def supports_pvt_analysis(self) -> bool:
        """
        Vérifie si le simulateur supporte l'analyse PVT.
        
        Returns:
            True si PVT est supporté
        """
        pass