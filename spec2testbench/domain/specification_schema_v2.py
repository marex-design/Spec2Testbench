"""Strict ACP-28 specification schema used by Spec2Testbench v0.5.0.

This module deliberately separates the *declared verification contract* from
runtime evidence.  A requirement may be mandatory yet explicitly
``metadata_only`` when the deterministic runtime does not implement it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PortRoles(_StrictModel):
    input: List[str] = Field(default_factory=list)
    output: List[str] = Field(default_factory=list)
    differential_positive: List[str] = Field(default_factory=list)
    differential_negative: List[str] = Field(default_factory=list)
    common_mode: List[str] = Field(default_factory=list)
    supply_positive: List[str] = Field(default_factory=list)
    supply_negative: List[str] = Field(default_factory=list)
    bias: List[str] = Field(default_factory=list)
    reference: List[str] = Field(default_factory=list)
    loop_break: List[str] = Field(default_factory=list)
    loop_injection: List[str] = Field(default_factory=list)
    current_probe: List[str] = Field(default_factory=list)


class OperatingConditions(_StrictModel):
    nominal_temperature: float = 25.0
    nominal_supply: Optional[float] = None
    process_corner: str = "tt"


class StimulusV2(_StrictModel):
    id: str
    kind: str
    source: Optional[str] = None
    node_positive: Optional[str] = None
    node_negative: str = "0"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""


class AnalysisV2(_StrictModel):
    id: str
    type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""


class FunctionalRequirementV2(_StrictModel):
    id: str
    description: str = ""
    metric: str
    analysis: str
    operator: str
    threshold: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    mandatory: bool = True
    criterion_source: str = "official_checker"
    equivalence: str = "exact"
    implementation_status: Literal["executable", "metadata_only"] = "metadata_only"
    executable_metric: Optional[str] = None
    notes: str = ""

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.operator == "between" and self.minimum is None and self.maximum is None:
            raise ValueError(f"requirement {self.id}: between requires minimum/maximum")
        if self.implementation_status == "executable" and not self.executable_metric:
            raise ValueError(f"requirement {self.id}: executable requirement requires executable_metric")
        if self.implementation_status == "metadata_only" and self.executable_metric:
            raise ValueError(f"requirement {self.id}: metadata_only requirement cannot expose executable_metric")
        return self


class MeasurementConfigV2(_StrictModel):
    backend: str = "AUTO"
    allow_fallback: bool = True


class VerificationPolicyV2(_StrictModel):
    auto_select: bool = True
    include_tests: List[str] = Field(default_factory=list)
    exclude_tests: List[str] = Field(default_factory=list)
    required_policy: str = "all"
    immutable_dut: bool = True
    not_evaluated_on_missing_mandatory_metric: bool = True
    require_full_contract_for_compliance: bool = True


class ACPYamlV2(_StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    case_id: str
    name: str
    circuit_type: str
    technology: str = "AnalogCoder-Pro generic Level-1 benchmark models"
    description: str = ""
    provenance: Dict[str, Any] = Field(default_factory=dict)
    ports: PortRoles = Field(default_factory=PortRoles)
    operating_conditions: OperatingConditions = Field(default_factory=OperatingConditions)
    stimuli: List[StimulusV2] = Field(default_factory=list)
    analyses: List[AnalysisV2] = Field(default_factory=list)
    functional_requirements: List[FunctionalRequirementV2] = Field(default_factory=list)
    performance_targets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    input_conditions: Dict[str, Any] = Field(default_factory=dict)
    measurement: MeasurementConfigV2 = Field(default_factory=MeasurementConfigV2)
    verification: VerificationPolicyV2 = Field(default_factory=VerificationPolicyV2)
    test_requirements: Dict[str, Any] = Field(default_factory=dict)
    test_categories: List[str] = Field(default_factory=list)
    pvt_config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_contract(self):
        ids = [r.id for r in self.functional_requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("functional requirement IDs must be unique")
        for req in self.functional_requirements:
            if req.implementation_status == "executable":
                if req.executable_metric not in self.performance_targets:
                    raise ValueError(
                        f"requirement {req.id}: executable_metric {req.executable_metric} "
                        "missing from performance_targets"
                    )
        return self

    @property
    def mandatory_requirement_count(self) -> int:
        return sum(bool(r.mandatory) for r in self.functional_requirements)

    @property
    def executable_mandatory_requirement_count(self) -> int:
        return sum(bool(r.mandatory) and r.implementation_status == "executable" for r in self.functional_requirements)

    @property
    def contract_implementation_coverage(self) -> float:
        total = self.mandatory_requirement_count
        return self.executable_mandatory_requirement_count / total if total else 1.0

    def verification_metric_names(self) -> List[str]:
        out: List[str] = []
        for req in self.functional_requirements:
            if req.mandatory and req.implementation_status == "executable" and req.executable_metric:
                if req.executable_metric not in out:
                    out.append(req.executable_metric)
        return out


def load_acp_yaml_v2(path: Union[str, Path]) -> ACPYamlV2:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return ACPYamlV2.model_validate(data)
