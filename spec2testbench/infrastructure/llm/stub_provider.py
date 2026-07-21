from __future__ import annotations

import json
import time
from typing import Any

from ...application.ports.llm_provider import LLMProvider, LLMRequest, LLMResponse
from ...domain.entities.testbench_plan import (
    AnalysisType,
    MeasurementBackendPreference,
    SimulationParameters,
    StimulusPlan,
    StimulusType,
    TestbenchPlan,
)


class DeterministicStubProvider(LLMProvider):
    """Deterministic non-network provider for smoke tests and local experiments."""

    def list_models(self) -> list[str]:
        return ["deepseek-stub-v1"]

    def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        payload = request.user_payload
        plan = self._build_plan(payload)
        content = plan.model_dump_json()
        return LLMResponse(
            content=content,
            provider="deepseek_stub",
            model=request.model,
            finish_reason="stop",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            latency_seconds=time.perf_counter() - started,
            raw_metadata={"attempts": [{"attempt_number": 1, "http_status": 200, "error_type": None, "retryable": False, "delay_before_retry": 0.0, "final_status": "SUCCESS"}]},
        )

    def _build_plan(self, payload: dict[str, Any]) -> TestbenchPlan:
        case_id = payload.get("case_id", "stub_case")
        requested_metrics = payload.get("requested_metrics", [])
        circuit_family = payload.get("circuit_family", "")
        available_nodes = payload.get("available_nodes", [])
        supply_information = payload.get("supply_information", {})
        supported_capabilities = payload.get("supported_capabilities", {})
        metric_definitions = {
            item["metric_name"]: item
            for item in supported_capabilities.get("supported_metric_definitions", [])
        }
        deterministic_summary = payload.get("deterministic_plan_summary", {})

        input_node = self._choose_input_node(available_nodes, deterministic_summary)
        output_node = self._choose_output_node(available_nodes, deterministic_summary)
        analysis_type = self._choose_analysis_type(
            requested_metrics,
            deterministic_summary,
            supported_capabilities.get("supported_analysis_types", []),
            metric_definitions,
        )

        stimuli = self._build_stimuli(
            analysis_type=analysis_type,
            input_node=input_node,
            circuit_family=circuit_family,
            supply_information=supply_information,
        )
        observed_nodes = [output_node] if output_node else []
        if any(metric in {"propagation_delay", "propagation_delay_s", "v_t_plus", "v_t_minus", "hysteresis_width"} for metric in requested_metrics) and input_node:
            observed_nodes.append(input_node)

        measurements = []
        for metric_name in requested_metrics:
            definition = metric_definitions.get(metric_name, {})
            preferred_backend = definition.get("preferred_backend", MeasurementBackendPreference.AUTO.value)
            measurements.append(
                {
                    "metric_name": metric_name,
                    "analysis_type": analysis_type.value,
                    "input_node": input_node if "input" in definition.get("required_nodes", []) else None,
                    "output_node": output_node if "output" in definition.get("required_nodes", []) else None,
                    "expected_unit": definition.get("expected_unit", ""),
                    "backend_preference": preferred_backend,
                    "measurement_parameters": {},
                }
            )

        simulation_parameters = self._build_simulation_parameters(
            analysis_type=analysis_type,
            input_source=(stimuli[0].source_name if stimuli else "vin"),
            circuit_family=circuit_family,
        )
        return TestbenchPlan.model_validate(
            {
                "case_id": case_id,
                "analysis_type": analysis_type.value,
                "stimuli": [item.model_dump(mode="json") for item in stimuli],
                "observed_nodes": list(dict.fromkeys(node for node in observed_nodes if node)),
                "measurements": measurements,
                "simulation_parameters": simulation_parameters.model_dump(mode="json"),
                "concise_rationale": "Deterministic stub provider generated a netlist-aware JSON TestbenchPlan.",
            }
        )

    @staticmethod
    def _choose_input_node(available_nodes: list[str], summary: dict[str, Any]) -> str | None:
        for stimulus in summary.get("stimuli", []):
            node = stimulus.get("node_positive")
            if node:
                return node
        for token in ("vin", "in", "inp", "in1"):
            for node in available_nodes:
                if token in node.lower():
                    return node
        return available_nodes[0] if available_nodes else None

    @staticmethod
    def _choose_output_node(available_nodes: list[str], summary: dict[str, Any]) -> str | None:
        for measurement in summary.get("measurements", []):
            node = measurement.get("node")
            if node:
                return node
        for token in ("vout", "out", "outp"):
            for node in available_nodes:
                if token in node.lower():
                    return node
        return available_nodes[-1] if available_nodes else None

    @staticmethod
    def _choose_analysis_type(
        requested_metrics: list[str],
        summary: dict[str, Any],
        supported_analysis_types: list[str],
        metric_definitions: dict[str, dict[str, Any]],
    ) -> AnalysisType:
        summary_preferences = []
        for item in summary.get("analyses", []):
            normalized = str(item.get("type", "")).upper()
            if normalized in AnalysisType.__members__:
                summary_preferences.append(AnalysisType[normalized])

        metric_candidates = []
        for metric_name in requested_metrics:
            definition = metric_definitions.get(metric_name, {})
            compatible = definition.get("compatible_analysis_types", [])
            if compatible:
                metric_candidates.append({AnalysisType(value) for value in compatible})

        if metric_candidates:
            common_candidates = set.intersection(*metric_candidates)
            if common_candidates:
                for preferred in summary_preferences:
                    if preferred in common_candidates:
                        return preferred
                for preferred in (AnalysisType.OP, AnalysisType.DC, AnalysisType.AC, AnalysisType.TRAN):
                    if preferred in common_candidates:
                        return preferred

            ranked_counts: dict[AnalysisType, int] = {}
            for candidates in metric_candidates:
                for analysis in candidates:
                    ranked_counts[analysis] = ranked_counts.get(analysis, 0) + 1
            ranked = sorted(
                ranked_counts.items(),
                key=lambda item: (
                    -item[1],
                    summary_preferences.index(item[0]) if item[0] in summary_preferences else len(summary_preferences),
                    (AnalysisType.OP, AnalysisType.DC, AnalysisType.AC, AnalysisType.TRAN).index(item[0]),
                ),
            )
            if ranked:
                return ranked[0][0]

        for preferred in summary_preferences:
            return preferred
        if supported_analysis_types:
            return AnalysisType(supported_analysis_types[0])
        return AnalysisType.OP

    @staticmethod
    def _build_stimuli(
        *,
        analysis_type: AnalysisType,
        input_node: str | None,
        circuit_family: str,
        supply_information: dict[str, Any],
    ) -> list[StimulusPlan]:
        if not input_node:
            return []
        vss = float(supply_information.get("vss", 0.0))
        vdd = float(supply_information.get("vdd", 5.0))
        vcm = float(supply_information.get("common_mode_voltage", (vdd + vss) / 2.0))
        if analysis_type == AnalysisType.OP:
            return []
        if analysis_type == AnalysisType.DC:
            return [
                StimulusPlan(
                    source_name="vin",
                    target_node=input_node,
                    stimulus_type=StimulusType.DC,
                    parameters={"value": vcm},
                )
            ]
        if analysis_type == AnalysisType.AC:
            return [
                StimulusPlan(
                    source_name="vin",
                    target_node=input_node,
                    stimulus_type=StimulusType.AC,
                    parameters={"magnitude": 1.0, "dc_value": vcm},
                )
            ]
        if "oscillator" in circuit_family.lower():
            return []
        return [
            StimulusPlan(
                source_name="vin",
                target_node=input_node,
                stimulus_type=StimulusType.PULSE,
                parameters={
                    "v1": vss,
                    "v2": vdd,
                    "delay": 0.0,
                    "rise": 1e-6,
                    "fall": 1e-6,
                    "width": 2e-4,
                    "period": 4e-4,
                },
            )
        ]

    @staticmethod
    def _build_simulation_parameters(
        *,
        analysis_type: AnalysisType,
        input_source: str,
        circuit_family: str,
    ) -> SimulationParameters:
        if analysis_type == AnalysisType.OP:
            return SimulationParameters()
        if analysis_type == AnalysisType.DC:
            return SimulationParameters(dc_source=input_source, dc_start=0.0, dc_stop=5.0, dc_step=0.1)
        if analysis_type == AnalysisType.AC:
            return SimulationParameters(
                frequency_start_hz=1.0,
                frequency_stop_hz=1e9,
                points_per_decade=20,
            )
        if "oscillator" in circuit_family.lower():
            return SimulationParameters(start_time_s=0.0, stop_time_s=2e-3, time_step_s=1e-6)
        return SimulationParameters(start_time_s=0.0, stop_time_s=2e-3, time_step_s=1e-6)
