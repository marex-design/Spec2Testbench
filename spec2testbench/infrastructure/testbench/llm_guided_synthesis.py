import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import AnalysisConfig, AnalysisType, Measurement, Stimulus, TestBench

logger = logging.getLogger(__name__)


_SPICE_SCALE_SUFFIXES = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def _parse_spice_number(text: str) -> Optional[float]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        pass

    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]+)", raw)
    if not match:
        return None
    magnitude = float(match.group(1))
    suffix = match.group(2).lower()
    scale = _SPICE_SCALE_SUFFIXES.get(suffix)
    if scale is None:
        return None
    return magnitude * scale


@dataclass
class SourceRecord:
    name: str
    raw_name: str
    node_positive: str
    node_negative: str
    body: str
    dc_value: Optional[float] = None
    ac_magnitude: Optional[float] = None


@dataclass
class NetlistInspectionResult:
    path: Optional[str]
    sources: List[SourceRecord] = field(default_factory=list)
    analyses: List[str] = field(default_factory=list)
    supply_nodes: List[str] = field(default_factory=list)
    ground_node: str = "0"


@dataclass
class ReusePolicy:
    reuse_existing_analyses_when_compatible: bool = True
    reuse_existing_sources_when_compatible: bool = True
    allow_source_replacement: bool = True
    allow_source_duplication_on_same_node: bool = False


@dataclass
class NodePlan:
    input_nodes: List[str] = field(default_factory=list)
    output_nodes: List[str] = field(default_factory=list)
    supply_nodes: List[str] = field(default_factory=list)
    ground_node: str = "0"


@dataclass
class SourceAction:
    target_name: str
    action: str
    reason: str
    new_source: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_name": self.target_name,
            "action": self.action,
            "reason": self.reason,
            "new_source": self.new_source,
        }


@dataclass
class AnalysisAction:
    analysis: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis": self.analysis,
            "action": self.action,
            "parameters": self.parameters,
        }


@dataclass
class MeasurementPlan:
    name: str
    analysis: str
    expression: str
    node: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "analysis": self.analysis,
            "expression": self.expression,
        }
        if self.node:
            data["node"] = self.node
        return data


@dataclass
class TestbenchPlan:
    circuit_name: str
    intent: str
    reuse_policy: ReusePolicy
    nodes: NodePlan
    source_actions: List[SourceAction] = field(default_factory=list)
    analysis_actions: List[AnalysisAction] = field(default_factory=list)
    measurements: List[MeasurementPlan] = field(default_factory=list)
    expected_outputs: Dict[str, Any] = field(default_factory=dict)
    reasoning_summary: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "circuit_name": self.circuit_name,
            "intent": self.intent,
            "reuse_policy": self.reuse_policy.__dict__,
            "nodes": self.nodes.__dict__,
            "source_actions": [item.to_dict() for item in self.source_actions],
            "analysis_actions": [item.to_dict() for item in self.analysis_actions],
            "measurements": [item.to_dict() for item in self.measurements],
            "expected_outputs": self.expected_outputs,
            "reasoning_summary": self.reasoning_summary,
        }


class NetlistInspector:
    SOURCE_PATTERN = re.compile(
        r"(?im)^\s*(?P<name>V\S+)\s+(?P<pos>\S+)\s+(?P<neg>\S+)\s+(?P<body>.+?)\s*$"
    )

    @classmethod
    def inspect(cls, netlist_path: Optional[Path]) -> NetlistInspectionResult:
        if not netlist_path or not netlist_path.exists():
            return NetlistInspectionResult(path=str(netlist_path) if netlist_path else None)

        text = netlist_path.read_text(encoding="utf-8", errors="ignore")
        return cls.inspect_text(text, str(netlist_path))

    @classmethod
    def inspect_text(cls, text: str, path: Optional[str] = None) -> NetlistInspectionResult:
        # Inspect active SPICE statements only. Canonical ACP DUTs intentionally
        # preserve upstream analyses as comments for provenance; those comments
        # must never be mistaken for executable .OP/.AC/.TRAN/.DC directives.
        active_text = "\n".join(
            line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("*")
        )
        sources: List[SourceRecord] = []
        supply_nodes: List[str] = []
        for match in cls.SOURCE_PATTERN.finditer(active_text):
            raw_name = match.group("name").strip()
            name = raw_name[1:] if raw_name.lower().startswith("v") else raw_name
            pos = match.group("pos").strip()
            neg = match.group("neg").strip()
            body = match.group("body").strip()
            dc_value = cls._extract_dc_value(body)
            ac_magnitude = cls._extract_ac_magnitude(body)
            sources.append(SourceRecord(
                name=name,
                raw_name=raw_name,
                node_positive=pos,
                node_negative=neg,
                body=body,
                dc_value=dc_value,
                ac_magnitude=ac_magnitude,
            ))
            if pos.lower().startswith("vdd") and pos not in supply_nodes:
                supply_nodes.append(pos)
        analyses = []
        active_lower = active_text.lower()
        for token, label in ((".op", "op"), (".ac", "ac"), (".tran", "tran"), (".dc", "dc"), (".four", "fourier")):
            if token in active_lower:
                analyses.append(label)
        return NetlistInspectionResult(
            path=path,
            sources=sources,
            analyses=analyses,
            supply_nodes=supply_nodes,
            ground_node="0",
        )

    @staticmethod
    def _extract_dc_value(body: str) -> Optional[float]:
        dc_match = re.search(r"(?i)\bDC\s+([^\s]+)", body)
        value = dc_match.group(1) if dc_match else body.split()[0]
        return _parse_spice_number(value)

    @staticmethod
    def _extract_ac_magnitude(body: str) -> Optional[float]:
        ac_match = re.search(r"(?i)\bAC\s+([^\s]+)", body)
        if not ac_match:
            return None
        return _parse_spice_number(ac_match.group(1))


class TestbenchPlanValidator:
    def validate(
        self,
        plan: TestbenchPlan,
        specification: Specification,
        inspection: NetlistInspectionResult,
    ) -> List[str]:
        errors: List[str] = []
        seen_nodes: Dict[str, str] = {}
        for action in plan.source_actions:
            source = action.new_source
            pos = str(source.get("node_positive", "")).strip()
            if not pos:
                errors.append(f"source_action {action.target_name} missing node_positive")
                continue
            if pos in seen_nodes and not plan.reuse_policy.allow_source_duplication_on_same_node:
                errors.append(f"duplicate source target on node {pos}")
            seen_nodes[pos] = action.target_name

            if action.action not in {"replace", "reuse", "add"}:
                errors.append(f"unsupported source action {action.action}")

        existing_nodes = {src.node_positive for src in inspection.sources} | {src.node_negative for src in inspection.sources}
        allowed_nodes = existing_nodes | set(specification.input_nodes) | set(specification.output_nodes) | {"0"}
        for measurement in plan.measurements:
            if measurement.node and measurement.node not in allowed_nodes:
                errors.append(f"measurement {measurement.name} references unknown node {measurement.node}")
            if measurement.analysis not in {"op", "dc", "ac", "tran", "fourier", "pvt"}:
                errors.append(f"measurement {measurement.name} uses unsupported analysis {measurement.analysis}")

        analyses = {item.analysis for item in plan.analysis_actions}
        for measurement in plan.measurements:
            if measurement.analysis not in analyses and measurement.analysis not in inspection.analyses:
                errors.append(f"measurement {measurement.name} has no matching analysis action")

        for metric_name in specification.verification_metric_names():
            if metric_name not in {item.name for item in plan.measurements}:
                logger.debug("Metric %s not covered by plan for %s", metric_name, plan.circuit_name)

        return errors


class LLMGuidedPlanner:
    SYSTEM_PROMPT = """You are an analog verification engineer specialized in SPICE testbench planning.

Your job is NOT to write a free-form SPICE deck.
Your job is to produce a structured JSON testbench plan that will later be validated and rendered by deterministic code.

Hard rules:
- Never place two independent voltage sources on the same input node unless explicitly requested.
- Prefer replacing an existing source rather than adding a duplicate source.
- Reuse existing .OP, .AC, and .TRAN analyses when they are already compatible with the specification.
- Do not invent node names.
- Every measurement must reference a compatible analysis.
- For analog amplifiers, preserve a reasonable DC bias point.
- Use small-signal excitation for AC analysis.
- Use a transient stimulus that is physically meaningful for the circuit category.
- Return raw JSON only.
"""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def plan(
        self,
        specification: Specification,
        testbench: TestBench,
        inspection: NetlistInspectionResult,
        use_llm: bool = False,
    ) -> TestbenchPlan:
        if use_llm and self.llm_client:
            return self._plan_with_llm(specification, testbench, inspection)
        return self._plan_deterministically(specification, testbench, inspection)

    def _plan_deterministically(
        self,
        specification: Specification,
        testbench: TestBench,
        inspection: NetlistInspectionResult,
    ) -> TestbenchPlan:
        primary_input = specification.input_nodes[0] if specification.input_nodes else "Vin"
        primary_output = specification.output_nodes[0] if specification.output_nodes else "Vout"
        source_actions: List[SourceAction] = []
        seen_inputs = set()
        grouped: Dict[str, List[Stimulus]] = {}
        for stimulus in testbench.stimuli:
            grouped.setdefault(stimulus.name.lower(), []).append(stimulus)

        for key, stimuli in grouped.items():
            candidate = self._choose_multimode_stimulus(stimuli, specification)
            target = self._find_existing_source(candidate, inspection)
            if candidate.node_positive in seen_inputs:
                continue
            seen_inputs.add(candidate.node_positive)
            source_actions.append(SourceAction(
                target_name=target.name if target else candidate.name,
                action="replace" if target else "add",
                reason="Consolidate generator stimuli into one non-conflicting source per input node",
                new_source=self._stimulus_to_source_dict(candidate),
            ))

        analysis_actions = []
        existing = set(inspection.analyses)
        for analysis in testbench.analyses:
            label = analysis.type.value
            normalized = "op" if label == "dc" and analysis.to_spice().strip().upper() == ".OP" else label
            action = "reuse_if_present_else_add" if normalized in existing else "add_if_missing"
            analysis_actions.append(AnalysisAction(
                analysis=normalized,
                action=action,
                parameters=dict(analysis.parameters),
            ))

        measurement_plans = []
        for measurement in testbench.measurements:
            analysis_name = self._analysis_for_measurement(measurement.name, testbench.analyses)
            measurement_plans.append(MeasurementPlan(
                name=measurement.name,
                analysis=analysis_name,
                expression=measurement.expression,
                node=measurement.node or primary_output,
            ))

        return TestbenchPlan(
            circuit_name=specification.name,
            intent=f"verify_{specification.circuit_type.value}",
            reuse_policy=ReusePolicy(
                reuse_existing_analyses_when_compatible=True,
                reuse_existing_sources_when_compatible=False,
                allow_source_replacement=True,
                allow_source_duplication_on_same_node=False,
            ),
            nodes=NodePlan(
                input_nodes=specification.input_nodes,
                output_nodes=specification.output_nodes,
                supply_nodes=inspection.supply_nodes or ["Vdd"],
                ground_node=inspection.ground_node,
            ),
            source_actions=source_actions,
            analysis_actions=analysis_actions,
            measurements=measurement_plans,
            expected_outputs={
                "should_generate_spice_deck": True,
                "should_generate_measure_backend_plan": True,
            },
            reasoning_summary=[
                f"Circuit treated as {specification.circuit_type.value}",
                "A single consolidated source is used per driven input node",
                "Existing analyses are reused when they already exist in the netlist",
            ],
        )

    def _plan_with_llm(
        self,
        specification: Specification,
        testbench: TestBench,
        inspection: NetlistInspectionResult,
    ) -> TestbenchPlan:
        prompt = json.dumps({
            "specification": specification.to_dict(),
            "inspection": {
                "path": inspection.path,
                "sources": [source.__dict__ for source in inspection.sources],
                "analyses": inspection.analyses,
                "supply_nodes": inspection.supply_nodes,
            },
            "generated_testbench": testbench.to_dict(),
        }, indent=2)
        response = self.llm_client.complete(
            prompt,
            response_format="json",
            system_prompt=self.SYSTEM_PROMPT,
        )
        data = json.loads(response)
        return TestbenchPlan(
            circuit_name=data["circuit_name"],
            intent=data["intent"],
            reuse_policy=ReusePolicy(**data.get("reuse_policy", {})),
            nodes=NodePlan(**data.get("nodes", {})),
            source_actions=[SourceAction(**item) for item in data.get("source_actions", [])],
            analysis_actions=[AnalysisAction(**item) for item in data.get("analysis_actions", [])],
            measurements=[MeasurementPlan(**item) for item in data.get("measurements", [])],
            expected_outputs=data.get("expected_outputs", {}),
            reasoning_summary=data.get("reasoning_summary", []),
        )

    def _choose_multimode_stimulus(self, stimuli: List[Stimulus], specification: Specification) -> Stimulus:
        primary = stimuli[-1]
        dc_value = None
        ac_magnitude = None
        transient = None
        for stimulus in stimuli:
            if stimulus.type == "dc":
                dc_value = stimulus.parameters.get("value")
            elif stimulus.type == "ac":
                ac_magnitude = stimulus.parameters.get("magnitude", 1.0)
                dc_value = stimulus.parameters.get("dc_value", dc_value)
            elif stimulus.type in {"pulse", "sin", "pwl"}:
                transient = stimulus
        params: Dict[str, Any] = {}
        if transient is not None:
            params.update(dict(transient.parameters))
            chosen_type = transient.type
            if ac_magnitude is not None:
                params["ac_magnitude"] = ac_magnitude
        elif ac_magnitude is not None:
            chosen_type = "ac"
            params["magnitude"] = ac_magnitude
        else:
            chosen_type = primary.type
            params.update(dict(primary.parameters))

        if chosen_type == "ac":
            params["magnitude"] = ac_magnitude if ac_magnitude is not None else params.get("magnitude", 1.0)
            if dc_value is not None:
                params["dc_value"] = dc_value
        elif dc_value is not None and chosen_type == "dc":
            params["value"] = dc_value
        elif dc_value is not None and chosen_type in {"pulse", "sin", "pwl"}:
            params["dc_value"] = dc_value

        if dc_value is None and chosen_type in {"pulse", "sin"}:
            params["dc_value"] = specification.common_mode_voltage

        return Stimulus(
            name=primary.name,
            type=chosen_type,
            parameters=params,
            node_positive=primary.node_positive,
            node_negative=primary.node_negative,
        )

    @staticmethod
    def _find_existing_source(stimulus: Stimulus, inspection: NetlistInspectionResult) -> Optional[SourceRecord]:
        for source in inspection.sources:
            if source.name.lower() == stimulus.name.lower():
                return source
            if source.node_positive == stimulus.node_positive and source.node_negative == stimulus.node_negative:
                return source
        return None

    @staticmethod
    def _stimulus_to_source_dict(stimulus: Stimulus) -> Dict[str, Any]:
        data = {
            "kind": "voltage",
            "type": stimulus.type,
            "node_positive": stimulus.node_positive,
            "node_negative": stimulus.node_negative,
        }
        if stimulus.type == "dc":
            data["dc_value"] = stimulus.parameters.get("value")
        elif stimulus.type == "ac":
            data["dc_value"] = stimulus.parameters.get("dc_value", 0.0)
            data["ac_magnitude"] = stimulus.parameters.get("magnitude", 1.0)
        else:
            if "dc_value" in stimulus.parameters:
                data["dc_value"] = stimulus.parameters.get("dc_value")
            if "ac_magnitude" in stimulus.parameters:
                data["ac_magnitude"] = stimulus.parameters.get("ac_magnitude")
            data["transient"] = dict(stimulus.parameters)
        return data

    @staticmethod
    def _analysis_for_measurement(name: str, analyses: List[AnalysisConfig]) -> str:
        lower = name.lower()
        available = {analysis.type.value for analysis in analyses}
        if any(token in lower for token in ("gain", "bandwidth", "ugbw", "phase", "cmrr", "psrr")) and "ac" in available:
            return "ac"
        if any(token in lower for token in ("slew", "settling", "delay", "frequency", "startup", "hysteresis")) and "tran" in available:
            return "tran"
        if ("thd" in lower or "sfdr" in lower) and "fourier" in available:
            return "fourier"
        # AnalysisType.DC represents both .OP and real .DC sweeps in the legacy
        # TestBench entity. Distinguish them using the rendered directive.
        for analysis in analyses:
            if analysis.type.value == "dc":
                return "op" if analysis.to_spice().strip().upper() == ".OP" else "dc"
        return next(iter(available), "op")


def resolve_netlist_hint(specification: Specification) -> Optional[str]:
    try:
        data = yaml.safe_load(specification.raw_specs or "") or {}
    except yaml.YAMLError:
        return None
    source = data.get("source", {})
    if isinstance(source, dict):
        return source.get("netlist")
    return None
