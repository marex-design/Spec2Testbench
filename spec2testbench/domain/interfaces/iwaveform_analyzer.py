# spec2testbench/domain/interfaces/iwaveform_analyzer.py

"""
Interface pour l'analyseur de formes d'onde multimodal (Module 3).
Définit le contrat pour l'analyse d'images par MLLM.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..value_objects.multimodal_result import MultimodalResult, WaveformAnalysis
from ..entities.specification import Specification


class IWaveformAnalyzer(ABC):
    """
    Interface pour l'analyse multimodale de formes d'onde.
    
    Cette interface est implémentée par:
    - GPT4VisionAnalyzer: utilise OpenAI GPT-4V
    - GeminiVisionAnalyzer: utilise Google Gemini
    - ClaudeVisionAnalyzer: utilise Anthropic Claude
    - RuleBasedAnalyzer: analyse algorithmique sans LLM
    
    Le Domain Layer ne sait pas quel modèle multimodal est utilisé.
    """
    
    @abstractmethod
    def analyze(self,
                image_path: Path,
                context: Optional[Dict[str, Any]] = None) -> WaveformAnalysis:
        """
        Analyse une image de forme d'onde.
        
        Args:
            image_path: Chemin vers l'image PNG
            context: Contexte optionnel (type de circuit, métriques attendues)
            
        Returns:
            WaveformAnalysis: Analyse structurée de la forme d'onde
        """
        pass
    
    @abstractmethod
    def check_specification(self,
                           image_path: Path,
                           metric_name: str,
                           expected_min: float,
                           expected_max: float,
                           unit: str) -> MultimodalResult:
        """
        Vérifie si une forme d'onde respecte une spécification.
        
        Args:
            image_path: Chemin vers l'image PNG
            metric_name: Nom de la métrique à vérifier
            expected_min: Valeur minimale attendue
            expected_max: Valeur maximale attendue
            unit: Unité de mesure
            
        Returns:
            MultimodalResult: Résultat complet avec diagnostic
        """
        pass
    
    @abstractmethod
    def diagnose_failure(self,
                        image_path: Path,
                        specification: Specification,
                        failed_metrics: List[str]) -> MultimodalResult:
        """
        Diagnostique la cause d'un échec de test.
        
        Args:
            image_path: Chemin vers l'image de la forme d'onde qui a échoué
            specification: Spécifications du circuit
            failed_metrics: Liste des métriques qui ont échoué
            
        Returns:
            MultimodalResult: Diagnostic avec recommandations
        """
        pass
    
    @abstractmethod
    def extract_metrics_from_image(self,
                                   image_path: Path,
                                   metrics: List[str]) -> Dict[str, float]:
        """
        Extrait des métriques spécifiques d'une image.
        
        Args:
            image_path: Chemin vers l'image PNG
            metrics: Liste des métriques à extraire (ex: ['amplitude', 'frequency'])
            
        Returns:
            Dictionnaire {metrique: valeur}
        """
        pass
    
    @abstractmethod
    def is_image_interpretable(self, image_path: Path) -> bool:
        """
        Vérifie si l'image est interprétable par le MLLM.
        
        Args:
            image_path: Chemin vers l'image
            
        Returns:
            True si l'image peut être analysée
        """
        pass