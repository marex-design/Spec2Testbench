from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, Stimulus, TestBench
from ...domain.entities.testbench_plan import (
    AnalysisType as PlanAnalysisType,
    MeasurementBackendPreference,
    TestbenchPlan,
)
from ...infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from .benchmark_deck_normalizer import BenchmarkDeckNormalizer
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
        signal_defaults = self._load_signal_defaults(specification)

        stimuli = [
            self._compile_stimulus(stimulus, primary_input, specification, signal_defaults)
            for stimulus in plan.stimuli
        ]
        analyses = [self._compile_analysis(plan)]
        measurements = []
        measurement_requests = []
        input_ac_magnitude = self._infer_input_ac_magnitude(stimuli, primary_input)
        reference_frequency_hz = self._infer_reference_frequency_hz(plan)

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
                    input_ac_magnitude=input_ac_magnitude,
                    reference_frequency_hz=reference_frequency_hz,
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
                "input_ac_magnitude": input_ac_magnitude,
                "reference_frequency_hz": reference_frequency_hz,
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
        signal_defaults: dict[str, dict[str, Any]],
    ) -> Stimulus:
        parameters = dict(stimulus_plan.parameters)
        stimulus_type = stimulus_plan.stimulus_type.value.lower()
        signal_default = self._resolve_signal_default(signal_defaults, stimulus_plan)
        default_dc_value = signal_default.get("dc_value")
        if stimulus_type == "triangle":
            amplitude = float(parameters.get("amplitude", 1.0))
            offset = float(
                parameters.get(
                    "offset",
                    default_dc_value if default_dc_value is not None else specification.common_mode_voltage,
                )
            )
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
        if default_dc_value is not None and stimulus_type in {"ac", "pulse", "sin", "pwl"}:
            parameters.setdefault("dc_value", default_dc_value)
        if stimulus_type == "sin" and default_dc_value is not None:
            parameters.setdefault("offset", default_dc_value)
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
        input_ac_magnitude: float | None,
        reference_frequency_hz: float | None,
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

        if measurement_plan.metric_name in {
            "dc_gain",
            "dc_gain_db",
            "cutoff_frequency_hz",
            "bandwidth",
            "lowpass_attenuation_db",
            "lowpass_monotonicity_percent",
            "highpass_attenuation_db",
            "highpass_monotonicity_percent",
            "bandpass_peak_separation_db",
            "bandstop_notch_depth_db",
        }:
            request.setdefault("in_real_column", 1)
            request.setdefault("in_imag_column", 2)
            request.setdefault("out_real_column", 3)
            request.setdefault("out_imag_column", 4)
            request.setdefault("input_ac_magnitude", input_ac_magnitude)
            request.setdefault("reference_frequency_hz", reference_frequency_hz)
        elif measurement_plan.metric_name in {"frequency_hz", "oscillator_frequency", "startup_amplitude"}:
            request.setdefault("time_column", 0)
            request.setdefault("value_column", 1)
        elif measurement_plan.metric_name in {"v_t_plus", "v_t_minus", "hysteresis_width"}:
            request.setdefault("time_column", 0)
            request.setdefault("vin_column", 1)
            request.setdefault("vout_column", 2)
        return request

    def _load_signal_defaults(self, specification: Specification) -> dict[str, dict[str, Any]]:
        netlist_path = self._resolve_spec_netlist_path(specification)
        if netlist_path is None:
            return {}
        try:
            result = BenchmarkDeckNormalizer().normalize(
                netlist_path,
                case_id=specification.case_id or specification.name,
            )
        except Exception:
            return {}

        defaults: dict[str, dict[str, Any]] = {}
        for source in result.sources:
            if source.role != "SIGNAL_SOURCE":
                continue
            payload = {
                "dc_value": source.original_dc_value,
                "ac_magnitude": source.original_ac_magnitude,
                "definition": source.original_definition,
            }
            defaults[source.name.strip().lower()] = payload
            defaults[source.positive_node.strip().lower()] = payload
        return defaults

    @staticmethod
    def _resolve_signal_default(
        signal_defaults: dict[str, dict[str, Any]],
        stimulus_plan,
    ) -> dict[str, Any]:
        for key in (
            str(getattr(stimulus_plan, "source_name", "")).strip().lower(),
            str(getattr(stimulus_plan, "target_node", "")).strip().lower(),
        ):
            if key and key in signal_defaults:
                return signal_defaults[key]
        return {}

    @staticmethod
    def _resolve_spec_netlist_path(specification: Specification) -> Path | None:
        raw_specs = specification.raw_specs or ""
        if not raw_specs.strip():
            return None
        try:
            payload = yaml.safe_load(raw_specs) or {}
        except yaml.YAMLError:
            return None
        netlist_hint = None
        source = payload.get("source", {})
        if isinstance(source, dict):
            netlist_hint = source.get("netlist")
        if not netlist_hint:
            provenance = payload.get("provenance", {})
            if isinstance(provenance, dict):
                dut = provenance.get("dut", {})
                if isinstance(dut, dict):
                    netlist_hint = dut.get("path")
        if not netlist_hint:
            return None
        netlist_path = Path(str(netlist_hint))
        if netlist_path.exists():
            return netlist_path
        candidate = Path.cwd() / netlist_path
        return candidate if candidate.exists() else None

    @staticmethod
    def _infer_input_ac_magnitude(stimuli: list[Stimulus], primary_input: str) -> float | None:
        for stimulus in stimuli:
            if stimulus.node_positive != primary_input:
                continue
            if stimulus.type == "ac":
                try:
                    return float(stimulus.parameters.get("magnitude", 1.0))
                except (TypeError, ValueError):
                    return None
            if stimulus.parameters.get("ac_magnitude") is not None:
                try:
                    return float(stimulus.parameters["ac_magnitude"])
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _infer_reference_frequency_hz(plan: TestbenchPlan) -> float | None:
        if plan.analysis_type != PlanAnalysisType.AC:
            return None
        try:
            return float(plan.simulation_parameters.frequency_start_hz)
        except (TypeError, ValueError):
            return None
