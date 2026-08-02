from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...domain.entities.analysis_harness import AnalysisHarnessPolicy, SourceOverridePolicy
from ...domain.entities.specification import Specification
from ...domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, Stimulus, TestBench
from ...infrastructure.testbench.testbench_generator import TestBenchGenerator
from .benchmark_deck_normalizer import BenchmarkDeckNormalizer
from .llm_metric_registry import get_metric_definition


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_DIR = ROOT / "benchmark" / "analogcoder_pro"
MANIFEST_PATH = BENCHMARK_DIR / "manifest.csv"

DC_METRICS = {"operating_point", "vout_dc", "quiescent_current", "idd", "power"}
AC_METRICS = {"dc_gain", "dc_gain_db", "bandwidth", "cutoff_frequency_hz", "unity_gain_frequency", "ugbw", "phase_margin"}
OSCILLATION_METRICS = {"frequency_hz", "oscillator_frequency", "startup_amplitude"}
SCHMITT_METRICS = {"v_t_plus", "v_t_minus", "hysteresis_width"}
TRANSIENT_METRICS = {"slew_rate", "settling_time", "propagation_delay", "propagation_delay_s"}
SPECTRAL_METRICS = {"thd", "thd_percent", "fundamental_frequency"}


@dataclass(frozen=True)
class NormalizedHarnessContext:
    case_id: str
    short_case_id: str
    harness_metadata: dict[str, Any]
    circuit_metadata: dict[str, Any]
    original_analysis_metadata: list[dict[str, Any]]
    canonical_dut_path: Path
    original_deck_path: Path


@dataclass
class CanonicalHarnessBuild:
    case_id: str
    analysis_key: str
    deck_name: str
    requested_metrics: list[str]
    source_policies: list[SourceOverridePolicy]
    policy: AnalysisHarnessPolicy
    testbench: TestBench
    audit_row: dict[str, Any]


def short_case_id(case_id: str) -> str:
    match = re.search(r"(p\d+)", str(case_id or "").lower())
    if not match:
        raise ValueError(f"Cannot infer normalized case id from {case_id!r}")
    return match.group(1)


@lru_cache(maxsize=1)
def _manifest_rows() -> dict[str, dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {Path(row["netlist"]).stem: row for row in rows}


def _resolve_manifest_case(case_id: str) -> tuple[str, dict[str, str]]:
    manifest_rows = _manifest_rows()
    if case_id in manifest_rows:
        return case_id, manifest_rows[case_id]
    short_id = short_case_id(case_id)
    matches = [(name, row) for name, row in manifest_rows.items() if name.lower().startswith(f"{short_id}_")]
    if len(matches) != 1:
        raise FileNotFoundError(f"Canonical benchmark netlist missing for {case_id}")
    return matches[0]


@lru_cache(maxsize=None)
def _normalize_manifest_case(resolved_case_id: str) -> tuple[Path, Any]:
    row = _manifest_rows()[resolved_case_id]
    netlist_path = BENCHMARK_DIR / row["netlist"]
    result = BenchmarkDeckNormalizer().normalize(
        netlist_path,
        case_id=resolved_case_id,
        declared_type=row["type"],
        declared_topology=row["description"],
        description=row["description"],
    )
    return netlist_path, result


def load_normalized_harness_context(case_id: str) -> NormalizedHarnessContext:
    short_id = short_case_id(case_id)
    resolved_case_id, _ = _resolve_manifest_case(case_id)
    netlist_path, result = _normalize_manifest_case(resolved_case_id)
    return NormalizedHarnessContext(
        case_id=case_id,
        short_case_id=short_id,
        harness_metadata=result.harness_metadata,
        circuit_metadata=result.circuit_metadata,
        original_analysis_metadata=list(result.original_analysis_metadata),
        canonical_dut_path=netlist_path,
        original_deck_path=netlist_path,
    )


def build_case_analysis_testbenches(specification: Specification) -> list[CanonicalHarnessBuild]:
    case_id = specification.case_id or specification.name
    context = load_normalized_harness_context(case_id)
    generator = TestBenchGenerator(use_llm=False)
    builds: list[CanonicalHarnessBuild] = []

    for analysis_key, metric_names in _analysis_groups(specification):
        requested_metrics = [name for name in metric_names if specification.has_metric(name)]
        if not requested_metrics:
            continue
        source_policies = _build_source_policies(specification, context, analysis_key)
        testbench = _build_testbench(
            specification=specification,
            generator=generator,
            context=context,
            analysis_key=analysis_key,
            requested_metrics=requested_metrics,
            source_policies=source_policies,
        )
        policy = _build_analysis_policy(
            specification=specification,
            context=context,
            analysis_key=analysis_key,
            requested_metrics=requested_metrics,
            source_policies=source_policies,
            testbench=testbench,
        )
        testbench.metadata["analysis_harness_policy"] = policy.to_dict()
        testbench.metadata["source_override_policies"] = [item.to_dict() for item in source_policies]
        audit_row = _build_audit_row(
            specification=specification,
            context=context,
            analysis_key=analysis_key,
            requested_metrics=requested_metrics,
            source_policies=source_policies,
            testbench=testbench,
            policy=policy,
        )
        builds.append(
            CanonicalHarnessBuild(
                case_id=case_id,
                analysis_key=analysis_key,
                deck_name=f"{case_id}__{analysis_key}.ckt",
                requested_metrics=requested_metrics,
                source_policies=source_policies,
                policy=policy,
                testbench=testbench,
                audit_row=audit_row,
            )
        )
    return builds


def _analysis_groups(specification: Specification) -> list[tuple[str, list[str]]]:
    metric_names = list(specification.performance_targets.keys())
    groups: list[tuple[str, list[str]]] = []
    if any(name in DC_METRICS for name in metric_names):
        groups.append(("op", [name for name in metric_names if name in DC_METRICS]))
    if any(name in AC_METRICS for name in metric_names):
        groups.append(("ac_gain", [name for name in metric_names if name in AC_METRICS]))
    if any(name in SCHMITT_METRICS for name in metric_names):
        schmitt_requested = [name for name in metric_names if name in SCHMITT_METRICS or name in {"propagation_delay", "propagation_delay_s"}]
        groups.append(("schmitt", schmitt_requested))
    elif any(name in OSCILLATION_METRICS for name in metric_names):
        groups.append(("oscillation", [name for name in metric_names if name in OSCILLATION_METRICS]))
    elif any(name in TRANSIENT_METRICS for name in metric_names):
        groups.append(("transient_delay", [name for name in metric_names if name in TRANSIENT_METRICS]))
    if any(name in SPECTRAL_METRICS for name in metric_names):
        groups.append(("spectral", [name for name in metric_names if name in SPECTRAL_METRICS]))
    return groups


def _build_source_policies(
    specification: Specification,
    context: NormalizedHarnessContext,
    analysis_key: str,
) -> list[SourceOverridePolicy]:
    policies: list[SourceOverridePolicy] = []
    for source in context.harness_metadata.get("sources", []):
        role = str(source.get("role") or "UNKNOWN_SOURCE")
        allowed, forbidden, requires_authority, reason = _override_rules(role, analysis_key)
        policy = SourceOverridePolicy(
            source_name=str(source.get("name", "")),
            source_role=role,
            positive_node=str(source.get("positive_node", "")),
            negative_node=str(source.get("negative_node", "0")),
            original_definition=str(source.get("original_definition", "")),
            original_dc_value=_coerce_optional_float(source.get("original_dc_value")),
            original_ac_magnitude=_coerce_optional_float(source.get("original_ac_magnitude")),
            original_ac_phase=_coerce_optional_float(source.get("original_ac_phase")),
            original_waveform=_normalize_optional_text(source.get("original_waveform")),
            replaceable_by_testbench=bool(source.get("replaceable_by_testbench")) and role == "SIGNAL_SOURCE",
            allowed_overrides_by_analysis={analysis_key: allowed},
            forbidden_overrides_by_analysis={analysis_key: forbidden},
            override_requires_specification=requires_authority,
            override_reason=reason,
            confidence=float(source.get("confidence", 0.0) or 0.0),
            manual_review_required=bool(source.get("manual_review_required")) or role == "UNKNOWN_SOURCE",
        )
        if analysis_key == "ac_gain" and role == "SIGNAL_SOURCE" and _resolve_signal_dc_authority(specification, policy)[0] is None:
            policy = SourceOverridePolicy(
                **{
                    **policy.to_dict(),
                    "manual_review_required": True,
                    "override_reason": "AC harness requires an explicit DC operating point authority before the signal source can be overridden.",
                }
            )
        policies.append(policy)
    return policies


def _override_rules(role: str, analysis_key: str) -> tuple[list[str], list[str], bool, str]:
    if role == "SUPPLY_SOURCE":
        return [], ["dc_value", "ac_magnitude", "waveform", "node_rewiring"], False, "Supply sources are preserved exactly unless an explicit variation campaign authorizes a change."
    if role == "BIAS_SOURCE":
        return [], ["dc_value", "ac_magnitude", "waveform", "node_rewiring"], True, "Bias sources keep their original or explicitly specified value and are never replaced silently."
    if role == "INTERNAL_BIAS_SOURCE":
        return [], ["dc_value", "ac_magnitude", "waveform", "node_rewiring", "ground_referencing"], False, "Internal bias sources are never replaced or converted into stimuli."
    if role == "UNKNOWN_SOURCE":
        return [], ["dc_value", "ac_magnitude", "waveform", "node_rewiring"], True, "Unknown sources are non-replaceable until reviewed manually."

    if analysis_key == "op":
        return ["preserve_original_dc", "drop_irrelevant_ac", "drop_irrelevant_waveform"], ["dc_midpoint_inference", "waveform_injection"], False, "OP decks preserve the original DC operating point and strip non-essential AC or transient modifiers."
    if analysis_key == "ac_gain":
        return ["preserve_original_dc", "normalize_ac_magnitude", "preserve_ac_phase"], ["waveform_injection", "dc_midpoint_inference"], False, "AC decks preserve the benchmark DC operating point and may normalize the small-signal AC magnitude."
    if analysis_key in {"transient_delay", "schmitt", "spectral"}:
        return ["validated_transient_waveform", "explicit_signal_dc_authority"], ["supply_override", "bias_override"], True, "Transient-class decks may replace only the signal source with a validated waveform recipe."
    if analysis_key == "oscillation":
        return [], ["signal_injection", "arbitrary_initial_condition"], False, "Oscillation decks preserve the original oscillator loop and do not inject a periodic input."
    return [], ["unknown_override"], True, "Unhandled analysis kind requires manual review."


def _build_testbench(
    *,
    specification: Specification,
    generator: TestBenchGenerator,
    context: NormalizedHarnessContext,
    analysis_key: str,
    requested_metrics: list[str],
    source_policies: list[SourceOverridePolicy],
) -> TestBench:
    case_id = specification.case_id or specification.name
    output_node = _primary_output_node(specification, context)
    signal_policies = [item for item in source_policies if item.source_role == "SIGNAL_SOURCE"]
    if analysis_key == "op":
        analyses = [_op_analysis(context)]
        stimuli = _op_stimuli(specification, signal_policies)
        testbench = TestBench(
            name=f"{case_id}__op",
            category="dc",
            circuit_name=specification.name,
            case_id=case_id,
            stimuli=stimuli,
            analyses=analyses,
            measurements=_build_measurements(specification, requested_metrics, output_node),
            temperature=specification.nominal_temperature,
        )
        if testbench.analyses and testbench.analyses[0].type == AnalysisType.DC:
            if testbench.stimuli:
                testbench.analyses[0].parameters["source"] = f"V{testbench.stimuli[0].name}"
                dc_value = _coerce_optional_float(testbench.stimuli[0].parameters.get("value"))
                if dc_value is not None:
                    testbench.analyses[0].parameters["start"] = dc_value
                    testbench.analyses[0].parameters["stop"] = dc_value
                    testbench.analyses[0].parameters["step"] = 1.0
                    testbench.analyses[0].parameters["force_sweep"] = True
            else:
                testbench.analyses[0].parameters.pop("force_sweep", None)
    elif analysis_key == "ac_gain":
        analyses = [_ac_analysis(context)]
        stimuli = _ac_stimuli(specification, signal_policies)
        testbench = TestBench(
            name=f"{case_id}__ac_gain",
            category="ac",
            circuit_name=specification.name,
            case_id=case_id,
            stimuli=stimuli,
            analyses=analyses,
            measurements=_build_measurements(specification, requested_metrics, output_node),
            temperature=specification.nominal_temperature,
        )
    elif analysis_key in {"transient_delay", "schmitt", "oscillation"}:
        testbench = generator.generate_for_category(specification, "transient")
        testbench.name = f"{case_id}__{analysis_key}"
        testbench.case_id = case_id
        testbench.measurements = _build_measurements(specification, requested_metrics, output_node)
        testbench.analyses = [_transient_analysis(context, fallback=testbench.analyses[0] if testbench.analyses else None)]
        if analysis_key == "oscillation":
            testbench.stimuli = []
        else:
            testbench.stimuli = _retarget_dynamic_stimuli(testbench.stimuli, signal_policies)
    elif analysis_key == "spectral":
        testbench = generator.generate_for_category(specification, "spectral")
        testbench.name = f"{case_id}__spectral"
        testbench.case_id = case_id
        testbench.measurements = _build_measurements(specification, requested_metrics, output_node)
        testbench.stimuli = _retarget_dynamic_stimuli(testbench.stimuli, signal_policies)
        for analysis in testbench.analyses:
            if analysis.type == AnalysisType.FOURIER:
                analysis.parameters["output_node"] = output_node
    else:
        raise ValueError(f"Unsupported canonical analysis key {analysis_key}")

    testbench.metadata = {
        **dict(testbench.metadata or {}),
        "required_metrics": requested_metrics,
        "measurement": {
            **dict((testbench.metadata or {}).get("measurement", {})),
            "allow_backend_fallback": True,
        },
        "analysis_key": analysis_key,
        "canonical_harness_case_id": case_id,
        "canonical_harness_context": {
            "short_case_id": context.short_case_id,
            "canonical_dut_path": str(context.canonical_dut_path),
            "original_deck_path": str(context.original_deck_path),
        },
    }
    generator._attach_measurement_metadata(testbench, specification)
    _override_measurement_context(
        testbench,
        input_node=signal_policies[0].positive_node if signal_policies else _primary_input_node(specification, context),
        output_node=output_node,
        input_ac_magnitude=_first_ac_magnitude(testbench),
        reference_frequency_hz=_reference_frequency_hz(testbench),
    )
    return testbench


def _build_analysis_policy(
    *,
    specification: Specification,
    context: NormalizedHarnessContext,
    analysis_key: str,
    requested_metrics: list[str],
    source_policies: list[SourceOverridePolicy],
    testbench: TestBench,
) -> AnalysisHarnessPolicy:
    measurement_requests = list((testbench.metadata or {}).get("measurement_requests", []))
    semantic_guards = sorted({guard for request in measurement_requests for guard in request.get("semantic_guards", [])})
    signal_policies = [policy for policy in source_policies if policy.source_role == "SIGNAL_SOURCE"]
    supply_policies = [policy for policy in source_policies if policy.source_role == "SUPPLY_SOURCE"]
    bias_policies = [policy for policy in source_policies if policy.source_role in {"BIAS_SOURCE", "INTERNAL_BIAS_SOURCE"}]
    canonical_signal_definitions = [stimulus.to_spice() for stimulus in testbench.stimuli]
    decision_authority, decision_evidence, reviewer_status = _decision_provenance(specification, signal_policies, analysis_key)
    return AnalysisHarnessPolicy(
        analysis_type=analysis_key,
        metric_names=requested_metrics,
        source_policies=[item.to_dict() for item in source_policies],
        supply_policies=[item.to_dict() for item in supply_policies],
        bias_policies=[item.to_dict() for item in bias_policies],
        signal_policies=[item.to_dict() for item in signal_policies],
        allowed_overrides=sorted({override for item in source_policies for override in item.allowed_overrides_by_analysis.get(analysis_key, [])}),
        forbidden_overrides=sorted({override for item in source_policies for override in item.forbidden_overrides_by_analysis.get(analysis_key, [])}),
        stimulus_recipe={
            "canonical_signal_definitions": canonical_signal_definitions,
            "signal_source_names": [item.source_name for item in signal_policies],
            "separate_analysis_deck": True,
        },
        analysis_parameters={
            "analysis_count": len(testbench.analyses),
            "commands": [analysis.to_spice() for analysis in testbench.analyses],
        },
        measurement_recipes=measurement_requests,
        semantic_guards=semantic_guards,
        provenance={
            "case_id": specification.case_id or specification.name,
            "short_case_id": context.short_case_id,
            "normalized_harness_path": str(context.canonical_dut_path),
            "decision_authority": decision_authority,
            "decision_evidence": decision_evidence,
            "reviewer_status": reviewer_status,
        },
    )


def _build_audit_row(
    *,
    specification: Specification,
    context: NormalizedHarnessContext,
    analysis_key: str,
    requested_metrics: list[str],
    source_policies: list[SourceOverridePolicy],
    testbench: TestBench,
    policy: AnalysisHarnessPolicy,
) -> dict[str, Any]:
    signal_policies = [item for item in source_policies if item.source_role == "SIGNAL_SOURCE"]
    compiled_stimuli = [stimulus for stimulus in testbench.stimuli if not signal_policies or any(stimulus.node_positive == item.positive_node for item in signal_policies)]
    original_signal_definition = " | ".join(item.original_definition for item in signal_policies)
    compiled_signal_definition = " | ".join(stimulus.to_spice() for stimulus in compiled_stimuli)
    original_dc = _join_scalar([item.original_dc_value for item in signal_policies])
    compiled_dc = _join_scalar([stimulus.parameters.get("dc_value", stimulus.parameters.get("value")) for stimulus in compiled_stimuli])
    original_ac = _join_scalar([item.original_ac_magnitude for item in signal_policies])
    compiled_ac = _join_scalar([stimulus.parameters.get("magnitude") or stimulus.parameters.get("ac_magnitude") for stimulus in compiled_stimuli])
    original_waveform = _join_text([item.original_waveform for item in signal_policies])
    compiled_waveform = _join_text([stimulus.type.upper() for stimulus in compiled_stimuli if stimulus.type not in {"dc", "ac"}])
    dc_override = _normalize_text(original_dc) != _normalize_text(compiled_dc)
    ac_override = _normalize_text(original_ac) != _normalize_text(compiled_ac)
    waveform_override = _normalize_text(original_waveform) != _normalize_text(compiled_waveform)
    difference_class = _difference_class(
        analysis_key=analysis_key,
        source_policies=signal_policies,
        compiled_stimuli=compiled_stimuli,
        dc_override=dc_override,
        ac_override=ac_override,
        waveform_override=waveform_override,
    )
    return {
        "case_id": specification.case_id or specification.name,
        "circuit_type": specification.circuit_type.value,
        "analysis_type": analysis_key,
        "requested_metrics": "|".join(requested_metrics),
        "signal_source": "|".join(item.source_name for item in signal_policies),
        "supply_sources": "|".join(item.source_name for item in source_policies if item.source_role == "SUPPLY_SOURCE"),
        "bias_sources": "|".join(item.source_name for item in source_policies if item.source_role == "BIAS_SOURCE"),
        "internal_bias_sources": "|".join(item.source_name for item in source_policies if item.source_role == "INTERNAL_BIAS_SOURCE"),
        "original_signal_definition": original_signal_definition,
        "compiled_signal_definition": compiled_signal_definition,
        "original_dc_value": original_dc,
        "compiled_dc_value": compiled_dc,
        "original_ac_magnitude": original_ac,
        "compiled_ac_magnitude": compiled_ac,
        "original_waveform": original_waveform,
        "compiled_waveform": compiled_waveform,
        "dc_override": dc_override,
        "ac_override": ac_override,
        "waveform_override": waveform_override,
        "override_authorized": difference_class not in {
            "UNAUTHORIZED_DC_OVERRIDE",
            "UNAUTHORIZED_SUPPLY_OVERRIDE",
            "UNAUTHORIZED_BIAS_OVERRIDE",
            "SOURCE_ROLE_CONFUSION",
            "MULTI_ANALYSIS_CONTAMINATION",
            "UNKNOWN_DIFFERENCE",
        },
        "authorization_source": policy.provenance.get("decision_authority", ""),
        "harness_difference_class": difference_class,
        "manual_review_required": any(item.manual_review_required for item in source_policies),
    }


def _build_measurements(specification: Specification, metric_names: list[str], output_node: str) -> list[Measurement]:
    measurements: list[Measurement] = []
    for metric_name in metric_names:
        definition = get_metric_definition(metric_name)
        node = None if metric_name in {"quiescent_current", "idd", "power"} else output_node
        measurements.append(
            Measurement(
                name=metric_name,
                expression=definition.semantic_definition if definition else metric_name,
                expected_min=specification.get_metric_min(metric_name),
                expected_max=specification.get_metric_max(metric_name),
                unit=specification.get_metric_unit(metric_name) or (definition.expected_unit if definition else ""),
                node=node,
            )
        )
    return measurements


def _op_analysis(context: NormalizedHarnessContext) -> AnalysisConfig:
    if any(str(item.get("directive", "")).upper() == ".OP" for item in context.original_analysis_metadata):
        return AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})
    return AnalysisConfig(type=AnalysisType.DC, parameters={"source": "VIN", "start": 0.0, "stop": 0.0, "step": 1.0})


def _ac_analysis(context: NormalizedHarnessContext) -> AnalysisConfig:
    for item in context.original_analysis_metadata:
        if str(item.get("directive", "")).upper() != ".AC":
            continue
        tokens = str(item.get("raw_line", "")).split()
        if len(tokens) >= 5:
            try:
                points = int(float(tokens[2]))
            except ValueError:
                points = 100
            return AnalysisConfig(
                type=AnalysisType.AC,
                parameters={
                    "sweep_type": tokens[1].lower(),
                    "points_per_decade": points,
                    "start_freq": tokens[3],
                    "stop_freq": tokens[4],
                },
            )
    return AnalysisConfig(type=AnalysisType.AC, parameters={"sweep_type": "dec", "points_per_decade": 100, "start_freq": 1, "stop_freq": "1G"})


def _transient_analysis(context: NormalizedHarnessContext, fallback: AnalysisConfig | None) -> AnalysisConfig:
    for item in context.original_analysis_metadata:
        if str(item.get("directive", "")).upper() != ".TRAN":
            continue
        tokens = str(item.get("raw_line", "")).split()
        if len(tokens) >= 3:
            return AnalysisConfig(
                type=AnalysisType.TRANSIENT,
                parameters={
                    "step_time": tokens[1],
                    "end_time": tokens[2],
                    "start_time": tokens[3] if len(tokens) >= 4 else 0,
                },
            )
    if fallback is not None:
        return fallback
    return AnalysisConfig(type=AnalysisType.TRANSIENT, parameters={"step_time": "1n", "end_time": "10u", "start_time": 0})


def _op_stimuli(specification: Specification, signal_policies: list[SourceOverridePolicy]) -> list[Stimulus]:
    stimuli: list[Stimulus] = []
    for policy in signal_policies:
        dc_value, _, _ = _resolve_signal_dc_authority(specification, policy)
        if dc_value is None:
            continue
        stimuli.append(
            Stimulus(
                name=policy.source_name.lower(),
                type="dc",
                parameters={"value": dc_value},
                node_positive=policy.positive_node,
                node_negative=policy.negative_node,
            )
        )
    return stimuli


def _ac_stimuli(specification: Specification, signal_policies: list[SourceOverridePolicy]) -> list[Stimulus]:
    stimuli: list[Stimulus] = []
    for policy in signal_policies:
        dc_value, authority, evidence = _resolve_signal_dc_authority(specification, policy)
        if dc_value is None:
            continue
        magnitude = 1.0 if policy.original_ac_magnitude is not None else 1.0
        phase = policy.original_ac_phase or 0.0
        stimulus = Stimulus(
            name=policy.source_name.lower(),
            type="ac",
            parameters={"dc_value": dc_value, "magnitude": magnitude, "phase": phase},
            node_positive=policy.positive_node,
            node_negative=policy.negative_node,
        )
        stimulus.parameters["decision_authority"] = authority
        stimulus.parameters["decision_evidence"] = evidence
        stimuli.append(stimulus)
    return stimuli


def _retarget_dynamic_stimuli(stimuli: list[Stimulus], signal_policies: list[SourceOverridePolicy]) -> list[Stimulus]:
    if not stimuli or not signal_policies:
        return list(stimuli)
    primary = signal_policies[0]
    rebound: list[Stimulus] = []
    for stimulus in stimuli:
        rebound.append(
            Stimulus(
                name=primary.source_name.lower(),
                type=stimulus.type,
                parameters={key: value for key, value in stimulus.parameters.items() if key not in {"ac_magnitude", "dc_value"}},
                node_positive=primary.positive_node,
                node_negative=primary.negative_node,
            )
        )
    return rebound


def _resolve_signal_dc_authority(specification: Specification, policy: SourceOverridePolicy) -> tuple[float | None, str, str]:
    input_conditions = dict(specification.input_conditions or {})
    source_key = policy.source_name.lower()
    node_key = policy.positive_node.lower()
    candidates = [
        input_conditions.get(f"{source_key}_dc_value"),
        input_conditions.get(f"{source_key}_dc_bias"),
        input_conditions.get(f"{node_key}_dc_value"),
        input_conditions.get(f"{node_key}_dc_bias"),
        input_conditions.get("signal_dc_value"),
        input_conditions.get("ac_signal_dc_value"),
    ]
    for candidate in candidates:
        value = _coerce_optional_float(candidate)
        if value is not None:
            return value, "SPECIFICATION_EXPLICIT_SIGNAL_DC", f"input_conditions provided an explicit DC bias for {policy.source_name}"
    if policy.original_dc_value is not None:
        return policy.original_dc_value, "ORIGINAL_HARNESS_DC_VALUE", policy.original_definition
    return None, "MANUAL_REVIEW_REQUIRED", "No explicit signal DC authority was found in the specification or normalized harness metadata."


def _decision_provenance(
    specification: Specification,
    signal_policies: list[SourceOverridePolicy],
    analysis_key: str,
) -> tuple[str, str, str]:
    if analysis_key != "ac_gain" or not signal_policies:
        return "ANALYSIS_HARNESS_POLICY", "Category-specific canonical deck derived from normalized benchmark metadata.", "AUTO"
    dc_value, authority, evidence = _resolve_signal_dc_authority(specification, signal_policies[0])
    reviewer_status = "MANUAL_REVIEW_REQUIRED" if dc_value is None else "AUTO"
    return authority, evidence, reviewer_status


def _override_measurement_context(
    testbench: TestBench,
    *,
    input_node: str,
    output_node: str,
    input_ac_magnitude: float | None,
    reference_frequency_hz: float | None,
) -> None:
    metadata = dict(testbench.metadata or {})
    metadata["measurement_context"] = {
        "input_node": input_node,
        "output_node": output_node,
        "output_threshold": metadata.get("measurement_context", {}).get("output_threshold", 2.5),
        "input_ac_magnitude": input_ac_magnitude,
        "reference_frequency_hz": reference_frequency_hz,
    }
    requests = []
    for request in metadata.get("measurement_requests", []):
        updated = dict(request)
        updated["input_node"] = input_node
        updated["output_node"] = output_node
        if input_ac_magnitude is not None:
            updated["input_ac_magnitude"] = input_ac_magnitude
        if reference_frequency_hz is not None:
            updated["reference_frequency_hz"] = reference_frequency_hz
        requests.append(updated)
    metadata["measurement_requests"] = requests
    testbench.metadata = metadata


def _reference_frequency_hz(testbench: TestBench) -> float | None:
    for analysis in testbench.analyses:
        if analysis.type != AnalysisType.AC:
            continue
        start = analysis.parameters.get("start_freq")
        return _coerce_optional_float(start)
    return None


def _first_ac_magnitude(testbench: TestBench) -> float | None:
    for stimulus in testbench.stimuli:
        if stimulus.type != "ac":
            continue
        return _coerce_optional_float(stimulus.parameters.get("magnitude"))
    return None


def _difference_class(
    *,
    analysis_key: str,
    source_policies: list[SourceOverridePolicy],
    compiled_stimuli: list[Stimulus],
    dc_override: bool,
    ac_override: bool,
    waveform_override: bool,
) -> str:
    if not source_policies:
        return "NO_DIFFERENCE"
    if any(policy.manual_review_required for policy in source_policies):
        return "SOURCE_ROLE_CONFUSION"
    if analysis_key == "ac_gain":
        if waveform_override:
            return "MULTI_ANALYSIS_CONTAMINATION"
        if dc_override:
            return "UNAUTHORIZED_DC_OVERRIDE"
        if ac_override:
            return "AUTHORIZED_AC_MAGNITUDE_NORMALIZATION"
        return "NO_DIFFERENCE"
    if analysis_key in {"transient_delay", "schmitt", "spectral"}:
        if waveform_override:
            return "AUTHORIZED_TRANSIENT_STIMULUS"
        if dc_override:
            return "UNAUTHORIZED_DC_OVERRIDE"
        return "NO_DIFFERENCE"
    if analysis_key == "oscillation":
        if compiled_stimuli:
            return "MULTI_ANALYSIS_CONTAMINATION"
        return "NO_DIFFERENCE"
    if analysis_key == "op" and dc_override:
        return "UNAUTHORIZED_DC_OVERRIDE"
    return "NO_DIFFERENCE"


def _primary_input_node(specification: Specification, context: NormalizedHarnessContext) -> str:
    signal_nodes = context.harness_metadata.get("signal_input_nodes", [])
    if signal_nodes:
        return str(signal_nodes[0])
    if specification.input_nodes:
        return specification.input_nodes[0]
    return "vin"


def _primary_output_node(specification: Specification, context: NormalizedHarnessContext) -> str:
    output_nodes = context.harness_metadata.get("output_nodes", [])
    if output_nodes:
        return str(output_nodes[0])
    if specification.output_nodes:
        return specification.output_nodes[0]
    return "vout"


def _coerce_optional_float(value: Any) -> float | None:
    if value in {"", None}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _join_scalar(values: list[Any]) -> str:
    rendered = [str(value) for value in values if value not in {None, ""}]
    return " | ".join(rendered)


def _join_text(values: list[Any]) -> str:
    rendered = [str(value) for value in values if str(value or "").strip()]
    return " | ".join(rendered)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()
