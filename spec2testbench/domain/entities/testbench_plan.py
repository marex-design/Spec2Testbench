from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _ensure_finite_mapping(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                raise ValueError(f"{name}.{key} must be finite")
        elif isinstance(value, str):
            if value.strip().lower() in {"nan", "inf", "+inf", "-inf"}:
                raise ValueError(f"{name}.{key} must not be NaN or Inf")
    return payload


class AnalysisType(str, Enum):
    OP = "OP"
    DC = "DC"
    AC = "AC"
    TRAN = "TRAN"


class StimulusType(str, Enum):
    DC = "DC"
    AC = "AC"
    PULSE = "PULSE"
    SIN = "SIN"
    PWL = "PWL"
    TRIANGLE = "TRIANGLE"


class MeasurementBackendPreference(str, Enum):
    NGSPICE_MEASURE = "NGSPICE_MEASURE"
    NGSPICE_WRDATA = "NGSPICE_WRDATA"
    AUTO = "AUTO"


class StimulusPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_name: str
    target_node: str
    stimulus_type: StimulusType
    parameters: dict[str, float | int | str] = Field(default_factory=dict)

    @field_validator("source_name", "target_node")
    @classmethod
    def _validate_names(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("parameters")
    @classmethod
    def _validate_parameters(cls, value: dict[str, float | int | str]) -> dict[str, float | int | str]:
        return _ensure_finite_mapping("stimulus.parameters", value)


class SimulationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_time_s: float | None = None
    stop_time_s: float | None = None
    time_step_s: float | None = None

    dc_source: str | None = None
    dc_start: float | None = None
    dc_stop: float | None = None
    dc_step: float | None = None

    frequency_start_hz: float | None = None
    frequency_stop_hz: float | None = None
    points_per_decade: int | None = None

    @field_validator(
        "start_time_s",
        "stop_time_s",
        "time_step_s",
        "dc_start",
        "dc_stop",
        "dc_step",
        "frequency_start_hz",
        "frequency_stop_hz",
    )
    @classmethod
    def _validate_numeric(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not math.isfinite(float(value)):
            raise ValueError("must be finite")
        return float(value)

    @field_validator("dc_source")
    @classmethod
    def _validate_dc_source(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("dc_source must not be empty")
        return text

    @field_validator("points_per_decade")
    @classmethod
    def _validate_ppd(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("points_per_decade must be positive")
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "SimulationParameters":
        if self.start_time_s is not None and self.start_time_s < 0:
            raise ValueError("start_time_s must be non-negative")
        if self.stop_time_s is not None and self.stop_time_s < 0:
            raise ValueError("stop_time_s must be non-negative")
        if self.time_step_s is not None and self.time_step_s <= 0:
            raise ValueError("time_step_s must be positive")
        if self.frequency_start_hz is not None and self.frequency_start_hz < 0:
            raise ValueError("frequency_start_hz must be non-negative")
        if self.frequency_stop_hz is not None and self.frequency_stop_hz < 0:
            raise ValueError("frequency_stop_hz must be non-negative")
        if self.dc_step is not None and self.dc_step == 0:
            raise ValueError("dc_step must be non-zero")
        if (
            self.frequency_start_hz is not None
            and self.frequency_stop_hz is not None
            and self.frequency_stop_hz <= self.frequency_start_hz
        ):
            raise ValueError("frequency_stop_hz must be greater than frequency_start_hz")
        if (
            self.start_time_s is not None
            and self.stop_time_s is not None
            and self.stop_time_s <= self.start_time_s
        ):
            raise ValueError("stop_time_s must be greater than start_time_s")
        if (
            self.time_step_s is not None
            and self.stop_time_s is not None
            and self.time_step_s >= self.stop_time_s
        ):
            raise ValueError("time_step_s must be less than stop_time_s")
        return self


class MeasurementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_name: str
    analysis_type: AnalysisType
    input_node: str | None = None
    output_node: str | None = None
    expected_unit: str
    backend_preference: MeasurementBackendPreference = MeasurementBackendPreference.AUTO
    measurement_parameters: dict[str, float | int | str] = Field(default_factory=dict)

    @field_validator("metric_name", "expected_unit")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("input_node", "output_node")
    @classmethod
    def _validate_optional_node(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("node must not be empty")
        return text

    @field_validator("measurement_parameters")
    @classmethod
    def _validate_measurement_parameters(
        cls,
        value: dict[str, float | int | str],
    ) -> dict[str, float | int | str]:
        return _ensure_finite_mapping("measurement.measurement_parameters", value)


class TestbenchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    analysis_type: AnalysisType
    stimuli: list[StimulusPlan] = Field(default_factory=list)
    observed_nodes: list[str] = Field(default_factory=list)
    measurements: list[MeasurementPlan]
    simulation_parameters: SimulationParameters
    concise_rationale: str

    @field_validator("case_id", "concise_rationale")
    @classmethod
    def _validate_non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("observed_nodes")
    @classmethod
    def _validate_observed_nodes(cls, value: list[str]) -> list[str]:
        cleaned = [node.strip() for node in value if node and node.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("observed_nodes must be unique")
        return cleaned

    @field_validator("measurements")
    @classmethod
    def _validate_measurements(cls, value: list[MeasurementPlan]) -> list[MeasurementPlan]:
        if not value:
            raise ValueError("measurements must not be empty")
        metric_names = [item.metric_name for item in value]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("measurement metric_name values must be unique")
        return value

    @model_validator(mode="after")
    def _validate_for_analysis(self) -> "TestbenchPlan":
        if self.analysis_type == AnalysisType.OP:
            return self
        if self.analysis_type == AnalysisType.DC and self.simulation_parameters.dc_source:
            return self
        if self.analysis_type == AnalysisType.AC:
            if self.simulation_parameters.frequency_start_hz is None:
                raise ValueError("AC plans require frequency_start_hz")
            if self.simulation_parameters.frequency_stop_hz is None:
                raise ValueError("AC plans require frequency_stop_hz")
            if self.simulation_parameters.points_per_decade is None:
                raise ValueError("AC plans require points_per_decade")
        if self.analysis_type == AnalysisType.TRAN:
            if self.simulation_parameters.stop_time_s is None:
                raise ValueError("TRAN plans require stop_time_s")
            if self.simulation_parameters.time_step_s is None:
                raise ValueError("TRAN plans require time_step_s")
        return self

