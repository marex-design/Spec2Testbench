from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, Stimulus, TestBench
from ...domain.entities.testbench_plan import (
    AnalysisType as PlanAnalysisType,
    MeasurementBackendPreference,
    TestbenchPlan,
)
from ...infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from .llm_metric_registry import get_metric_definition


@dataclass(frozen=True)
class CompiledTestbenchPlan:
    testbench: TestBench
    measurement_requests: list[dict[str, Any]]
    measurement_backend: str


class TestbenchPlanCompiler:
    def compile(
        self,
        plan: TestbenchPlan,
        *,
        specification: Specification,
    ) -> CompiledTestbenchPlan:
        primary_input = specification.input_nodes[0] if specification.input_nodes else "vin"
        primary_output = specification.output_nodes[0] if specification.output_nodes else "vout"
        output_threshold = float((specification.vdd + specification.vss) / 2.0)

        stimuli = [
            self._compile_stimulus(stimulus, primary_input, specification)
            for stimulus in plan.stimuli
        ]
        analyses = [self._compile_analysis(plan)]
        measurements = []
        measurement_requests = []

        for measurement_plan in plan.measurements:
            definition = get_metric_definition(measurement_plan.metric_name)
            expression = definition.semantic_definition if definition else measurement_plan.metric_name
            measurements.append(
                Measurement(
                    name=measurement_plan.metric_name,
                    expression=expression,
                    expected_min=specification.get_metric_min(measurement_plan.metric_name),
                    expected_max=specification.get_metric_max(measurement_plan.metric_name),
                    unit=measurement_plan.expected_unit,
                    node=measurement_plan.output_node or primary_output,
                )
            )
            measurement_requests.append(
                self._build_measurement_request(
                    measurement_plan,
                    primary_input=measurement_plan.input_node or primary_input,
                    primary_output=measurement_plan.output_node or primary_output,
                    output_threshold=output_threshold,
                )
            )

        plan_backend = self._summarize_backend_preferences(plan)
        category = self._category_for_analysis(plan.analysis_type)
        metadata = {
            "required_metrics": [item.metric_name for item in plan.measurements],
            "measurement": {
                "required_backend": plan_backend if plan_backend != "MIXED" else None,
                "allow_backend_fallback": True,
            },
            "measurement_context": {
                "input_node": primary_input,
                "output_node": primary_output,
                "output_threshold": output_threshold,
            },
            "measurement_requests": measurement_requests,
            "llm_testbench_plan": plan.model_dump(mode="json"),
            "provider_mode": plan.provider_mode,
            "scientific_llm_evidence": plan.scientific_llm_evidence,
            "knowledge_version": plan.knowledge_version,
            "knowledge_bundle_sha256": plan.knowledge_bundle_sha256,
            # Frequency-only specs still need a scientifically meaningful
            # oscillation guard instead of the old arbitrary 1e-6 V fallback.
            "oscillation_amplitude_threshold": float(specification.get_metric_min("startup_amplitude") or 1e-12),
            "oscillation_minimum_cycles": 3,
            "oscillation_max_period_cv": 0.25,
            "oscillation_min_spectral_prominence": 5.0,
        }

        testbench = TestBench(
            name=f"{plan.case_id}_{category}_compiled",
            category=category,
            circuit_name=specification.name,
            case_id=plan.case_id,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
            description=plan.concise_rationale,
            temperature=specification.nominal_temperature,
            metadata=metadata,
        )
        testbench.generate_pyspice_code()

        return CompiledTestbenchPlan(
            testbench=testbench,
            measurement_requests=measurement_requests,
            measurement_backend=plan_backend,
        )

    def compile_to_spice_deck(
        self,
        plan: TestbenchPlan,
        *,
        specification: Specification,
        netlist_path: Path,
    ) -> str:
        compiled = self.compile(plan, specification=specification)
        simulator = PySpiceSimulator(allow_mock=False)
        return simulator._generate_measure_deck(netlist_path, compiled.testbench, Path("measures.txt"), Path("vectors.dat"))

    def _compile_stimulus(
        self,
        stimulus_plan,
        primary_input: str,
        specification: Specification,
    ) -> Stimulus:
        parameters = dict(stimulus_plan.parameters)
        stimulus_type = stimulus_plan.stimulus_type.value.lower()
        if stimulus_type == "triangle":
            amplitude = float(parameters.get("amplitude", 1.0))
            offset = float(parameters.get("offset", specification.common_mode_voltage))
            period = parameters.get("period", "1u")
            parameters = {
                "points": [
                    (0, offset - amplitude),
                    (0.25, offset + amplitude),
                    (0.75, offset - amplitude),
                    (1.0, offset - amplitude),
                ],
                "period": period,
            }
            stimulus_type = "pwl"
        return Stimulus(
            name=stimulus_plan.source_name,
            type=stimulus_type,
            parameters=parameters,
            node_positive=stimulus_plan.target_node or primary_input,
            node_negative="0",
        )

    def _compile_analysis(self, plan: TestbenchPlan) -> AnalysisConfig:
        mapping = {
            PlanAnalysisType.OP: AnalysisType.DC,
            PlanAnalysisType.DC: AnalysisType.DC,
            PlanAnalysisType.AC: AnalysisType.AC,
            PlanAnalysisType.TRAN: AnalysisType.TRANSIENT,
        }
        params = plan.simulation_parameters
        if plan.analysis_type == PlanAnalysisType.OP:
            return AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})
        if plan.analysis_type == PlanAnalysisType.DC:
            return AnalysisConfig(
                type=AnalysisType.DC,
                parameters={
                    "source": params.dc_source or "VIN",
                    "start": params.dc_start,
                    "stop": params.dc_stop,
                    "step": params.dc_step,
                    "force_sweep": True,
                },
            )
        if plan.analysis_type == PlanAnalysisType.AC:
            return AnalysisConfig(
                type=AnalysisType.AC,
                parameters={
                    "sweep_type": "dec",
                    "points_per_decade": params.points_per_decade,
                    "start_freq": params.frequency_start_hz,
                    "stop_freq": params.frequency_stop_hz,
                },
            )
        return AnalysisConfig(
            type=mapping[plan.analysis_type],
            parameters={
                "start_time": params.start_time_s or 0.0,
                "step_time": params.time_step_s,
                "end_time": params.stop_time_s,
            },
        )

    @staticmethod
    def _category_for_analysis(analysis_type: PlanAnalysisType) -> str:
        mapping = {
            PlanAnalysisType.OP: "dc",
            PlanAnalysisType.DC: "dc",
            PlanAnalysisType.AC: "ac",
            PlanAnalysisType.TRAN: "transient",
        }
        return mapping[analysis_type]

    @staticmethod
    def _summarize_backend_preferences(plan: TestbenchPlan) -> str:
        preferences = {measurement.backend_preference.value for measurement in plan.measurements}
        preferences.discard(MeasurementBackendPreference.AUTO.value)
        if not preferences:
            return "AUTO"
        if len(preferences) == 1:
            return next(iter(preferences))
        return "MIXED"

    @staticmethod
    def _build_measurement_request(
        measurement_plan,
        *,
        primary_input: str,
        primary_output: str,
        output_threshold: float,
    ) -> dict[str, Any]:
        request = {
            "name": measurement_plan.metric_name,
            "unit": measurement_plan.expected_unit,
            "preferred_backend": measurement_plan.backend_preference.value,
            "output_threshold": output_threshold,
            "input_node": primary_input,
            "output_node": primary_output,
        }
        request.update(dict(measurement_plan.measurement_parameters))

        definition = get_metric_definition(measurement_plan.metric_name)
        if definition is not None:
            request.setdefault("metric_definition_version", definition.definition_version)
            request.setdefault("quantity_type", definition.quantity_type.value if definition.quantity_type else None)
            request.setdefault("measurement_expression_id", definition.measurement_expression_id)
            request.setdefault("semantic_guards", sorted(definition.required_semantic_guards.keys()))

        if measurement_plan.metric_name in {"dc_gain", "dc_gain_db", "cutoff_frequency_hz", "bandwidth"}:
            request.setdefault("in_real_column", 1)
            request.setdefault("in_imag_column", 2)
            request.setdefault("out_real_column", 3)
            request.setdefault("out_imag_column", 4)
        elif measurement_plan.metric_name in {"frequency_hz", "oscillator_frequency", "startup_amplitude"}:
            request.setdefault("time_column", 0)
            request.setdefault("value_column", 1)
        elif measurement_plan.metric_name in {"v_t_plus", "v_t_minus", "hysteresis_width"}:
            request.setdefault("time_column", 0)
            request.setdefault("vin_column", 1)
            request.setdefault("vout_column", 2)
        return request
