# spec2testbench/domain/interfaces/ispec_checker.py

"""
Interface pour le vérificateur de spécifications (Module 2).
Définit le contrat que doit respecter toute implémentation de SpecChecker.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from ..entities.specification import Specification
from ..value_objects.verdict import Verdict, CheckResult


class ISpecChecker(ABC):
    """
    Interface pour la vérification des spécifications.
    
    Cette interface est implémentée par:
    - MathBasedSpecChecker: calcul direct à partir des résultats
    - LLMBasedSpecChecker: utilise un LLM pour l'évaluation
    - HybridSpecChecker: combine les deux approches
    
    Le Domain Layer ne connaît pas comment les vérifications sont faites.
    """
    
    @abstractmethod
    def verify(self, 
               simulation_results: Dict[str, Any],
               specification: Specification) -> List[CheckResult]:
        """
        Vérifie les résultats de simulation contre les spécifications.
        
        Args:
            simulation_results: Résultats bruts de la simulation
            specification: Spécifications attendues
            
        Returns:
            List[CheckResult]: Liste des résultats de vérification
        """
        pass
    
    @abstractmethod
    def verify_single_metric(self,
                             metric_name: str,
                             measured_value: float,
                             specification: Specification) -> CheckResult:
        """
        Vérifie une métrique unique.
        
        Args:
            metric_name: Nom de la métrique à vérifier
            measured_value: Valeur mesurée
            specification: Spécifications contenant la valeur attendue
            
        Returns:
            CheckResult: Résultat de la vérification
        """
        pass
    
    @abstractmethod
    def extract_metrics(self, 
                        simulation_results: Dict[str, Any],
                        specification: Specification) -> Dict[str, float]:
        """
        Extrait les métriques pertinentes des résultats de simulation.
        
        Args:
            simulation_results: Résultats bruts de la simulation
            specification: Spécifications pour savoir quelles métriques extraire
            
        Returns:
            Dictionnaire {nom_metrique: valeur}
        """
        pass
    
    @abstractmethod
    def generate_assertions(self, specification: Specification) -> str:
        """
        Génère du code d'assertion Python à partir des spécifications.
        
        Args:
            specification: Spécifications
            
        Returns:
            Code Python contenant les fonctions d'assertion
        """
        pass
    
    @abstractmethod
    def get_failed_metrics(self, 
                           check_results: List[CheckResult]) -> List[CheckResult]:
        """
        Retourne uniquement les métriques qui ont échoué.
        
        Args:
            check_results: Liste complète des résultats
            
        Returns:
            Liste des résultats FAIL et WARNING
        """
        pass
    
    @abstractmethod
    def summary(self, check_results: List[CheckResult]) -> dict:
        """
        Génère un résumé des vérifications.
        
        Args:
            check_results: Liste des résultats
            
        Returns:
            Dictionnaire avec statistiques (pass_count, fail_count, etc.)
        """
        pass