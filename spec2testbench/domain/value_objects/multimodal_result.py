# spec2testbench/domain/value_objects/multimodal_result.py

"""
Résultat de l'analyse multimodale de forme d'onde.
Structure le diagnostic produit par le MLLM (GPT-4V, Gemini, Claude Vision).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from .verdict import Verdict


class WaveformType(Enum):
    """
    Types de formes d'onde identifiables par le MLLM.
    """
    SINUSOIDAL = "sinusoidal"
    """Onde sinusoïdale pure"""
    
    SQUARE = "square"
    """Onde carrée"""
    
    TRIANGULAR = "triangular"
    """Onde triangulaire / dents de scie"""
    
    DAMPED_SINUSOIDAL = "damped_sinusoidal"
    """Sinusoïdale amortie (oscillations qui décroissent)"""
    
    RINGING = "ringing"
    """Oscillations parasites après un front"""
    
    CLIPPED = "clipped"
    """Signal écrêté (saturation haute ou basse)"""
    
    SLEW_LIMITED = "slew_limited"
    """Signal limité en pente (slew rate insuffisant)"""
    
    NOISY = "noisy"
    """Signal bruité"""
    
    CONSTANT = "constant"
    """Signal constant (pas d'oscillation)"""
    
    UNKNOWN = "unknown"
    """Type non reconnu"""


@dataclass
class WaveformFeature:
    """
    Caractéristique extraite d'une forme d'onde.
    Exemple: amplitude, fréquence, temps de montée, etc.
    """
    
    name: str
    """Nom de la caractéristique (ex: 'amplitude', 'frequency')"""
    
    value: float
    """Valeur numérique"""
    
    unit: str
    """Unité (V, Hz, s, etc.)"""
    
    confidence: float
    """Score de confiance (0.0 à 1.0)"""
    
    description: str = ""
    """Description textuelle de la mesure"""
    
    def __post_init__(self):
        """Validation des valeurs."""
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confiance doit être entre 0 et 1, reçu {self.confidence}")
        if not self.name:
            raise ValueError("Le nom de la caractéristique ne peut pas être vide")
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WaveformFeature":
        """Crée depuis un dictionnaire."""
        return cls(
            name=data.get("name", ""),
            value=float(data.get("value", 0)),
            unit=data.get("unit", ""),
            confidence=float(data.get("confidence", 0.5)),
            description=data.get("description", ""),
        )


@dataclass
class WaveformAnalysis:
    """
    Analyse complète d'une forme d'onde.
    Produit par le WaveformChecker (MLLM).
    """
    
    waveform_type: WaveformType
    """Type de forme d'onde identifié"""
    
    features: List[WaveformFeature]
    """Caractéristiques extraites de la forme d'onde"""
    
    anomalies: List[str]
    """Anomalies détectées (ex: 'overshoot at t=10ns')"""
    
    diagnosis: str
    """Diagnostic textuel détaillé"""
    
    recommendations: List[str]
    """Recommandations pour corriger les problèmes"""
    
    confidence: float
    """Score de confiance global (0.0 à 1.0)"""
    
    raw_llm_response: str = ""
    """Réponse brute du LLM (pour débogage)"""
    
    def __post_init__(self):
        """Validation post-initialisation."""
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confiance doit être entre 0 et 1, reçu {self.confidence}")
    
    @property
    def has_anomalies(self) -> bool:
        """True si des anomalies ont été détectées."""
        return len(self.anomalies) > 0
    
    @property
    def is_reliable(self) -> bool:
        """True si l'analyse est fiable (confiance >= 0.7)."""
        return self.confidence >= 0.7
    
    @property
    def primary_feature(self) -> Optional[WaveformFeature]:
        """Retourne la caractéristique principale (amplitude ou fréquence)."""
        priority = ["amplitude", "frequency", "period", "rise_time"]
        for name in priority:
            for feature in self.features:
                if feature.name.lower() == name:
                    return feature
        return self.features[0] if self.features else None
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "waveform_type": self.waveform_type.value,
            "features": [f.to_dict() for f in self.features],
            "anomalies": self.anomalies,
            "diagnosis": self.diagnosis,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
            "has_anomalies": self.has_anomalies,
            "is_reliable": self.is_reliable,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WaveformAnalysis":
        """Crée depuis un dictionnaire."""
        return cls(
            waveform_type=WaveformType(data.get("waveform_type", "unknown")),
            features=[WaveformFeature.from_dict(f) for f in data.get("features", [])],
            anomalies=data.get("anomalies", []),
            diagnosis=data.get("diagnosis", ""),
            recommendations=data.get("recommendations", []),
            confidence=float(data.get("confidence", 0.5)),
            raw_llm_response=data.get("raw_llm_response", ""),
        )


@dataclass
class MultimodalResult:
    """
    Résultat complet de l'analyse multimodale.
    Combine l'analyse de la forme d'onde avec la vérification des spécifications.
    
    C'est l'objet principal retourné par le module WaveformChecker.
    """
    
    verdict: Verdict
    """Verdict global (PASS/FAIL/WARNING) basé sur l'analyse"""
    
    waveform_image_path: str
    """Chemin vers l'image PNG analysée"""
    
    analysis: WaveformAnalysis
    """Analyse détaillée de la forme d'onde"""
    
    extracted_metrics: Dict[str, float] = field(default_factory=dict)
    """Métriques extraites (amplitude, fréquence, etc.)"""
    
    violations: List[str] = field(default_factory=list)
    """Spécifications violées identifiées"""
    
    reasoning: str = ""
    """Raisonnement complet du LLM (peut être long)"""
    
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    """Horodatage de l'analyse"""
    
    # Métadonnées additionnelles
    circuit_name: str = ""
    """Nom du circuit analysé"""
    
    test_name: str = ""
    """Nom du test correspondant"""
    
    processing_time_ms: float = 0.0
    """Temps de traitement en millisecondes"""
    
    llm_model: str = ""
    """Modèle LLM utilisé (ex: 'gpt-4-vision-preview')"""
    
    def __post_init__(self):
        """Validation post-initialisation."""
        if not self.waveform_image_path:
            raise ValueError("Le chemin de l'image ne peut pas être vide")
    
    # =========================================================
    # PROPRIÉTÉS
    # =========================================================
    
    @property
    def is_pass(self) -> bool:
        """True si le verdict est PASS."""
        return self.verdict == Verdict.PASS
    
    @property
    def is_fail(self) -> bool:
        """True si le verdict est FAIL."""
        return self.verdict == Verdict.FAIL
    
    @property
    def is_warning(self) -> bool:
        """True si le verdict est WARNING."""
        return self.verdict == Verdict.WARNING
    
    @property
    def has_violations(self) -> bool:
        """True si des violations ont été détectées."""
        return len(self.violations) > 0
    
    @property
    def confidence(self) -> float:
        """Confiance de l'analyse (délégation à WaveformAnalysis)."""
        return self.analysis.confidence
    
    @property
    def waveform_type(self) -> WaveformType:
        """Type de forme d'onde (délégation)."""
        return self.analysis.waveform_type
    
    @property
    def anomalies(self) -> List[str]:
        """Anomalies détectées (délégation)."""
        return self.analysis.anomalies
    
    @property
    def recommendations(self) -> List[str]:
        """Recommandations (délégation)."""
        return self.analysis.recommendations
    
    @property
    def diagnosis(self) -> str:
        """Diagnostic (délégation)."""
        return self.analysis.diagnosis
    
    # =========================================================
    # MÉTHODES PRATIQUES
    # =========================================================
    
    def get_metric(self, metric_name: str) -> Optional[float]:
        """
        Récupère une métrique extraite par son nom.
        
        Args:
            metric_name: Nom de la métrique (ex: 'amplitude', 'frequency')
            
        Returns:
            Valeur ou None si non trouvée
        """
        return self.extracted_metrics.get(metric_name)
    
    def get_feature(self, feature_name: str) -> Optional[WaveformFeature]:
        """
        Récupère une caractéristique par son nom.
        
        Args:
            feature_name: Nom de la caractéristique
            
        Returns:
            WaveformFeature ou None
        """
        for feature in self.analysis.features:
            if feature.name.lower() == feature_name.lower():
                return feature
        return None
    
    def to_summary(self) -> str:
        """
        Résumé textuel court pour logs ou CLI.
        """
        verdict_str = f"{self.verdict.emoji} {self.verdict.value}"
        return (f"[{verdict_str}] {self.test_name or 'Waveform Analysis'}: "
                f"{self.waveform_type.value}, conf={self.confidence:.2f}")
    
    def to_markdown(self) -> str:
        """
        Génère un rapport Markdown pour intégration dans la documentation.
        """
        lines = [
            f"## Analyse Multimodale: {self.test_name or 'Waveform Analysis'}",
            "",
            f"**Verdict:** {self.verdict.emoji} **{self.verdict.value}**",
            f"**Confiance:** {self.confidence:.1%}",
            f"**Type de forme d'onde:** {self.waveform_type.value}",
            f"**Modèle LLM:** {self.llm_model or 'N/A'}",
            "",
            "### Métriques extraites",
            "",
            "| Métrique | Valeur | Unité | Confiance |",
            "|----------|--------|-------|-----------|",
        ]
        
        for name, value in self.extracted_metrics.items():
            lines.append(f"| {name} | {value:.4g} | | - |")
        
        for feature in self.analysis.features:
            lines.append(f"| {feature.name} | {feature.value:.4g} | {feature.unit} | {feature.confidence:.0%} |")
        
        if self.analysis.anomalies:
            lines.extend([
                "",
                "### Anomalies détectées",
                "",
            ])
            for anomaly in self.analysis.anomalies:
                lines.append(f"- ⚠️ {anomaly}")
        
        if self.analysis.recommendations:
            lines.extend([
                "",
                "### Recommandations",
                "",
            ])
            for rec in self.analysis.recommendations:
                lines.append(f"- 🔧 {rec}")
        
        if self.violations:
            lines.extend([
                "",
                "### Violations des spécifications",
                "",
            ])
            for violation in self.violations:
                lines.append(f"- ❌ {violation}")
        
        lines.extend([
            "",
            "---",
            f"*Généré le {self.timestamp}*",
        ])
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "verdict": self.verdict.value,
            "waveform_image_path": self.waveform_image_path,
            "analysis": self.analysis.to_dict(),
            "extracted_metrics": self.extracted_metrics,
            "violations": self.violations,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "circuit_name": self.circuit_name,
            "test_name": self.test_name,
            "processing_time_ms": self.processing_time_ms,
            "llm_model": self.llm_model,
            "confidence": self.confidence,
            "waveform_type": self.waveform_type.value,
            "has_violations": self.has_violations,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MultimodalResult":
        """Crée depuis un dictionnaire."""
        # Gérer les deux formats possibles pour analysis
        analysis_data = data.get("analysis", {})
        if isinstance(analysis_data, dict):
            analysis = WaveformAnalysis.from_dict(analysis_data)
        else:
            # Fallback pour compatibilité
            analysis = WaveformAnalysis(
                waveform_type=WaveformType(data.get("waveform_type", "unknown")),
                features=[
                    WaveformFeature(
                        name=k,
                        value=v,
                        unit="",
                        confidence=0.8,
                    )
                    for k, v in data.get("extracted_metrics", {}).items()
                ],
                anomalies=data.get("anomalies", []),
                diagnosis=data.get("diagnosis", ""),
                recommendations=data.get("recommendations", []),
                confidence=data.get("confidence", 0.5),
            )
        
        return cls(
            verdict=Verdict(data.get("verdict", "ERROR")),
            waveform_image_path=data.get("waveform_image_path", ""),
            analysis=analysis,
            extracted_metrics=data.get("extracted_metrics", {}),
            violations=data.get("violations", []),
            reasoning=data.get("reasoning", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            circuit_name=data.get("circuit_name", ""),
            test_name=data.get("test_name", ""),
            processing_time_ms=data.get("processing_time_ms", 0.0),
            llm_model=data.get("llm_model", ""),
        )
    
    def __str__(self) -> str:
        """Représentation string lisible."""
        return self.to_summary()