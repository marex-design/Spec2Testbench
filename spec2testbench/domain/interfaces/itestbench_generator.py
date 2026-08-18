# spec2testbench/domain/interfaces/itestbench_generator.py

"""
Interface pour le générateur de testbenches (Module 1).
Définit le contrat que doit respecter toute implémentation de TestBenchGen.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path

from ..entities.specification import Specification
from ..entities.testbench import TestBench


class ITestBenchGenerator(ABC):
    """
    Interface pour la génération automatique de testbenches.
    
    Cette interface est implémentée par:
    - LLMTestBenchGenerator: utilise un LLM (OpenAI, Anthropic)
    - TemplateTestBenchGenerator: utilise des templates pré-définis
    - RuleBasedTestBenchGenerator: utilise des règles heuristiques
    
    Le Domain Layer (nos entités) ne connaît pas l'implémentation.
    """
    
    @abstractmethod
    def generate(self, specification: Specification) -> TestBench:
        """
        Génère un testbench complet à partir des spécifications.
        
        Args:
            specification: Spécifications du circuit (entrée utilisateur)
            
        Returns:
            TestBench: Plan de test complet et exécutable
            
        Raises:
            GenerationError: Si la génération échoue
        """
        pass
    
    @abstractmethod
    def generate_for_category(self, 
                              specification: Specification,
                              category: str) -> TestBench:
        """
        Génère un testbench pour une catégorie spécifique.
        
        Args:
            specification: Spécifications du circuit
            category: Catégorie ('dc', 'ac', 'transient', 'pvt', 'spectral', 'differential')
            
        Returns:
            TestBench: Testbench spécifique à la catégorie
        """
        pass
    
    @abstractmethod
    def generate_from_text(self, text: str) -> Specification:
        """
        Extrait les spécifications d'un texte en langage naturel.
        
        Args:
            text: Description textuelle du circuit souhaité
            
        Returns:
            Specification: Spécifications extraites par le LLM
        """
        pass
    
    @abstractmethod
    def get_supported_circuit_types(self) -> List[str]:
        """
        Retourne la liste des types de circuits supportés.
        
        Returns:
            Liste des noms de CircuitType supportés
        """
        pass
    
    @abstractmethod
    def get_supported_categories(self) -> List[str]:
        """
        Retourne la liste des catégories de tests supportées.
        
        Returns:
            Liste des catégories ('dc', 'ac', 'transient', etc.)
        """
        pass
    
    @abstractmethod
    def validate_specification(self, specification: Specification) -> tuple:
        """
        Valide qu'une spécification est générable par ce générateur.
        
        Args:
            specification: Spécification à valider
            
        Returns:
            (is_valid, list_of_errors)
        """
        pass