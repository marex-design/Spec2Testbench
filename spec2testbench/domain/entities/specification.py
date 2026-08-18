"""User and benchmark specification entity.

The class keeps the legacy 0.x API while exposing the strict ACP-28 v2
contract used by the deterministic benchmark and the LLM planning layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import copy
import hashlib
import json
import yaml

from ..value_objects.circuit_type import CircuitType
from ..specification_schema_v2 import ACPYamlV2, load_acp_yaml_v2


class TemperatureRange(Enum):
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    MILITARY = "military"
    EXTENDED = "extended"


class ProcessCorner(Enum):
    TT = "tt"
    FF = "ff"
    SS = "ss"
    FS = "fs"
    SF = "sf"


@dataclass
class Specification:
    name: str
    circuit_type: CircuitType
    performance_targets: Dict[str, Any] = field(default_factory=dict)
    input_conditions: Dict[str, Any] = field(default_factory=dict)
    test_categories: List[str] = field(default_factory=list)
    process_corners: List[ProcessCorner] = field(default_factory=list)
    temperature_range: TemperatureRange = TemperatureRange.COMMERCIAL
    supply_variation: float = 0.10
    technology: str = "CMOS_45nm"
    description: str = ""
    raw_specs: str = ""

    # v2 additions
    schema_version: str = "1.0"
    case_id: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    ports: Dict[str, List[str]] = field(default_factory=dict)
    operating_conditions: Dict[str, Any] = field(default_factory=dict)
    stimuli: List[Dict[str, Any]] = field(default_factory=list)
    analyses: List[Dict[str, Any]] = field(default_factory=list)
    functional_requirements: List[Dict[str, Any]] = field(default_factory=list)
    measurement: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    test_requirements: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[str] = None

    @property
    def vdd(self) -> float:
        return float(self.input_conditions.get("vdd", self.operating_conditions.get("nominal_supply", 1.8) or 1.8))

    @property
    def vss(self) -> float:
        return float(self.input_conditions.get("vss", 0.0))

    @property
    def common_mode_voltage(self) -> float:
        return float(self.input_conditions.get("vcm", self.vdd / 2))

    @property
    def load_capacitance(self) -> float:
        return float(self.input_conditions.get("cl", 1e-12))

    @property
    def load_resistance(self) -> Optional[float]:
        value = self.input_conditions.get("rl")
        return None if value is None else float(value)

    @property
    def nominal_temperature(self) -> float:
        return float(self.operating_conditions.get("nominal_temperature", self.input_conditions.get("temperature", 27.0)))

    @property
    def test_frequency(self) -> float:
        return float(self.input_conditions.get("input_frequency", 1e6))

    @property
    def is_v2(self) -> bool:
        return str(self.schema_version) == "2.0"

    def get_metric(self, metric_name: str) -> Optional[Dict[str, Any]]:
        target = self.performance_targets.get(metric_name)
        if target is None:
            return None
        if isinstance(target, (int, float)):
            return {"min": target}
        return dict(target)

    def get_metric_min(self, metric_name: str) -> Optional[float]:
        metric = self.get_metric(metric_name)
        return None if not metric else metric.get("min")

    def get_metric_max(self, metric_name: str) -> Optional[float]:
        metric = self.get_metric(metric_name)
        return None if not metric else metric.get("max")

    def get_metric_unit(self, metric_name: str) -> str:
        metric = self.get_metric(metric_name)
        return "" if not metric else str(metric.get("unit", ""))

    def has_metric(self, metric_name: str) -> bool:
        return metric_name in self.performance_targets

    def verification_metric_names(self) -> List[str]:
        if self.is_v2 and self.functional_requirements:
            out: List[str] = []
            for req in self.functional_requirements:
                if not req.get("mandatory", True):
                    continue
                if req.get("implementation_status") != "executable":
                    continue
                metric = req.get("executable_metric")
                if metric and metric not in out:
                    out.append(metric)
            return out
        return [
            name for name, target in self.performance_targets.items()
            if not (isinstance(target, dict) and target.get("diagnostic_only", False))
        ]

    def mandatory_requirements(self) -> List[Dict[str, Any]]:
        return [r for r in self.functional_requirements if r.get("mandatory", True)]

    def requirement_for_metric(self, metric_name: str) -> Optional[Dict[str, Any]]:
        for req in self.functional_requirements:
            if req.get("executable_metric") == metric_name or req.get("metric") == metric_name:
                return req
        return None

    def project_verification_metrics(self, metric_names: List[str]) -> "Specification":
        wanted = {str(x) for x in metric_names}
        clone = copy.deepcopy(self)
        if clone.is_v2:
            clone.functional_requirements = [
                r for r in clone.functional_requirements
                if (r.get("executable_metric") in wanted or r.get("metric") in wanted)
            ]
            keep_targets = set(wanted)
            # retain diagnostic targets, but they never become mandatory evidence
            for name, target in clone.performance_targets.items():
                if isinstance(target, dict) and target.get("diagnostic_only"):
                    keep_targets.add(name)
            clone.performance_targets = {
                k: v for k, v in clone.performance_targets.items() if k in keep_targets
            }
        else:
            clone.performance_targets = {k: v for k, v in clone.performance_targets.items() if k in wanted}
        return clone

    def validate(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not self.name or len(self.name) < 2:
            errors.append("Le nom du circuit doit faire au moins 2 caractères")
        for metric_name, target in self.performance_targets.items():
            if isinstance(target, dict):
                lo, hi = target.get("min"), target.get("max")
                if lo is not None and hi is not None and float(lo) > float(hi):
                    errors.append(f"Métrique {metric_name}: min ({lo}) > max ({hi})")
        if self.vdd <= 0:
            errors.append(f"VDD doit être > 0, actuel: {self.vdd}")
        if not 0 <= self.supply_variation <= 1:
            errors.append("Supply variation doit être entre 0 et 1")
        return not errors, errors

    def is_valid(self) -> bool:
        return self.validate()[0]

    def canonical_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "name": self.name,
            "circuit_type": self.circuit_type.value,
            "technology": self.technology,
            "description": self.description,
            "provenance": self.provenance,
            "ports": self.ports,
            "operating_conditions": self.operating_conditions,
            "stimuli": self.stimuli,
            "analyses": self.analyses,
            "functional_requirements": self.functional_requirements,
            "performance_targets": self.performance_targets,
            "input_conditions": self.input_conditions,
            "measurement": self.measurement,
            "verification": self.verification,
            "test_requirements": self.test_requirements,
            "test_categories": self.test_categories,
            "pvt_config": {
                "corners": [c.value for c in self.process_corners],
                "temperature_range": self.temperature_range.value,
                "supply_variation": self.supply_variation,
            },
        }

    def sha256(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_yaml(cls, path: Path) -> "Specification":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"{path}: YAML root must be a mapping")

        if str(data.get("schema_version", "")) == "2.0":
            model: ACPYamlV2 = load_acp_yaml_v2(path)
            d = model.model_dump(mode="python")
            try:
                circuit_type = CircuitType(d["circuit_type"])
            except ValueError:
                # Preserve old behavior for a few benchmark aliases.
                aliases = {"inverter": CircuitType.AMPLIFIER, "adder": CircuitType.COMPOSITE,
                           "subtractor": CircuitType.COMPOSITE, "integrator": CircuitType.OPAMP_INTEGRATOR,
                           "differentiator": CircuitType.OPAMP_DIFFERENTIATOR}
                circuit_type = aliases.get(d["circuit_type"], CircuitType.COMPOSITE)
            pvt = d.get("pvt_config", {})
            corners = []
            for c in pvt.get("corners", ["tt"]):
                try: corners.append(ProcessCorner(str(c).lower()))
                except ValueError: pass
            try:
                tr = TemperatureRange(pvt.get("temperature_range", "commercial"))
            except ValueError:
                tr = TemperatureRange.COMMERCIAL
            return cls(
                name=d["name"], circuit_type=circuit_type,
                performance_targets=d.get("performance_targets", {}),
                input_conditions=d.get("input_conditions", {}),
                test_categories=d.get("test_categories", []),
                process_corners=corners, temperature_range=tr,
                supply_variation=float(pvt.get("supply_variation", 0.0)),
                technology=d.get("technology", ""), description=d.get("description", ""),
                schema_version="2.0", case_id=d.get("case_id", path.stem),
                provenance=d.get("provenance", {}), ports=d.get("ports", {}),
                operating_conditions=d.get("operating_conditions", {}),
                stimuli=d.get("stimuli", []), analyses=d.get("analyses", []),
                functional_requirements=d.get("functional_requirements", []),
                measurement=d.get("measurement", {}), verification=d.get("verification", {}),
                test_requirements=d.get("test_requirements", {}), source_path=str(path),
            )

        circuit_type_str = data.get("circuit_type", "amplifier")
        circuit_type = CircuitType(circuit_type_str)
        pvt = data.get("pvt_config", {})
        corners = []
        for corner in pvt.get("corners", ["tt"]):
            try: corners.append(ProcessCorner(str(corner).lower()))
            except ValueError: pass
        try: temp_range = TemperatureRange(pvt.get("temperature_range", "commercial"))
        except ValueError: temp_range = TemperatureRange.COMMERCIAL
        return cls(
            name=data.get("name", "unnamed_circuit"), circuit_type=circuit_type,
            performance_targets=data.get("performance_targets", {}),
            input_conditions=data.get("input_conditions", {}), test_categories=data.get("test_categories", []),
            process_corners=corners, temperature_range=temp_range,
            supply_variation=float(pvt.get("supply_variation", 0.10)),
            technology=data.get("technology", "CMOS_45nm"), description=data.get("description", ""),
            source_path=str(path),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Specification":
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
            tmp = Path(f.name)
        try:
            return cls.from_yaml(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def from_text(cls, text: str, circuit_name: Optional[str] = None) -> "Specification":
        return cls(name=circuit_name or "from_text", circuit_type=CircuitType.AMPLIFIER,
                   raw_specs=text, description=text[:200])

    def to_dict(self) -> dict:
        return self.canonical_dict()

    def to_yaml(self, path: Optional[Path] = None) -> str:
        content = yaml.safe_dump(self.canonical_dict(), sort_keys=False, allow_unicode=True)
        if path:
            Path(path).write_text(content, encoding="utf-8")
        return content

    def __str__(self) -> str:
        return f"Specification({self.case_id or self.name}, {self.circuit_type.value}, metrics={self.verification_metric_names()})"
