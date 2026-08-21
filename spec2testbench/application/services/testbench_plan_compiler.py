from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench import (
    TestBench,
    Stimulus,
    AnalysisConfig,
    AnalysisType as TBAnalysisType,
    Measurement,
)
from spec2testbench.domain.entities.testbench_plan import (
    TestbenchPlan,
    AnalysisType,
)


@dataclass
class CompiledTestbenchPlan:
    """Deterministic compilation result used by hybrid experiments."""

    testbench: TestBench
    measurement_requests: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __getattr__(self, name: str):
        # Backwards-compatible convenience for callers that treated compile()
        # as returning the TestBench directly.
        return getattr(self.testbench, name)


class TestbenchPlanCompiler:
    def compile(
        self,
        plan: TestbenchPlan,
        specification: Specification,
        netlist_path: Optional[Path] = None,
    ) -> CompiledTestbenchPlan:

        analysis_map = {
            AnalysisType.OP: TBAnalysisType.OP,
            AnalysisType.DC: TBAnalysisType.DC,
            AnalysisType.AC: TBAnalysisType.AC,
            AnalysisType.TRAN: TBAnalysisType.TRANSIENT,
            AnalysisType.FOURIER: TBAnalysisType.FOURIER,
        }

        sp = plan.simulation_parameters

        params = {
            key: value
            for key, value in {
                "start_freq": sp.frequency_start_hz,
                "stop_freq": sp.frequency_stop_hz,
                "points_per_decade": sp.points_per_decade,
                "source": sp.dc_source,
                "start": sp.dc_start,
                "stop": sp.dc_stop,
                "step": sp.dc_step,
                "start_time": sp.start_time_s,
                "end_time": sp.stop_time_s,
                "step_time": sp.time_step_s,
            }.items()
            if value is not None
        }

        stimuli = [
            Stimulus(
                name=s.source_name,
                type=s.stimulus_type.lower(),
                parameters=dict(s.parameters),
                node_positive=s.target_node,
                node_negative=s.reference_node,
            )
            for s in plan.stimuli
        ]

        measurements = [
            Measurement(
                name=m.metric_name,
                expression=m.metric_name,
                unit=m.expected_unit,
                node=m.output_node,
            )
            for m in plan.measurements
        ]

        # ------------------------------------------------------------------
        # Ports declared by the specification.
        #
        # For a conventional single-ended metric:
        #   input_nodes[0]  -> Vin
        #   output_nodes[0] -> Vout
        #
        # For differential_gain_db:
        #   input_nodes[0]  -> positive differential input
        #   input_nodes[1]  -> negative differential input
        #   output_nodes[0] -> selected single-ended output
        # ------------------------------------------------------------------
        input_nodes = specification.ports.get("input") or []
        output_nodes = specification.ports.get("output") or []

        input_node = input_nodes[0] if input_nodes else None
        output_node = output_nodes[0] if output_nodes else None

        # A validated LLM plan may explicitly identify the input/output node.
        # This behaviour is retained for the existing single-ended metrics.
        if plan.measurements:
            input_node = plan.measurements[0].input_node or input_node
            output_node = plan.measurements[0].output_node or output_node

        testbench = TestBench(
            name=f"{plan.case_id}_llm_compiled",
            category="llm_plan",
            circuit_name=specification.name,
            netlist_path=str(netlist_path) if netlist_path else None,
            stimuli=stimuli,
            analyses=[
                AnalysisConfig(
                    type=analysis_map[plan.analysis_type],
                    parameters=params,
                )
            ],
            measurements=measurements,
            temperature=specification.nominal_temperature,
            metadata={
                "case_id": plan.case_id,
                "required_metrics": [m.name for m in measurements],
                "compiled_from_llm_plan": True,
                "llm_plan": plan.model_dump(mode="json"),
                "input_node": input_node,
                "output_node": output_node,
                "measurement_context": {
                    "input_node": input_node,
                    "output_node": output_node,
                },
                "needs_op_bias_probe": (
                    "minimum_device_drain_current_a"
                    in {m.name for m in measurements}
                ),
            },
        )

        measurement_requests: list[dict[str, Any]] = []

        for measurement_plan in plan.measurements:
            request: dict[str, Any] = {
                "metric_name": measurement_plan.metric_name,
                "analysis_type": measurement_plan.analysis_type.value,
                "backend_preference": measurement_plan.backend_preference,
                "input_node": measurement_plan.input_node,
                "output_node": measurement_plan.output_node,
                "expected_unit": measurement_plan.expected_unit,
            }

            # --------------------------------------------------------------
            # Existing single-ended AC metrics.
            #
            # Expected WRDATA layout:
            #
            #   column 0 : frequency
            #   column 1 : Re(Vin)
            #   column 2 : Im(Vin)
            #   column 3 : Re(Vout)
            #   column 4 : Im(Vout)
            # --------------------------------------------------------------
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
                request.update(
                    {
                        "in_real_column": 1,
                        "in_imag_column": 2,
                        "out_real_column": 3,
                        "out_imag_column": 4,
                    }
                )

            # --------------------------------------------------------------
            # External BC547A differential-pair extension.
            #
            # Definition:
            #
            #   Vid = V(input_positive) - V(input_negative)
            #
            #   Ad = V(output) / Vid
            #
            #   differential_gain_db = 20*log10(abs(Ad))
            #
            # Expected WRDATA layout:
            #
            #   column 0 : frequency
            #   column 1 : Re(Vin+)
            #   column 2 : Im(Vin+)
            #   column 3 : Re(Vin-)
            #   column 4 : Im(Vin-)
            #   column 5 : Re(Vout)
            #   column 6 : Im(Vout)
            # --------------------------------------------------------------
            elif measurement_plan.metric_name == "differential_gain_db":

                if len(input_nodes) < 2:
                    raise ValueError(
                        "differential_gain_db requires two input nodes"
                    )

                if len(output_nodes) < 1:
                    raise ValueError(
                        "differential_gain_db requires at least one output node"
                    )

                request.update(
                    {
                        "input_positive_node": input_nodes[0],
                        "input_negative_node": input_nodes[1],
                        "output_node": output_nodes[0],
                        "in_pos_real_column": 1,
                        "in_pos_imag_column": 2,
                        "in_neg_real_column": 3,
                        "in_neg_imag_column": 4,
                        "out_real_column": 5,
                        "out_imag_column": 6,
                        "reference_frequency_hz": 1000.0,
                    }
                )

            measurement_requests.append(request)

        testbench.metadata["measurement_requests"] = measurement_requests

        return CompiledTestbenchPlan(
            testbench=testbench,
            measurement_requests=measurement_requests,
        )
