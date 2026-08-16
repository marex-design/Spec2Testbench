from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceOverridePolicy:
    source_name: str
    source_role: str
    positive_node: str
    negative_node: str
    original_definition: str
    original_dc_value: float | None
    original_ac_magnitude: float | None
    original_ac_phase: float | None
    original_waveform: str | None
    replaceable_by_testbench: bool
    allowed_overrides_by_analysis: dict[str, list[str]] = field(default_factory=dict)
    forbidden_overrides_by_analysis: dict[str, list[str]] = field(default_factory=dict)
    override_requires_specification: bool = False
    override_reason: str = ""
    confidence: float = 0.0
    manual_review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisHarnessPolicy:
    analysis_type: str
    metric_names: list[str]
    source_policies: list[dict[str, Any]]
    supply_policies: list[dict[str, Any]]
    bias_policies: list[dict[str, Any]]
    signal_policies: list[dict[str, Any]]
    allowed_overrides: list[str]
    forbidden_overrides: list[str]
    stimulus_recipe: dict[str, Any]
    analysis_parameters: dict[str, Any]
    measurement_recipes: list[dict[str, Any]]
    semantic_guards: list[str]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
