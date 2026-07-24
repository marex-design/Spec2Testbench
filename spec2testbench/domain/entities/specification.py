
"""
Specification Entity - Représente les spécifications utilisateur.
Point d'entrée du framework : les specs sont ce que l'utilisateur veut vérifier.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import json
import yaml
from enum import Enum

# Import correct depuis les value_objects
from ..value_objects.circuit_type import CircuitType


class TemperatureRange(Enum):
    """Gamme de température standard pour les tests PVT."""
    COMMERCIAL = "commercial"      # 0°C to 70°C
    INDUSTRIAL = "industrial"      # -40°C to 85°C
    MILITARY = "military"          # -55°C to 125°C
    EXTENDED = "extended"          # -40°C to 125°C


class ProcessCorner(Enum):
    """Coins de procédé pour les tests PVT."""
    TT = "tt"      # Typical-Typical (nominal)
    FF = "ff"      # Fast-Fast (transistors rapides)
    SS = "ss"      # Slow-Slow (transistors lents)
    FS = "fs"      # Fast-Slow (NMOS rapide, PMOS lent)
    SF = "sf"      # Slow-Fast (NMOS lent, PMOS rapide)


@dataclass
class VariantOverride:
    case_id: str
    target: str
    parameter_name: str
    original_value: Any
    override_value: Any
    source: str


@dataclass
class VerificationSelection:
    include_tests: List[str] = field(default_factory=list)
    exclude_tests: List[str] = field(default_factory=list)
    auto_select: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "include_tests": list(self.include_tests),
            "exclude_tests": list(self.exclude_tests),
            "auto_select": self.auto_select,
        }


@dataclass
class PortRoles:
    input: List[str] = field(default_factory=list)
    output: List[str] = field(default_factory=list)
    differential_positive: List[str] = field(default_factory=list)
    differential_negative: List[str] = field(default_factory=list)
    common_mode: List[str] = field(default_factory=list)
    supply_positive: List[str] = field(default_factory=list)
    supply_negative: List[str] = field(default_factory=list)
    bias: List[str] = field(default_factory=list)
    reference: List[str] = field(default_factory=list)
    loop_break: List[str] = field(default_factory=list)
    loop_injection: List[str] = field(default_factory=list)
    current_probe: List[str] = field(default_factory=list)

    def get(self, role: str) -> List[str]:
        values = getattr(self, role, [])
        return list(values) if isinstance(values, list) else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input": list(self.input),
            "output": list(self.output),
            "differential_positive": list(self.differential_positive),
            "differential_negative": list(self.differential_negative),
            "common_mode": list(self.common_mode),
            "supply_positive": list(self.supply_positive),
            "supply_negative": list(self.supply_negative),
            "bias": list(self.bias),
            "reference": list(self.reference),
            "loop_break": list(self.loop_break),
            "loop_injection": list(self.loop_injection),
            "current_probe": list(self.current_probe),
        }


@dataclass
class OperatingConditions:
    nominal_temperature: Optional[float] = None
    nominal_supply: Optional[float] = None
    process_corner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nominal_temperature": self.nominal_temperature,
            "nominal_supply": self.nominal_supply,
            "process_corner": self.process_corner,
        }


@dataclass
class Specification:
    """
    Specification Entity - Spécifications complètes d'un circuit analogique.
    
    Cette entité est créée à partir :
    - D'un fichier YAML
    - D'un texte en langage naturel (via LLM)
    - De paramètres par défaut
    
    Elle est ensuite utilisée par :
    - TestBenchGen pour générer les testbenches
    - SpecChecker pour vérifier les résultats
    - WaveformChecker pour analyser les formes d'onde
    """
    
    # =========================================================
    # CHAMPS OBLIGATOIRES
    # =========================================================
    
    name: str
    """Nom unique du circuit (ex: 'two_stage_opamp_v2')"""
    
    circuit_type: CircuitType
    """Type de circuit (amplificateur, oscillateur, etc.)"""
    
    # =========================================================
    # CHAMPS OPTIONNELS AVEC VALEURS PAR DÉFAUT
    # =========================================================
    
    performance_targets: Dict[str, Any] = field(default_factory=dict)
    input_conditions: Dict[str, Any] = field(default_factory=dict)
    test_categories: List[str] = field(default_factory=list)
    process_corners: List[ProcessCorner] = field(default_factory=list)
    temperature_range: TemperatureRange = TemperatureRange.COMMERCIAL
    supply_variation: float = 0.10
    technology: str = "CMOS_45nm"
    description: str = ""
    raw_specs: str = ""
    case_id: Optional[str] = None
    parent_circuit_id: Optional[str] = None
    variant_overrides: List[VariantOverride] = field(default_factory=list)
    measurement: Dict[str, Any] = field(default_factory=dict)
    verification: VerificationSelection = field(default_factory=VerificationSelection)
    ports: PortRoles = field(default_factory=PortRoles)
    operating_conditions: OperatingConditions = field(default_factory=OperatingConditions)
    test_requirements: Dict[str, Any] = field(default_factory=dict)
    
    # =========================================================
    # PROPRIÉTÉS COURANTES (getters simplifiés)
    # =========================================================
    
    @property
    def vdd(self) -> float:
        """Tension d'alimentation (V)."""
        if self.operating_conditions.nominal_supply is not None:
            return float(self.operating_conditions.nominal_supply)
        return self.input_conditions.get("vdd", 1.8)
    
    @property
    def vss(self) -> float:
        """Tension de masse (V)."""
        return self.input_conditions.get("vss", 0.0)
    
    @property
    def common_mode_voltage(self) -> float:
        """Tension de mode commun (V)."""
        return self.input_conditions.get("vcm", self.vdd / 2)
    
    @property
    def load_capacitance(self) -> float:
        """Capacité de charge (F)."""
        return self.input_conditions.get("cl", 1e-12)
    
    @property
    def load_resistance(self) -> Optional[float]:
        """Résistance de charge (Ω)."""
        return self.input_conditions.get("rl", None)
    
    @property
    def nominal_temperature(self) -> float:
        """Température nominale (°C)."""
        if self.operating_conditions.nominal_temperature is not None:
            return float(self.operating_conditions.nominal_temperature)
        return self.input_conditions.get("temperature", 27.0)
    
    @property
    def test_frequency(self) -> float:
        """Fréquence de test pour analyses AC (Hz)."""
        return self.input_conditions.get("input_frequency", 1e6)

    @property
    def input_nodes(self) -> List[str]:
        if self.ports.input:
            return list(self.ports.input)
        raw_nodes = self.input_conditions.get("input_nodes", [])
        return self._normalize_node_list(raw_nodes)

    @property
    def output_nodes(self) -> List[str]:
        if self.ports.output:
            return list(self.ports.output)
        raw_nodes = self.input_conditions.get("output_nodes", [])
        return self._normalize_node_list(raw_nodes)

    def port_nodes(self, role: str) -> List[str]:
        return self.ports.get(role)
    
    # =========================================================
    # MÉTHODES D'ACCÈS AUX MÉTRIQUES
    # =========================================================
    
    def get_metric(self, metric_name: str) -> Optional[Dict]:
        """
        Retourne une métrique par son nom.
        
        Args:
            metric_name: Nom de la métrique (ex: 'dc_gain')
            
        Returns:
            Dictionnaire avec min, max, typ, unit ou None
        """
        target = self.performance_targets.get(metric_name)
        if target is None:
            return None
        
        # Si c'est un nombre simple, le convertir en dict
        if isinstance(target, (int, float)):
            return {"min": target}
        if isinstance(target, dict):
            return self._normalize_metric_target(target)
        
        return target
    
    def get_metric_min(self, metric_name: str) -> Optional[float]:
        """Retourne la valeur minimale d'une métrique."""
        metric = self.get_metric(metric_name)
        if not metric:
            return None
        return metric.get("min")
    
    def get_metric_max(self, metric_name: str) -> Optional[float]:
        """Retourne la valeur maximale d'une métrique."""
        metric = self.get_metric(metric_name)
        if not metric:
            return None
        return metric.get("max")
    
    def get_metric_unit(self, metric_name: str) -> str:
        """Retourne l'unité d'une métrique."""
        metric = self.get_metric(metric_name)
        if not metric:
            return ""
        return metric.get("unit", "")
    
    def has_metric(self, metric_name: str) -> bool:
        """Vérifie si une métrique est spécifiée."""
        return metric_name in self.performance_targets
    
    # =========================================================
    # MÉTHODES DE VALIDATION
    # =========================================================
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Valide que la spécification est cohérente.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Vérifier le nom
        if not self.name or len(self.name) < 2:
            errors.append("Le nom du circuit doit faire au moins 2 caractères")
        
        # Vérifier les métriques
        for metric_name, target in self.performance_targets.items():
            if isinstance(target, dict):
                min_val = target.get("min")
                max_val = target.get("max")
                
                # Vérifier que min < max si les deux sont spécifiés
                if min_val is not None and max_val is not None and min_val >= max_val:
                    errors.append(f"Métrique {metric_name}: min ({min_val}) >= max ({max_val})")
        
        # Vérifier les conditions d'entrée
        if self.vdd <= 0:
            errors.append(f"VDD doit être > 0, actuel: {self.vdd}")
        
        if self.load_capacitance <= 0:
            errors.append(f"CL doit être > 0, actuel: {self.load_capacitance}")
        
        # Vérifier la variation d'alimentation
        if not 0 <= self.supply_variation <= 1:
            errors.append(f"Supply variation doit être entre 0 et 1, actuel: {self.supply_variation}")
        
        return (len(errors) == 0, errors)
    
    def is_valid(self) -> bool:
        """Version simplifiée de validate."""
        is_valid, _ = self.validate()
        return is_valid
    
    # =========================================================
    # CONSTRUCTEURS ALTERNATIFS
    # =========================================================
    
    @classmethod
    def from_yaml(cls, path: Path) -> "Specification":
        """
        Crée une spécification depuis un fichier YAML.
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Extraire le type de circuit
        circuit_type_str = data.get("circuit_type", "amplifier")
        circuit_type = CircuitType(circuit_type_str)
        # Extraire les performance targets
        perf_targets = cls._normalize_performance_targets(data.get("performance_targets", {}))
        
        # Extraire les input conditions
        input_conditions = data.get("input_conditions", {}) if isinstance(data.get("input_conditions", {}), dict) else {}
        verification = cls._load_verification(data.get("verification", {}))
        ports = cls._load_ports(data.get("ports", {}), input_conditions)
        operating_conditions = cls._load_operating_conditions(data.get("operating_conditions", {}), input_conditions)
        test_requirements = cls._normalize_test_requirements(data.get("test_requirements", {}))
        
        # Extraire les test categories
        test_categories = data.get("test_categories", [])
        
        # Extraire la config PVT
        pvt_config = data.get("pvt_config", {})
        corners = pvt_config.get("corners", ["tt"])
        process_corners = []
        for corner in corners:
            try:
                process_corners.append(ProcessCorner(corner.lower()))
            except ValueError:
                pass  # Ignorer les corners invalides
        if not process_corners and operating_conditions.process_corner:
            try:
                process_corners.append(ProcessCorner(str(operating_conditions.process_corner).lower()))
            except ValueError:
                pass
        
        temp_range_str = pvt_config.get("temperature_range", "commercial")
        try:
            temperature_range = TemperatureRange(temp_range_str)
        except ValueError:
            temperature_range = TemperatureRange.COMMERCIAL
        
        supply_variation = cls._coerce_numeric(pvt_config.get("supply_variation", 0.10))
        
        return cls(
            name=data.get("name", "unnamed_circuit"),
            circuit_type=circuit_type,
            performance_targets=perf_targets,
            input_conditions=input_conditions,
            test_categories=test_categories,
            process_corners=process_corners,
            temperature_range=temperature_range,
            supply_variation=supply_variation,
            technology=data.get("technology", "CMOS_45nm"),
            description=data.get("description", ""),
            raw_specs=yaml.dump(data, allow_unicode=True),
            case_id=data.get("case_id"),
            parent_circuit_id=data.get("parent_circuit_id"),
            variant_overrides=cls._load_variant_overrides(path),
            measurement=data.get("measurement", {}) if isinstance(data.get("measurement", {}), dict) else {},
            verification=verification,
            ports=ports,
            operating_conditions=operating_conditions,
            test_requirements=test_requirements,
        )
    
    @classmethod
    def from_text(cls, text: str, circuit_name: Optional[str] = None) -> "Specification":
        """
        Crée une spécification depuis du texte en langage naturel.
        """
        return cls(
            name=circuit_name or "from_text",
            circuit_type=CircuitType.AMPLIFIER,  # Sera affiné par LLM
            raw_specs=text,
            description=text[:200],
        )
    
    @classmethod
    def from_dict(cls, data: dict) -> "Specification":
        """Crée une spécification depuis un dictionnaire."""
        circuit_type_str = data.get("circuit_type", "amplifier")
        circuit_type = CircuitType(circuit_type_str)
        input_conditions = data.get("input_conditions", {}) if isinstance(data.get("input_conditions", {}), dict) else {}
        verification = cls._load_verification(data.get("verification", {}))
        ports = cls._load_ports(data.get("ports", {}), input_conditions)
        operating_conditions = cls._load_operating_conditions(data.get("operating_conditions", {}), input_conditions)
        test_requirements = cls._normalize_test_requirements(data.get("test_requirements", {}))

        # Convertir les process corners
        corners_data = data.get("process_corners", ["tt"])
        process_corners = []
        for c in corners_data:
            try:
                process_corners.append(ProcessCorner(c))
            except ValueError:
                pass
        if not process_corners and operating_conditions.process_corner:
            try:
                process_corners.append(ProcessCorner(str(operating_conditions.process_corner).lower()))
            except ValueError:
                pass
        
        temp_range_str = data.get("temperature_range", "commercial")
        try:
            temperature_range = TemperatureRange(temp_range_str)
        except ValueError:
            temperature_range = TemperatureRange.COMMERCIAL
        
        return cls(
            name=data.get("name", "unnamed"),
            circuit_type=circuit_type,
            performance_targets=cls._normalize_performance_targets(data.get("performance_targets", {})),
            input_conditions=input_conditions,
            test_categories=data.get("test_categories", []),
            process_corners=process_corners,
            temperature_range=temperature_range,
            supply_variation=cls._coerce_numeric(data.get("supply_variation", 0.10)),
            technology=data.get("technology", "CMOS_45nm"),
            description=data.get("description", ""),
            raw_specs=data.get("raw_specs", ""),
            case_id=data.get("case_id"),
            parent_circuit_id=data.get("parent_circuit_id"),
            variant_overrides=[
                VariantOverride(**override)
                for override in data.get("variant_overrides", [])
                if isinstance(override, dict)
            ],
            measurement=data.get("measurement", {}) if isinstance(data.get("measurement", {}), dict) else {},
            verification=verification,
            ports=ports,
            operating_conditions=operating_conditions,
            test_requirements=test_requirements,
        )

    @staticmethod
    def _coerce_numeric(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value
        return value

    @classmethod
    def _normalize_metric_target(cls, target: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(target)
        for key in ("min", "max", "typ", "weight", "absolute_tolerance", "relative_tolerance"):
            if key in normalized:
                normalized[key] = cls._coerce_numeric(normalized[key])
        return normalized

    @classmethod
    def _load_variant_overrides(cls, path: Path) -> List[VariantOverride]:
        mutation_path = path.parent / "mutation.json"
        if not mutation_path.exists():
            return []
        try:
            mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        case_id = str(mutation.get("case_id", "")).strip()
        target = str(mutation.get("target_component", "")).strip().upper()
        original_value = mutation.get("original_value")
        override_value = mutation.get("mutated_value")
        source = "controlled_variant"
        overrides: List[VariantOverride] = []

        if target == "TRAN" and isinstance(override_value, str):
            tokens = override_value.split()
            original_tokens = str(original_value).split()
            if len(tokens) >= 2:
                overrides.append(VariantOverride(
                    case_id=case_id,
                    target="TRAN",
                    parameter_name="step_time",
                    original_value=original_tokens[0] if original_tokens else None,
                    override_value=tokens[0],
                    source=source,
                ))
                overrides.append(VariantOverride(
                    case_id=case_id,
                    target="TRAN",
                    parameter_name="end_time",
                    original_value=original_tokens[1] if len(original_tokens) > 1 else None,
                    override_value=tokens[1],
                    source=source,
                ))
        return overrides

    @classmethod
    def _normalize_performance_targets(cls, targets: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for metric_name, target in (targets or {}).items():
            if isinstance(target, dict):
                normalized[metric_name] = cls._normalize_metric_target(target)
            else:
                normalized[metric_name] = cls._coerce_numeric(target)
        return normalized

    @classmethod
    def _normalize_test_requirements(cls, requirements: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(requirements, dict):
            return {}
        normalized: Dict[str, Any] = {}
        for key, value in requirements.items():
            if isinstance(value, dict):
                normalized[str(key)] = {
                    inner_key: cls._coerce_numeric(inner_value)
                    for inner_key, inner_value in value.items()
                }
            else:
                normalized[str(key)] = cls._coerce_numeric(value)
        return normalized

    @classmethod
    def _load_verification(cls, raw_verification: Any) -> VerificationSelection:
        if not isinstance(raw_verification, dict):
            return VerificationSelection()
        return VerificationSelection(
            include_tests=cls._normalize_node_list(raw_verification.get("include_tests", [])),
            exclude_tests=cls._normalize_node_list(raw_verification.get("exclude_tests", [])),
            auto_select=bool(raw_verification.get("auto_select", True)),
        )

    @classmethod
    def _load_ports(cls, raw_ports: Any, input_conditions: Dict[str, Any]) -> PortRoles:
        ports = raw_ports if isinstance(raw_ports, dict) else {}
        return PortRoles(
            input=cls._normalize_node_list(ports.get("input", input_conditions.get("input_nodes", []))),
            output=cls._normalize_node_list(ports.get("output", input_conditions.get("output_nodes", []))),
            differential_positive=cls._normalize_node_list(ports.get("differential_positive", input_conditions.get("differential_positive", []))),
            differential_negative=cls._normalize_node_list(ports.get("differential_negative", input_conditions.get("differential_negative", []))),
            common_mode=cls._normalize_node_list(ports.get("common_mode", input_conditions.get("common_mode", []))),
            supply_positive=cls._normalize_node_list(
                ports.get("supply_positive", input_conditions.get("supply_positive", input_conditions.get("vdd_node", [])))
            ),
            supply_negative=cls._normalize_node_list(
                ports.get("supply_negative", input_conditions.get("supply_negative", input_conditions.get("vss_node", [])))
            ),
            bias=cls._normalize_node_list(ports.get("bias", input_conditions.get("bias_nodes", []))),
            reference=cls._normalize_node_list(ports.get("reference", input_conditions.get("reference_nodes", []))),
            loop_break=cls._normalize_node_list(ports.get("loop_break", input_conditions.get("loop_break_nodes", []))),
            loop_injection=cls._normalize_node_list(ports.get("loop_injection", input_conditions.get("loop_injection_nodes", []))),
            current_probe=cls._normalize_node_list(ports.get("current_probe", input_conditions.get("current_probe_nodes", []))),
        )

    @classmethod
    def _load_operating_conditions(cls, raw_conditions: Any, input_conditions: Dict[str, Any]) -> OperatingConditions:
        conditions = raw_conditions if isinstance(raw_conditions, dict) else {}
        nominal_temperature = cls._coerce_numeric(
            conditions.get("nominal_temperature", input_conditions.get("temperature"))
        )
        nominal_supply = cls._coerce_numeric(
            conditions.get("nominal_supply", input_conditions.get("vdd"))
        )
        process_corner = conditions.get("process_corner")
        if process_corner is not None:
            process_corner = str(process_corner)
        return OperatingConditions(
            nominal_temperature=nominal_temperature,
            nominal_supply=nominal_supply,
            process_corner=process_corner,
        )
    
    # =========================================================
    # MÉTHODES POUR LLM
    # =========================================================
    
    def to_prompt_context(self) -> str:
        """
        Génère un contexte pour le LLM.
        Utilisé par TestBenchGen pour générer le testbench.
        """
        lines = [
            f"Circuit: {self.name}",
            f"Type: {self.circuit_type.display_name}",
            f"Technology: {self.technology}",
            "",
            "Specifications:",
        ]
        
        for metric_name, target in self.performance_targets.items():
            if isinstance(target, dict):
                parts = []
                if "min" in target:
                    parts.append(f"min={target['min']}{target.get('unit', '')}")
                if "max" in target:
                    parts.append(f"max={target['max']}{target.get('unit', '')}")
                if "typ" in target:
                    parts.append(f"typ={target['typ']}{target.get('unit', '')}")
                lines.append(f"  - {metric_name}: {', '.join(parts)}")
            else:
                lines.append(f"  - {metric_name}: {target}")
        
        lines.extend([
            "",
            "Input Conditions:",
            f"  - VDD: {self.vdd} V",
            f"  - VCM: {self.common_mode_voltage} V",
            f"  - CL: {self.load_capacitance} F",
        ])
        
        if self.load_resistance:
            lines.append(f"  - RL: {self.load_resistance} Ω")
        
        return "\n".join(lines)
    
    # =========================================================
    # MÉTHODES D'EXPORT
    # =========================================================
    
    def to_yaml(self) -> str:
        """Exporte la spécification au format YAML."""
        data = {
            "name": self.name,
            "circuit_type": self.circuit_type.value,
            "technology": self.technology,
            "performance_targets": self.performance_targets,
            "input_conditions": self.input_conditions,
            "verification": self.verification.to_dict(),
            "ports": self.ports.to_dict(),
            "operating_conditions": self.operating_conditions.to_dict(),
            "test_requirements": self.test_requirements,
            "test_categories": self.test_categories,
            "pvt_config": {
                "corners": [c.value for c in self.process_corners] if self.process_corners else ["tt"],
                "temperature_range": self.temperature_range.value,
                "supply_variation": self.supply_variation,
            },
            "description": self.description,
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "name": self.name,
            "circuit_type": self.circuit_type.value,
            "circuit_type_display": self.circuit_type.display_name,
            "technology": self.technology,
            "performance_targets": self.performance_targets,
            "input_conditions": self.input_conditions,
            "verification": self.verification.to_dict(),
            "ports": self.ports.to_dict(),
            "operating_conditions": self.operating_conditions.to_dict(),
            "test_requirements": self.test_requirements,
            "test_categories": self.test_categories,
            "process_corners": [c.value for c in self.process_corners],
            "temperature_range": self.temperature_range.value,
            "supply_variation": self.supply_variation,
            "description": self.description,
            "case_id": self.case_id,
            "parent_circuit_id": self.parent_circuit_id,
            "variant_overrides": [
                {
                    "case_id": override.case_id,
                    "target": override.target,
                    "parameter_name": override.parameter_name,
                    "original_value": override.original_value,
                    "override_value": override.override_value,
                    "source": override.source,
                }
                for override in self.variant_overrides
            ],
            "measurement": self.measurement,
        }
    
    # =========================================================
    # REPRÉSENTATIONS
    # =========================================================
    
    def __str__(self) -> str:
        return f"Specification({self.name}, {self.circuit_type.display_name}, {len(self.performance_targets)} metrics)"
    
    def __repr__(self) -> str:
        return f"Specification(name='{self.name}', circuit_type={self.circuit_type})"

    @staticmethod
    def _normalize_node_list(raw_nodes: Any) -> List[str]:
        if isinstance(raw_nodes, str):
            candidates = [item.strip() for item in raw_nodes.split(",")]
        elif isinstance(raw_nodes, list):
            candidates = [str(item).strip() for item in raw_nodes]
        else:
            return []
        return [node for node in candidates if node and node != "-"]
