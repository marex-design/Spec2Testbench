# spec2testbench/domain/value_objects/verdict.py

"""
Verdicts for specification verification.
Représente le résultat de la vérification pour chaque test.
"""

from enum import Enum
from typing import Optional


class Verdict(Enum):
    """
    Verdict possible pour un test de vérification.
    
    Hiérarchie de sévérité:
    PASS (0) < WARNING (1) < FAIL (2) < ERROR (3) < N/A (4)
    """
    
    PASS = "PASS"
    """
    SPÉCIFICATION RESPECTÉE
    
    Le circuit satisfait toutes les exigences du test.
    - Gain mesuré >= Gain minimum requis
    - Bande passante dans les limites spécifiées
    - Consommation <= Puissance maximale
    - Tous les critères sont remplis
    """
    
    FAIL = "FAIL"
    """
    SPÉCIFICATION NON RESPECTÉE
    
    Le circuit ne satisfait pas les exigences du test.
    - Gain mesuré < Gain minimum requis
    - Bande passante hors limites
    - Consommation > Puissance maximale
    - Au moins un critère n'est pas rempli
    """
    
    WARNING = "WARNING"
    """
    SPÉCIFICATION MARGINALE
    
    Le circuit est proche de la limite mais passe encore.
    - Gain mesuré à moins de 5% du minimum
    - Marge de phase < 50° (critique)
    - Comportement acceptable mais non optimal
    - Nécessite une attention particulière
    """
    
    ERROR = "ERROR"
    """
    ERREUR D'ANALYSE
    
    La simulation ou l'analyse a échoué.
    - Circuit ne converge pas
    - Forme d'onde ininterprétable
    - Métrique non mesurable
    - Résultat non fiable
    """
    
    NOT_APPLICABLE = "N/A"
    """
    TEST NON APPLICABLE
    
    Le test n'est pas pertinent pour ce type de circuit.
    - Test AC sur un oscillateur
    - Test de slew rate sur une référence de tension
    - Le circuit ne possède pas la fonctionnalité testée
    """
    
    # =========================================================
    # PROPRIÉTÉS ET MÉTHODES
    # =========================================================
    
    @property
    def is_success(self) -> bool:
        """
        True si le verdict indique un succès.
        
        Le succès est défini comme PASS ou WARNING.
        (WARNING est un succès mais avec réserve)
        """
        return self in (Verdict.PASS, Verdict.WARNING)
    
    @property
    def is_failure(self) -> bool:
        """
        True si le verdict indique un échec.
        
        L'échec inclut FAIL et ERROR.
        """
        return self in (Verdict.FAIL, Verdict.ERROR)
    
    @property
    def is_definitive(self) -> bool:
        """
        True si le verdict est définitif (ne nécessite pas de re-test).
        
        PASS et FAIL sont définitifs.
        WARNING peut nécessiter une analyse plus approfondie.
        ERROR nécessite une correction puis re-test.
        """
        return self in (Verdict.PASS, Verdict.FAIL)
    
    @property
    def severity(self) -> int:
        """
        Niveau de sévérité (0 = meilleur, 4 = pire).
        
        Utilisé pour trier/classer les résultats.
        """
        severity_map = {
            Verdict.PASS: 0,
            Verdict.WARNING: 1,
            Verdict.FAIL: 2,
            Verdict.ERROR: 3,
            Verdict.NOT_APPLICABLE: 4,
        }
        return severity_map.get(self, 2)
    
    @property
    def emoji(self) -> str:
        """
        Emoji représentant le verdict.
        
        Utile pour l'affichage dans les rapports et CLI.
        """
        emoji_map = {
            Verdict.PASS: "✅",
            Verdict.FAIL: "❌",
            Verdict.WARNING: "⚠️",
            Verdict.ERROR: "🔴",
            Verdict.NOT_APPLICABLE: "⭕",
        }
        return emoji_map.get(self, "❓")
    
    @property
    def color_code(self) -> str:
        """
        Code ANSI pour la colorisation dans le terminal.
        """
        color_map = {
            Verdict.PASS: "\033[92m",      # Vert
            Verdict.FAIL: "\033[91m",      # Rouge
            Verdict.WARNING: "\033[93m",   # Jaune
            Verdict.ERROR: "\033[95m",     # Magenta
            Verdict.NOT_APPLICABLE: "\033[90m",  # Gris
        }
        return color_map.get(self, "\033[0m")
    
    @property
    def colorized(self) -> str:
        """
        Verdict colorisé pour affichage terminal.
        """
        reset = "\033[0m"
        return f"{self.color_code}{self.value}{reset}"
    
    @property
    def colorized_with_emoji(self) -> str:
        """
        Verdict avec emoji et couleur pour affichage terminal.
        """
        reset = "\033[0m"
        return f"{self.color_code}{self.emoji} {self.value}{reset}"
    
    # =========================================================
    # MÉTHODES DE CONVERSION
    # =========================================================
    
    @classmethod
    def from_bool(cls, passed: bool, is_marginal: bool = False) -> "Verdict":
        """
        Convertit un booléen en Verdict.
        
        Args:
            passed: True si le test est réussi
            is_marginal: True si le succès est marginal (génère WARNING)
            
        Returns:
            Verdict.PASS, Verdict.WARNING, ou Verdict.FAIL
        """
        if not passed:
            return Verdict.FAIL
        if is_marginal:
            return Verdict.WARNING
        return Verdict.PASS
    
    @classmethod
    def from_margin(cls, measured: float, expected_min: float, 
                    expected_max: Optional[float] = None,
                    warning_margin: float = 0.05) -> "Verdict":
        """
        Calcule le verdict basé sur la marge par rapport aux spécifications.
        
        Args:
            measured: Valeur mesurée
            expected_min: Valeur minimale attendue
            expected_max: Valeur maximale attendue (optionnel)
            warning_margin: Marge pour émettre un WARNING (défaut: 5%)
            
        Returns:
            Verdict basé sur la marge
        """
        # Vérifier si en dessous du minimum
        if measured < expected_min:
            # Calculer l'écart relatif
            margin = (expected_min - measured) / expected_min
            
            # Si très proche du minimum (< 5%), c'est un WARNING
            if margin < warning_margin:
                return Verdict.WARNING
            return Verdict.FAIL
        
        # Vérifier si au-dessus du maximum
        if expected_max is not None and measured > expected_max:
            margin = (measured - expected_max) / expected_max
            if margin < warning_margin:
                return Verdict.WARNING
            return Verdict.FAIL
        
        # Tout va bien
        return Verdict.PASS
    
    @classmethod
    def worst_case(cls, verdicts: list["Verdict"]) -> "Verdict":
        """
        Retourne le pire verdict parmi une liste.
        
        Utile pour agréger plusieurs tests.
        La sévérité détermine l'ordre: ERROR > FAIL > WARNING > PASS > N/A
        
        Args:
            verdicts: Liste de verdicts
            
        Returns:
            Le verdict avec la sévérité la plus élevée
        """
        if not verdicts:
            return Verdict.NOT_APPLICABLE
        
        # Filtrer les N/A car ils ne sont pas significatifs
        meaningful = [v for v in verdicts if v != Verdict.NOT_APPLICABLE]
        
        if not meaningful:
            return Verdict.PASS
        
        # Retourner celui avec la plus haute sévérité
        return max(meaningful, key=lambda v: v.severity)
    
    # =========================================================
    # REPRÉSENTATIONS
    # =========================================================
    
    def __str__(self) -> str:
        """Représentation string simple."""
        return self.value
    
    def __repr__(self) -> str:
        """Représentation pour débogage."""
        return f"Verdict.{self.name}"
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "verdict": self.value,
            "is_success": self.is_success,
            "severity": self.severity,
            "emoji": self.emoji,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Verdict":
        """Crée un Verdict depuis un dictionnaire."""
        return cls(data.get("verdict", "ERROR"))


# =========================================================
# CLASSE ASSOCIÉE: CheckResult
# =========================================================

class ValidationStatus(Enum):
    """High-level verification outcome for end-to-end evaluation."""

    FAIL = "FAIL"
    RUN = "RUN"
    PASS = "PASS"
    ROBUST_PASS = "ROBUST PASS"

    @property
    def severity(self) -> int:
        severity_map = {
            ValidationStatus.ROBUST_PASS: 0,
            ValidationStatus.PASS: 1,
            ValidationStatus.RUN: 2,
            ValidationStatus.FAIL: 3,
        }
        return severity_map[self]

    @property
    def emoji(self) -> str:
        emoji_map = {
            ValidationStatus.FAIL: "❌",
            ValidationStatus.RUN: "⚙️",
            ValidationStatus.PASS: "✅",
            ValidationStatus.ROBUST_PASS: "🛡️",
        }
        return emoji_map[self]

    @property
    def is_success(self) -> bool:
        return self in (ValidationStatus.PASS, ValidationStatus.ROBUST_PASS)

    @property
    def color_code(self) -> str:
        color_map = {
            ValidationStatus.FAIL: "\033[91m",
            ValidationStatus.RUN: "\033[93m",
            ValidationStatus.PASS: "\033[92m",
            ValidationStatus.ROBUST_PASS: "\033[96m",
        }
        return color_map[self]

    @property
    def colorized_with_emoji(self) -> str:
        reset = "\033[0m"
        return f"{self.color_code}{self.emoji} {self.value}{reset}"


from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CheckResult:
    """
    Résultat complet d'une vérification.
    
    Assemble le verdict avec les valeurs mesurées et attendues.
    Utilisé par le module SpecChecker.
    """
    
    test_name: str
    """Nom du test effectué"""
    
    verdict: Verdict
    """Verdict du test"""
    
    measured_value: Optional[float] = None
    """Valeur mesurée"""
    
    expected_min: Optional[float] = None
    """Valeur minimale attendue"""
    
    expected_max: Optional[float] = None
    """Valeur maximale attendue"""
    
    unit: str = ""
    """Unité de mesure (V, A, Hz, dB, etc.)"""
    
    message: str = ""
    """Message détaillant le résultat"""
    
    category: Optional[str] = None
    """Catégorie du test (DC, AC, TRANSIENT, etc.)"""
    
    waveform_path: Optional[str] = None
    """Chemin vers l'image de la forme d'onde (si générée)"""
    
    def __post_init__(self):
        """Validation post-initialisation."""
        if not self.test_name:
            raise ValueError("test_name cannot be empty")
    
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
    def expected_range(self) -> str:
        """Chaîne décrivant la plage attendue."""
        if self.expected_min is not None and self.expected_max is not None:
            return f"[{self.expected_min}, {self.expected_max}] {self.unit}"
        elif self.expected_min is not None:
            return f">= {self.expected_min} {self.unit}"
        elif self.expected_max is not None:
            return f"<= {self.expected_max} {self.unit}"
        return "No specification"
    
    @property
    def measured_str(self) -> str:
        """Valeur mesurée formatée."""
        if self.measured_value is None:
            return "N/A"
        return f"{self.measured_value:.6g} {self.unit}"
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "test_name": self.test_name,
            "verdict": self.verdict.value,
            "is_pass": self.is_pass,
            "measured_value": self.measured_value,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
            "unit": self.unit,
            "message": self.message,
            "category": self.category,
            "waveform_path": self.waveform_path,
        }
    
    def __str__(self) -> str:
        """Représentation string lisible."""
        verdict_str = f"{self.verdict.emoji} {self.verdict.colorized}"
        return (f"[{verdict_str}] {self.test_name}: "
                f"measured={self.measured_str}, "
                f"expected={self.expected_range}")
