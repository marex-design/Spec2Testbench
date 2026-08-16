"""Strict schema for reproducible Spec2Testbench v2 YAML specifications.

The runtime ``Specification`` entity remains backward-compatible with legacy YAML.
This model is intentionally stricter and is used by ``spec-lint`` and ACP-28
benchmark campaigns before any simulation is started.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


AnalysisKind = Literal["OP", "DC", "AC", "TRAN", "FFT"]
EquivalenceKind = Literal["exact", "semantic", "partial", "diagnostic"]
ImplementationKind = Literal["executable", "metadata_only"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpstreamChecker(StrictModel):
    path: str
    criterion_summary: List[str] = Field(default_factory=list)
    upstream_mutates_dut: bool = False
    notes: Optional[str] = None


class DutProvenance(StrictModel):
    path: str
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    canonicalization: str
    topology_and_values_preserved: bool = True


class Provenance(StrictModel):
    benchmark: str
    benchmark_subset: str
    upstream_repository: str
    upstream_task_id: int = Field(ge=1)
    upstream_level: str
    upstream_type: str
    upstream_submodule_name: str
    upstream_task_description: str
    upstream_testbench_description: str
    official_checker: UpstreamChecker
    dut: DutProvenance


class Ports(StrictModel):
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


class OperatingConditions(StrictModel):
    nominal_temperature: float = 27.0
    nominal_supply: Optional[float] = None
    process_corner: str = "tt"


class StimulusSpec(StrictModel):
    id: str
    kind: Literal["DC", "AC", "PULSE", "SIN", "PWL", "TRIANGLE", "NONE"]
    source: Optional[str] = None
    node_positive: Optional[str] = None
    node_negative: str = "0"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    purpose: str


class AnalysisSpec(StrictModel):
    id: str
    type: AnalysisKind
    parameters: Dict[str, Any] = Field(default_factory=dict)
    purpose: str


class FunctionalRequirement(StrictModel):
    id: str
    description: str
    metric: str
    analysis: str
    operator: Literal[">", ">=", "<", "<=", "==", "between"]
    threshold: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str
    mandatory: bool = True
    criterion_source: Literal["official_checker", "task_description", "derived_semantic"]
    equivalence: EquivalenceKind
    implementation_status: ImplementationKind
    executable_metric: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.operator == "between":
            if self.minimum is None or self.maximum is None:
                raise ValueError("between requires minimum and maximum")
            if self.minimum >= self.maximum:
                raise ValueError("minimum must be < maximum")
        elif self.threshold is None:
            raise ValueError(f"operator {self.operator} requires threshold")
        if self.implementation_status == "executable" and not self.executable_metric:
            raise ValueError("executable requirements must name executable_metric")
        return self


class MetricTarget(StrictModel):
    min: Optional[float] = None
    max: Optional[float] = None
    typ: Optional[float] = None
    unit: str
    diagnostic_only: bool = False
    requirement_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_range(self):
        if self.min is None and self.max is None and self.typ is None:
            raise ValueError("metric target needs min, max or typ")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("metric min must be < max")
        return self


class VerificationPolicy(StrictModel):
    auto_select: bool = True
    include_tests: List[str] = Field(default_factory=list)
    exclude_tests: List[str] = Field(default_factory=list)
    required_policy: Literal["all", "any"] = "all"
    immutable_dut: bool = True
    not_evaluated_on_missing_mandatory_metric: bool = True
    require_full_contract_for_compliance: bool = True


class MeasurementPolicy(StrictModel):
    backend: Literal["AUTO", "NGSPICE_MEASURE", "NGSPICE_WRDATA"] = "AUTO"
    allow_fallback: bool = True


class ACPYamlV2(StrictModel):
    schema_version: Literal["2.0"]
    case_id: str
    name: str
    circuit_type: str
    technology: str
    description: str
    provenance: Provenance
    ports: Ports
    operating_conditions: OperatingConditions
    stimuli: List[StimulusSpec]
    analyses: List[AnalysisSpec]
    functional_requirements: List[FunctionalRequirement]
    performance_targets: Dict[str, MetricTarget]
    input_conditions: Dict[str, Any]
    measurement: MeasurementPolicy
    verification: VerificationPolicy
    test_requirements: Dict[str, Any] = Field(default_factory=dict)
    test_categories: List[str]
    pvt_config: Dict[str, Any] = Field(default_factory=lambda: {
        "corners": ["tt"], "temperature_range": "commercial", "supply_variation": 0.0
    })

    @model_validator(mode="after")
    def validate_cross_references(self):
        analysis_ids = [item.id for item in self.analyses]
        if len(analysis_ids) != len(set(analysis_ids)):
            raise ValueError("analysis ids must be unique")
        requirement_ids = [item.id for item in self.functional_requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("functional requirement ids must be unique")
        known_analyses = set(analysis_ids)
        known_requirements = set(requirement_ids)
        for req in self.functional_requirements:
            if req.analysis not in known_analyses:
                raise ValueError(f"requirement {req.id}: unknown analysis {req.analysis}")
            if req.executable_metric and req.executable_metric not in self.performance_targets:
                raise ValueError(
                    f"requirement {req.id}: executable_metric {req.executable_metric} missing from performance_targets"
                )
        for metric_name, target in self.performance_targets.items():
            for req_id in target.requirement_ids:
                if req_id not in known_requirements:
                    raise ValueError(f"metric {metric_name}: unknown requirement id {req_id}")
        if not self.ports.output:
            raise ValueError("at least one output port is required")
        return self

    @property
    def mandatory_requirement_count(self) -> int:
        return sum(1 for req in self.functional_requirements if req.mandatory)

    @property
    def executable_mandatory_requirement_count(self) -> int:
        return sum(
            1 for req in self.functional_requirements
            if req.mandatory and req.implementation_status == "executable"
        )

    @property
    def contract_implementation_coverage(self) -> float:
        total = self.mandatory_requirement_count
        if total == 0:
            return 0.0
        return self.executable_mandatory_requirement_count / total


def load_acp_yaml_v2(path: Union[str, Path]) -> ACPYamlV2:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return ACPYamlV2.model_validate(data)
