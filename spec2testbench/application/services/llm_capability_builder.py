from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.entities.testbench_plan import (
    AnalysisType,
    MeasurementBackendPreference,
)
from ...infrastructure.simulator.netlist_parser import NetlistParser
from .llm_metric_registry import (
    SUPPORTED_STIMULUS_TYPES,
    get_metric_definition,
)


@dataclass(frozen=True)
class LLMCapabilityPayload:
    case_id: str
    circuit_family: str
    available_nodes: list[str]
    supply_information: dict[str, Any]
    requested_metrics: list[str]
    supported_analysis_types: list[str]
    supported_stimulus_types: list[str]
    supported_measurement_backends: list[str]
    supported_metric_definitions: list[dict[str, Any]]
    deterministic_plan_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "circuit_family": self.circuit_family,
            "available_nodes": self.available_nodes,
            "supply_information": self.supply_information,
            "requested_metrics": self.requested_metrics,
            "supported_capabilities": {
                "supported_analysis_types": self.supported_analysis_types,
                "supported_stimulus_types": self.supported_stimulus_types,
                "supported_measurement_backends": self.supported_measurement_backends,
                "supported_metric_definitions": self.supported_metric_definitions,
            },
            "deterministic_plan_summary": self.deterministic_plan_summary,
        }

    def sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LLMCapabilityBuilder:
    def __init__(self, netlist_parser: NetlistParser | None = None) -> None:
        self._netlist_parser = netlist_parser or NetlistParser()

    def build(
        self,
        specification: Specification,
        *,
        netlist_path: Path,
        deterministic_testbench: TestBench | None = None,
    ) -> LLMCapabilityPayload:
        netlist = self._netlist_parser.parse(netlist_path)
        requested_metrics = list(specification.performance_targets.keys())
        metric_definitions = []
        analysis_values: set[str] = set()

        for metric_name in requested_metrics:
            definition = get_metric_definition(metric_name)
            if definition is None:
                continue
            metric_definitions.append(definition.to_dict())
            analysis_values.update(item.value for item in definition.compatible_analysis_types)

        analysis_values = analysis_values or {AnalysisType.OP.value}
        available_nodes = sorted(
            {
                *netlist.nodes,
                *specification.input_nodes,
                *specification.output_nodes,
                "0",
                "gnd",
                "GND",
            }
        )
        supply_information = {
            "vdd": specification.vdd,
            "vss": specification.vss,
            "common_mode_voltage": specification.common_mode_voltage,
            "load_capacitance_f": specification.load_capacitance,
            "load_resistance_ohm": specification.load_resistance,
            "nominal_temperature_c": specification.nominal_temperature,
        }

        return LLMCapabilityPayload(
            case_id=specification.case_id or specification.name,
            circuit_family=specification.circuit_type.value,
            available_nodes=available_nodes,
            supply_information=supply_information,
            requested_metrics=requested_metrics,
            supported_analysis_types=sorted(analysis_values),
            supported_stimulus_types=[item.value for item in SUPPORTED_STIMULUS_TYPES],
            supported_measurement_backends=[
                MeasurementBackendPreference.NGSPICE_MEASURE.value,
                MeasurementBackendPreference.NGSPICE_WRDATA.value,
                MeasurementBackendPreference.AUTO.value,
            ],
            supported_metric_definitions=metric_definitions,
            deterministic_plan_summary=self._summarize_testbench(deterministic_testbench),
        )

    def _summarize_testbench(self, testbench: TestBench | None) -> dict[str, Any]:
        if testbench is None:
            return {}
        return {
            "name": testbench.name,
            "category": testbench.category,
            "stimuli": [
                {
                    "name": item.name,
                    "type": item.type,
                    "node_positive": item.node_positive,
                    "node_negative": item.node_negative,
                    "parameters": dict(item.parameters),
                }
                for item in testbench.stimuli
            ],
            "analyses": [
                {
                    "type": item.type.value,
                    "parameters": dict(item.parameters),
                }
                for item in testbench.analyses
            ],
            "measurements": [
                {
                    "name": item.name,
                    "expression": item.expression,
                    "unit": item.unit,
                    "node": item.node,
                }
                for item in testbench.measurements
            ],
            "required_metrics": list((testbench.metadata or {}).get("required_metrics", [])),
        }

