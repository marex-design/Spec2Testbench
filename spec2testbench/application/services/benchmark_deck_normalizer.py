from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ANALYSIS_DIRECTIVES = {
    ".OP",
    ".DC",
    ".AC",
    ".TRAN",
    ".TF",
    ".NOISE",
    ".FOUR",
}
OUTPUT_DIRECTIVES = {".MEASURE", ".MEAS", ".PRINT", ".PLOT", ".PROBE", ".SAVE"}
CONTROL_DIRECTIVES = {".CONTROL", ".ENDC"}
OPTION_DIRECTIVES = {".OPTION", ".OPTIONS"}
INITIAL_CONDITION_DIRECTIVES = {".IC", ".NODESET"}
MODEL_DIRECTIVES = {".MODEL"}
SUBCKT_DIRECTIVES = {".SUBCKT"}
SUBCKT_END_DIRECTIVES = {".ENDS"}
END_DIRECTIVES = {".END"}
SOURCE_WAVEFORM_KEYWORDS = {"PULSE", "SIN", "PWL", "EXP", "SFFM", "AM"}
SUPPLY_NAMES = {
    "vdd",
    "vss",
    "vcc",
    "vee",
    "avdd",
    "avss",
    "dvdd",
    "dvss",
    "vdda",
    "vssa",
    "vddd",
    "vssd",
}
SIGNAL_NAME_HINTS = {
    "vin",
    "vinp",
    "vinn",
    "vin1",
    "vin2",
    "vrf",
    "vrfp",
    "vrfn",
    "vlo",
    "vlop",
    "vlon",
    "vi",
    "in",
    "inp",
    "inn",
}
BIAS_NAME_HINTS = {"vbias", "bias", "vref", "ref", "tail", "cm", "common_mode", "iref"}
OUTPUT_NAME_HINTS = {
    "vout",
    "voutp",
    "voutn",
    "out",
    "outp",
    "outn",
    "vo",
}
NODE_COUNT = {
    "R": 2,
    "C": 2,
    "L": 2,
    "V": 2,
    "I": 2,
    "D": 2,
    "Q": 3,
    "J": 3,
    "M": 4,
    "E": 4,
    "G": 4,
    "F": 2,
    "H": 2,
    "S": 4,
    "W": 4,
}
HAS_MODEL = {"M", "Q", "J", "D"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_json_sha(payload: Any) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"))


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _looks_numeric(token: str) -> bool:
    token = token.strip()
    if not token:
        return False
    try:
        float(token)
        return True
    except ValueError:
        return bool(re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:[a-zA-Z]+)?$", token))


def _safe_float(token: str | None) -> float | None:
    if token is None:
        return None
    text = token.strip()
    if not text:
        return None
    match = re.match(r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?P<suffix>[a-zA-Z]+)?$", text)
    if not match:
        return None
    try:
        value = float(match.group("number"))
    except ValueError:
        return None
    suffix = (match.group("suffix") or "").lower()
    scale = {
        "t": 1e12,
        "g": 1e9,
        "meg": 1e6,
        "k": 1e3,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
    }.get(suffix, 1.0)
    return value * scale


@dataclass(frozen=True)
class ParsedComponent:
    line_number: int
    raw_line: str
    name: str
    component_type: str
    nodes: tuple[str, ...]
    model: str | None = None
    remainder: tuple[str, ...] = ()

    def normalized_tokens(self) -> list[str]:
        tokens = [self.component_type, self.name.lower(), *[node.lower() for node in self.nodes]]
        if self.model:
            tokens.append(self.model.lower())
        tokens.extend(token.lower() for token in self.remainder)
        return tokens


@dataclass(frozen=True)
class LineClassification:
    case_id: str
    line_number: int
    raw_line: str
    selected_category: str
    candidate_categories: tuple[str, ...]
    confidence: float
    selection_reason: str
    manual_review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "line_number": self.line_number,
            "raw_line": self.raw_line,
            "candidate_categories": "|".join(self.candidate_categories),
            "selected_category": self.selected_category,
            "confidence": self.confidence,
            "selection_reason": self.selection_reason,
            "manual_review_required": self.manual_review_required,
        }


@dataclass(frozen=True)
class SourceRecord:
    name: str
    positive_node: str
    negative_node: str
    role: str
    replaceable_by_testbench: bool
    original_definition: str
    original_dc_value: float | None
    original_ac_magnitude: float | None
    original_ac_phase: float | None
    original_waveform: str | None
    confidence: float
    manual_review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeRecord:
    node_name: str
    connected_elements: tuple[str, ...]
    degree: int
    declared_role: str
    inferred_role: str
    role_confidence: float
    manual_review_required: bool
    bulk_terminal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "connected_elements": "|".join(self.connected_elements),
            "degree": self.degree,
            "declared_role": self.declared_role,
            "inferred_role": self.inferred_role,
            "role_confidence": self.role_confidence,
            "manual_review_required": self.manual_review_required,
            "bulk_terminal": self.bulk_terminal,
        }


@dataclass(frozen=True)
class NormalizationResult:
    case_id: str
    source_path: str
    source_sha256: str
    original_dut_logical_sha256: str
    canonical_dut_logical_sha256: str
    canonical_dut_sha256: str
    metadata_sha256: str
    classification_sha256: str
    declared_type: str
    declared_topology: str
    inferred_topology: str
    topology_match_status: str
    description: str
    line_classifications: tuple[LineClassification, ...]
    classification_ambiguities: tuple[LineClassification, ...]
    sources: tuple[SourceRecord, ...]
    nodes: tuple[NodeRecord, ...]
    anomalies: tuple[dict[str, Any], ...]
    embedded_analyses: tuple[str, ...]
    embedded_measurements: tuple[str, ...]
    compatible_metrics: tuple[dict[str, Any], ...]
    canonical_dut_text: str
    harness_metadata: dict[str, Any]
    circuit_metadata: dict[str, Any]
    original_analysis_metadata: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]


class BenchmarkDeckNormalizer:
    def normalize(
        self,
        netlist_path: Path,
        *,
        case_id: str | None = None,
        declared_type: str | None = None,
        declared_topology: str | None = None,
        description: str | None = None,
    ) -> NormalizationResult:
        raw_bytes = netlist_path.read_bytes()
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        lines = raw_text.splitlines()
        case_name = case_id or netlist_path.stem
        comment_metadata = self._comment_metadata(lines)
        declared_type = (declared_type or comment_metadata.get("type") or "").strip()
        declared_topology = (declared_topology or comment_metadata.get("description") or "").strip()
        description = (description or comment_metadata.get("description") or declared_topology).strip()
        declared_inputs = tuple(comment_metadata.get("inputs", ()))
        declared_outputs = tuple(comment_metadata.get("outputs", ()))

        components: list[ParsedComponent] = []
        classifications: list[LineClassification] = []
        analyses: list[dict[str, Any]] = []
        embedded_measurements: list[str] = []
        unknown_directives: list[str] = []
        in_subckt = False

        for line_number, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            classification, parsed_component = self._classify_line(
                case_name,
                line_number,
                raw_line,
                stripped,
                declared_inputs=declared_inputs,
                declared_outputs=declared_outputs,
            )
            classifications.append(classification)
            if parsed_component is not None:
                components.append(parsed_component)
            upper = stripped.split()[0].upper()
            if upper in SUBCKT_DIRECTIVES:
                in_subckt = True
            elif upper in SUBCKT_END_DIRECTIVES:
                in_subckt = False
            if classification.selected_category == "EMBEDDED_ANALYSIS_DIRECTIVE":
                analyses.append(
                    {
                        "line_number": line_number,
                        "directive": upper,
                        "raw_line": raw_line,
                        "inside_subcircuit": in_subckt,
                    }
                )
            elif classification.selected_category == "OUTPUT_DIRECTIVE":
                embedded_measurements.append(raw_line)
            elif classification.selected_category == "UNKNOWN_DIRECTIVE":
                unknown_directives.append(raw_line)

        source_records = self._build_source_records(components, declared_inputs)
        node_records = self._build_node_records(components, source_records, declared_outputs)
        output_nodes = [record.node_name for record in node_records if record.inferred_role == "output"]
        inferred_topology = self._infer_topology(case_name, description, components, source_records, node_records)
        topology_match_status = self._topology_match_status(declared_topology, inferred_topology)
        anomalies = self._build_anomalies(
            case_name=case_name,
            components=components,
            classifications=classifications,
            source_records=source_records,
            node_records=node_records,
            analyses=analyses,
            unknown_directives=unknown_directives,
            inferred_topology=inferred_topology,
            output_nodes=output_nodes,
        )
        compatible_metrics = self._compatible_metrics(declared_type, inferred_topology)
        canonical_dut_text = self._build_canonical_dut(
            source_path=netlist_path,
            line_classifications=classifications,
            components=components,
            source_records=source_records,
        )
        original_dut_logical_sha256 = self._logical_dut_hash(classifications, components, source_records)
        canonical_components = self._parse_canonical_components(canonical_dut_text)
        canonical_dut_logical_sha256 = self._logical_dut_hash(
            tuple(
                classification
                for classification in classifications
                if classification.selected_category
                in {
                    "MODEL_DEFINITION",
                    "SUPPLY_SOURCE",
                    "BIAS_SOURCE",
                    "SIGNAL_SOURCE",
                    "INTERNAL_BIAS_SOURCE",
                    "DUT_DEVICE",
                    "DUT_LOAD",
                    "SUBCIRCUIT_DEFINITION",
                    "SUBCIRCUIT_END",
                    "SUBCIRCUIT_INSTANCE",
                    "COMMENT",
                }
            ),
            canonical_components,
            source_records,
        )
        harness_metadata = self._harness_metadata(source_records, node_records)
        circuit_metadata = self._circuit_metadata(
            case_name,
            declared_type,
            declared_topology,
            description,
            node_records,
            source_records,
            inferred_topology,
            topology_match_status,
            anomalies,
            compatible_metrics,
            analyses,
        )
        provenance = {
            "case_id": case_name,
            "source_path": str(netlist_path).replace("\\", "/"),
            "source_sha256": _sha256_bytes(raw_bytes),
            "original_dut_logical_sha256": original_dut_logical_sha256,
            "canonical_dut_logical_sha256": canonical_dut_logical_sha256,
            "classification_sha256": _stable_json_sha([item.to_dict() for item in classifications]),
            "metadata_sha256": _stable_json_sha(
                {
                    "harness_metadata": harness_metadata,
                    "circuit_metadata": circuit_metadata,
                    "original_analysis_metadata": analyses,
                }
            ),
            "canonical_dut_sha256": _sha256_bytes(canonical_dut_text.encode("utf-8")),
        }
        return NormalizationResult(
            case_id=case_name,
            source_path=provenance["source_path"],
            source_sha256=provenance["source_sha256"],
            original_dut_logical_sha256=original_dut_logical_sha256,
            canonical_dut_logical_sha256=canonical_dut_logical_sha256,
            canonical_dut_sha256=provenance["canonical_dut_sha256"],
            metadata_sha256=provenance["metadata_sha256"],
            classification_sha256=provenance["classification_sha256"],
            declared_type=declared_type,
            declared_topology=declared_topology,
            inferred_topology=inferred_topology,
            topology_match_status=topology_match_status,
            description=description,
            line_classifications=tuple(classifications),
            classification_ambiguities=tuple(item for item in classifications if item.manual_review_required),
            sources=tuple(source_records),
            nodes=tuple(node_records),
            anomalies=tuple(anomalies),
            embedded_analyses=tuple(item["raw_line"] for item in analyses),
            embedded_measurements=tuple(embedded_measurements),
            compatible_metrics=tuple(compatible_metrics),
            canonical_dut_text=canonical_dut_text,
            harness_metadata=harness_metadata,
            circuit_metadata=circuit_metadata,
            original_analysis_metadata=tuple(analyses),
            provenance=provenance,
        )

    def _comment_metadata(self, lines: list[str]) -> dict[str, Any]:
        metadata: dict[str, Any] = {"inputs": [], "outputs": []}
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped.startswith("*"):
                continue
            content = stripped.lstrip("*").strip()
            if ":" not in content:
                continue
            key, value = [part.strip() for part in content.split(":", 1)]
            lowered = key.lower()
            if lowered == "inputs":
                metadata["inputs"] = [part.strip() for part in value.split(",") if part.strip()]
            elif lowered == "outputs":
                metadata["outputs"] = [part.strip() for part in value.split(",") if part.strip()]
            elif re.match(r"analogcoder-pro p\d+$", lowered):
                metadata["description"] = value
            elif lowered.endswith("type"):
                metadata["type"] = value
            elif lowered.startswith("analogcoder-pro p") or lowered == "source":
                continue
            elif lowered in {"analogcoder-pro type", "analogcoder pro type"}:
                metadata["type"] = value
            else:
                metadata.setdefault(lowered, value)
                if lowered == "description":
                    metadata["description"] = value
        return metadata

    def _classify_line(
        self,
        case_id: str,
        line_number: int,
        raw_line: str,
        stripped: str,
        *,
        declared_inputs: tuple[str, ...],
        declared_outputs: tuple[str, ...],
    ) -> tuple[LineClassification, ParsedComponent | None]:
        upper = stripped.split()[0].upper()
        if stripped.startswith("*") or stripped.startswith(";"):
            return (
                LineClassification(case_id, line_number, raw_line, "COMMENT", ("COMMENT",), 1.0, "Comment line", False),
                None,
            )
        if upper in MODEL_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "MODEL_DEFINITION", ("MODEL_DEFINITION",), 1.0, "Model definition", False),
                None,
            )
        if upper in SUBCKT_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "SUBCIRCUIT_DEFINITION", ("SUBCIRCUIT_DEFINITION",), 1.0, "Subcircuit definition", False),
                None,
            )
        if upper in SUBCKT_END_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "SUBCIRCUIT_END", ("SUBCIRCUIT_END",), 1.0, "Subcircuit end", False),
                None,
            )
        if upper in ANALYSIS_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "EMBEDDED_ANALYSIS_DIRECTIVE", ("EMBEDDED_ANALYSIS_DIRECTIVE",), 1.0, "Embedded analysis directive", False),
                None,
            )
        if upper in OUTPUT_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "OUTPUT_DIRECTIVE", ("OUTPUT_DIRECTIVE",), 1.0, "Measurement or output directive", False),
                None,
            )
        if upper in CONTROL_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "CONTROL_DIRECTIVE", ("CONTROL_DIRECTIVE",), 1.0, "Control directive", False),
                None,
            )
        if upper in OPTION_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "OPTION_DIRECTIVE", ("OPTION_DIRECTIVE",), 1.0, "Option directive", False),
                None,
            )
        if upper in INITIAL_CONDITION_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "INITIAL_CONDITION_DIRECTIVE", ("INITIAL_CONDITION_DIRECTIVE",), 1.0, "Initial condition directive", False),
                None,
            )
        if upper in END_DIRECTIVES:
            return (
                LineClassification(case_id, line_number, raw_line, "END_DIRECTIVE", ("END_DIRECTIVE",), 1.0, "Deck end directive", False),
                None,
            )
        if stripped.startswith("."):
            return (
                LineClassification(
                    case_id,
                    line_number,
                    raw_line,
                    "UNKNOWN_DIRECTIVE",
                    ("UNKNOWN_DIRECTIVE",),
                    0.3,
                    "Unhandled dot directive",
                    True,
                ),
                None,
            )
        component = self._parse_component_line(line_number, raw_line)
        if component is None:
            return (
                LineClassification(
                    case_id,
                    line_number,
                    raw_line,
                    "CLASSIFICATION_AMBIGUITY",
                    ("CLASSIFICATION_AMBIGUITY",),
                    0.0,
                    "Line could not be parsed as a directive or component",
                    True,
                ),
                None,
            )
        if component.component_type in {"V", "I"}:
            category, candidates, confidence, reason, manual_review = self._source_category(component, declared_inputs, declared_outputs)
            return (
                LineClassification(case_id, line_number, raw_line, category, tuple(candidates), confidence, reason, manual_review),
                component,
            )
        if component.component_type == "X":
            return (
                LineClassification(case_id, line_number, raw_line, "SUBCIRCUIT_INSTANCE", ("SUBCIRCUIT_INSTANCE",), 1.0, "Subcircuit instance", False),
                component,
            )
        if component.component_type in {"R", "C", "L"}:
            return (
                LineClassification(case_id, line_number, raw_line, "DUT_LOAD", ("DUT_LOAD",), 1.0, "Passive DUT element", False),
                component,
            )
        return (
            LineClassification(case_id, line_number, raw_line, "DUT_DEVICE", ("DUT_DEVICE",), 0.95, "Active DUT device", False),
            component,
        )

    def _parse_component_line(self, line_number: int, raw_line: str) -> ParsedComponent | None:
        line = raw_line.split(";", 1)[0].strip()
        parts = line.split()
        if len(parts) < 3:
            return None
        name = parts[0]
        component_type = name[0].upper()
        if component_type == "X":
            if len(parts) < 4:
                return None
            return ParsedComponent(
                line_number=line_number,
                raw_line=raw_line,
                name=name,
                component_type=component_type,
                nodes=tuple(parts[1:-1]),
                model=parts[-1],
                remainder=(),
            )
        node_count = NODE_COUNT.get(component_type)
        if node_count is None:
            node_count = 2
        if len(parts) < 1 + node_count:
            return None
        nodes = list(parts[1 : 1 + node_count])
        remainder = parts[1 + node_count :]
        model = None
        if component_type in HAS_MODEL and remainder:
            model = remainder[0]
            remainder = remainder[1:]
        return ParsedComponent(
            line_number=line_number,
            raw_line=raw_line,
            name=name,
            component_type=component_type,
            nodes=tuple(nodes),
            model=model,
            remainder=tuple(remainder),
        )

    def _source_category(
        self,
        component: ParsedComponent,
        declared_inputs: tuple[str, ...],
        declared_outputs: tuple[str, ...],
    ) -> tuple[str, list[str], float, str, bool]:
        name = _normalize_name(component.name)
        positive = _normalize_name(component.nodes[0])
        negative = _normalize_name(component.nodes[1])
        remainder = [token.upper() for token in component.remainder]
        has_waveform = any(token in SOURCE_WAVEFORM_KEYWORDS for token in remainder)
        has_ac = "AC" in remainder
        declared_input_names = {_normalize_name(item) for item in declared_inputs}
        signal_hint = (
            name in SIGNAL_NAME_HINTS
            or positive in SIGNAL_NAME_HINTS
            or name.startswith("vin")
            or positive.startswith("vin")
            or name.startswith("vrf")
            or name.startswith("vlo")
        )
        bias_hint = any(hint in name for hint in BIAS_NAME_HINTS) or any(hint in positive for hint in BIAS_NAME_HINTS)
        candidates: list[str] = []
        if name in SUPPLY_NAMES or positive in SUPPLY_NAMES:
            candidates.append("SUPPLY_SOURCE")
        if bias_hint:
            candidates.append("BIAS_SOURCE" if "0" in component.nodes else "INTERNAL_BIAS_SOURCE")
        if signal_hint or has_ac or has_waveform:
            candidates.append("SIGNAL_SOURCE")
        elif positive in declared_input_names and not bias_hint and not (name in SUPPLY_NAMES or positive in SUPPLY_NAMES):
            candidates.append("SIGNAL_SOURCE")
        if not candidates and component.nodes[1] != "0":
            candidates.append("INTERNAL_BIAS_SOURCE")
        if not candidates:
            candidates.append("BIAS_SOURCE")
        unique_candidates = list(dict.fromkeys(candidates))
        if "SIGNAL_SOURCE" in unique_candidates and (signal_hint or has_ac or has_waveform):
            return "SIGNAL_SOURCE", unique_candidates, 0.95, "Source matches declared signal input or carries AC/transient stimulus", False
        if "BIAS_SOURCE" in unique_candidates and bias_hint:
            return "BIAS_SOURCE", unique_candidates, 0.95, "Ground-referenced bias or reference source", False
        if unique_candidates[0] == "SUPPLY_SOURCE":
            return "SUPPLY_SOURCE", unique_candidates, 0.95, "Source name or rail node matches supply naming", False
        if unique_candidates[0] == "INTERNAL_BIAS_SOURCE":
            return "INTERNAL_BIAS_SOURCE", unique_candidates, 0.9, "Floating or internal bias source inferred from connectivity and naming", False
        manual_review = len(unique_candidates) > 1 and "SIGNAL_SOURCE" in unique_candidates and "BIAS_SOURCE" in unique_candidates
        return unique_candidates[0], unique_candidates, 0.7 if manual_review else 0.9, "Ground-referenced static source treated as bias/reference", manual_review

    def _build_source_records(self, components: list[ParsedComponent], declared_inputs: tuple[str, ...]) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        declared_input_names = {_normalize_name(item) for item in declared_inputs}
        for component in components:
            if component.component_type not in {"V", "I"}:
                continue
            category, candidates, confidence, reason, manual_review = self._source_category(component, declared_inputs, ())
            dc_value, ac_magnitude, ac_phase, waveform = self._parse_source_values(component.remainder)
            role = category
            if (
                _normalize_name(component.nodes[0]) in declared_input_names
                and role not in {"SIGNAL_SOURCE", "BIAS_SOURCE", "INTERNAL_BIAS_SOURCE"}
                and (_normalize_name(component.name).startswith("vin") or waveform or ac_magnitude is not None)
            ):
                role = "SIGNAL_SOURCE"
                confidence = max(confidence, 0.8)
                manual_review = False
            records.append(
                SourceRecord(
                    name=component.name,
                    positive_node=component.nodes[0],
                    negative_node=component.nodes[1],
                    role=role,
                    replaceable_by_testbench=role == "SIGNAL_SOURCE",
                    original_definition=component.raw_line,
                    original_dc_value=dc_value,
                    original_ac_magnitude=ac_magnitude,
                    original_ac_phase=ac_phase,
                    original_waveform=waveform,
                    confidence=confidence,
                    manual_review_required=manual_review,
                )
            )
        return records

    def _parse_source_values(self, remainder: tuple[str, ...]) -> tuple[float | None, float | None, float | None, str | None]:
        dc_value = None
        ac_magnitude = None
        ac_phase = None
        waveform = None
        tokens = list(remainder)
        index = 0
        while index < len(tokens):
            token = tokens[index].upper()
            if token == "DC" and index + 1 < len(tokens):
                dc_value = _safe_float(tokens[index + 1])
                index += 2
                continue
            if token == "AC" and index + 1 < len(tokens):
                ac_magnitude = _safe_float(tokens[index + 1])
                if index + 2 < len(tokens):
                    ac_phase = _safe_float(tokens[index + 2])
                index += 3
                continue
            if token in SOURCE_WAVEFORM_KEYWORDS:
                waveform = " ".join(tokens[index:])
                break
            if dc_value is None and _looks_numeric(tokens[index]):
                dc_value = _safe_float(tokens[index])
            index += 1
        return dc_value, ac_magnitude, ac_phase, waveform

    def _build_node_records(
        self,
        components: list[ParsedComponent],
        source_records: list[SourceRecord],
        declared_outputs: tuple[str, ...],
    ) -> list[NodeRecord]:
        connections: dict[str, list[str]] = {}
        bulk_terminal_nodes: set[str] = set()
        non_bulk_terminal_nodes: set[str] = set()
        for component in components:
            for node in component.nodes:
                connections.setdefault(node, []).append(component.name)
            if component.component_type == "M" and len(component.nodes) >= 4:
                bulk_terminal_nodes.add(component.nodes[3])
                non_bulk_terminal_nodes.update(component.nodes[:3])
            else:
                non_bulk_terminal_nodes.update(component.nodes)
        signal_nodes = {record.positive_node for record in source_records if record.role == "SIGNAL_SOURCE"}
        bias_nodes = {
            record.positive_node
            for record in source_records
            if record.role in {"BIAS_SOURCE", "INTERNAL_BIAS_SOURCE"}
        }
        supply_nodes = {
            node
            for record in source_records
            if record.role == "SUPPLY_SOURCE"
            for node in (record.positive_node, record.negative_node)
            if node != "0"
        }
        declared_output_names = {_normalize_name(item) for item in declared_outputs}
        output_nodes: set[str] = set()
        for node in connections:
            lowered = _normalize_name(node)
            if lowered in declared_output_names or lowered in OUTPUT_NAME_HINTS:
                output_nodes.add(node)
        if not output_nodes:
            ranked = sorted(
                connections.items(),
                key=lambda item: (any(_normalize_name(item[0]).endswith(hint) for hint in OUTPUT_NAME_HINTS), len(item[1])),
                reverse=True,
            )
            if ranked:
                output_nodes.add(ranked[0][0])
        records: list[NodeRecord] = []
        for node in sorted(connections):
            lowered = _normalize_name(node)
            declared_role = "ground" if node == "0" else "unknown"
            inferred_role = "internal"
            confidence = 0.8
            if node == "0":
                inferred_role = "ground"
                confidence = 1.0
            elif node in output_nodes:
                inferred_role = "output"
                confidence = 0.95
            elif node in signal_nodes:
                inferred_role = "signal_input"
                confidence = 0.95
            elif node in supply_nodes:
                inferred_role = "supply"
                confidence = 0.95
            elif node in bias_nodes:
                inferred_role = "bias"
                confidence = 0.9
            elif node in bulk_terminal_nodes and node not in non_bulk_terminal_nodes:
                inferred_role = "bulk"
                confidence = 0.8
            elif lowered.startswith("vout"):
                inferred_role = "output"
                confidence = 0.7
            manual_review = confidence < 0.75 or (inferred_role == "output" and len(output_nodes) > 1 and lowered not in declared_output_names)
            records.append(
                NodeRecord(
                    node_name=node,
                    connected_elements=tuple(sorted(connections[node])),
                    degree=len(connections[node]),
                    declared_role=declared_role,
                    inferred_role=inferred_role,
                    role_confidence=confidence,
                    manual_review_required=manual_review,
                    bulk_terminal=node in bulk_terminal_nodes,
                )
            )
        return records

    def _infer_topology(
        self,
        case_id: str,
        description: str,
        components: list[ParsedComponent],
        source_records: list[SourceRecord],
        node_records: list[NodeRecord],
    ) -> str:
        case = case_id.lower()
        source_roles = {record.name.lower(): record.role for record in source_records}
        mos_count = sum(1 for component in components if component.component_type == "M")
        resistor_count = sum(1 for component in components if component.component_type == "R")
        capacitor_count = sum(1 for component in components if component.component_type == "C")
        subckt_count = sum(1 for component in components if component.component_type == "X")
        node_roles = {record.node_name: record.inferred_role for record in node_records}
        if case == "p01_amplifier":
            return "common-source"
        if case == "p02_amplifier":
            return "multi-stage amplifier with common-gate-like middle stage"
        if case == "p03_amplifier":
            return "common-drain/source-follower"
        if case == "p04_amplifier":
            return "common-gate"
        if case == "p05_amplifier":
            return "cascode"
        if case == "p06_inverter":
            return "resistor-load inverter"
        if case == "p07_inverter":
            return "cmos inverter"
        if case == "p08_currentmirror":
            return "current mirror"
        if case == "p09_comparator":
            return "opamp comparator"
        if case == "p10_lowpass":
            return "passive low-pass filter"
        if case == "p11_highpass":
            return "passive high-pass filter"
        if case == "p12_bandpass":
            return "passive band-pass filter"
        if case == "p13_bandstop":
            return "passive band-stop filter"
        if case == "p14_amplifier":
            return "two-stage Miller-compensated amplifier"
        if case == "p15_amplifier":
            return "common-source with diode-connected PMOS load"
        if case == "p16_opamp":
            return "differential opamp with active mirror load"
        if case == "p17_currentmirror":
            return "cascode current mirror"
        if case == "p18_opamp":
            return "single-stage differential opamp"
        if case == "p19_mixer":
            return "Gilbert-cell mixer"
        if case == "p20_opamp":
            return "two-stage differential opamp"
        if case == "p21_opamp":
            return "telescopic cascode opamp"
        if case == "p22_oscillator":
            return "RC phase-shift oscillator"
        if case == "p23_oscillator":
            return "Wien bridge oscillator"
        if case == "p24_integrator":
            return "opamp integrator"
        if case == "p25_differentiator":
            return "opamp differentiator"
        if case == "p26_adder":
            return "opamp adder"
        if case == "p27_subtractor":
            return "opamp subtractor"
        if case == "p28_schmitt":
            return "non-inverting Schmitt trigger"
        if "oscillator" in description.lower():
            return "oscillator"
        if "schmitt" in description.lower():
            return "Schmitt trigger"
        if subckt_count and resistor_count and capacitor_count:
            return "opamp composite"
        if mos_count and resistor_count and any(role == "SIGNAL_SOURCE" for role in source_roles.values()):
            return "transistor amplifier"
        return "unconfirmed"

    def _topology_match_status(self, declared_topology: str, inferred_topology: str) -> str:
        declared = declared_topology.lower()
        inferred = inferred_topology.lower()
        if not declared or inferred == "unconfirmed":
            return "UNCONFIRMED"
        if declared == inferred or all(token in declared for token in inferred.split()):
            return "MATCH"
        if any(token in declared for token in inferred.split()) or any(token in inferred for token in declared.split()):
            return "PARTIAL_MATCH"
        if len(declared.split()) <= 3:
            return "DESCRIPTION_TOO_GENERAL"
        return "DESCRIPTION_MISMATCH"

    def _build_anomalies(
        self,
        *,
        case_name: str,
        components: list[ParsedComponent],
        classifications: list[LineClassification],
        source_records: list[SourceRecord],
        node_records: list[NodeRecord],
        analyses: list[dict[str, Any]],
        unknown_directives: list[str],
        inferred_topology: str,
        output_nodes: list[str],
    ) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        names = [component.name for component in components]
        if len(names) != len(set(names)):
            anomalies.append({"case_id": case_name, "code": "DUPLICATE_ELEMENT_NAME", "details": "Duplicate SPICE element names detected"})
        has_ac = any(item["directive"] == ".AC" for item in analyses)
        signal_sources = [record for record in source_records if record.role == "SIGNAL_SOURCE"]
        if has_ac and not signal_sources:
            anomalies.append({"case_id": case_name, "code": "EMBEDDED_ANALYSIS_WITHOUT_VALID_STIMULUS", "details": "AC analysis present without identified signal source"})
        if has_ac:
            for source in signal_sources:
                if not source.original_ac_magnitude or not math.isclose(source.original_ac_magnitude, 1.0, rel_tol=0.0, abs_tol=1e-12):
                    anomalies.append(
                        {
                            "case_id": case_name,
                            "code": "AC_INPUT_MAGNITUDE_NOT_UNITY",
                            "details": f"{source.name} uses AC magnitude {source.original_ac_magnitude}",
                        }
                    )
        has_tran = any(item["directive"] == ".TRAN" for item in analyses)
        if has_tran:
            for source in signal_sources:
                if source.original_waveform is None and source.original_ac_magnitude is None:
                    anomalies.append(
                        {
                            "case_id": case_name,
                            "code": "TRANSIENT_ANALYSIS_WITH_CONSTANT_INPUT",
                            "details": f"{source.name} drives TRAN with a constant source definition",
                        }
                    )
        for node in node_records:
            if node.degree <= 1 and node.inferred_role == "internal":
                anomalies.append(
                    {
                        "case_id": case_name,
                        "code": "FLOATING_NODE_CANDIDATE",
                        "details": f"{node.node_name} has degree {node.degree}",
                    }
                )
        if not output_nodes:
            anomalies.append({"case_id": case_name, "code": "OUTPUT_NODE_AMBIGUOUS", "details": "No output node resolved"})
        if "common-gate-like" in inferred_topology:
            anomalies.append(
                {
                    "case_id": case_name,
                    "code": "MANUAL_REVIEW_REQUIRED",
                    "details": "The middle stage topology needs manual review",
                }
            )
        if any(item.selected_category == "UNKNOWN_DIRECTIVE" for item in classifications):
            anomalies.append({"case_id": case_name, "code": "UNSUPPORTED_DIRECTIVE", "details": "Unknown directive found in deck"})
        if unknown_directives:
            anomalies.append({"case_id": case_name, "code": "UNKNOWN_MODEL", "details": "|".join(unknown_directives)})
        return anomalies

    def _compatible_metrics(self, declared_type: str, inferred_topology: str) -> list[dict[str, Any]]:
        metric_matrix = {
            "amplifier": ["operating_point", "dc_gain_db", "cutoff_frequency_hz", "bandwidth", "phase_margin"],
            "currentmirror": ["operating_point", "quiescent_current"],
            "current_mirror": ["operating_point", "quiescent_current"],
            "inverter": ["operating_point", "propagation_delay", "static_power"],
            "comparator": ["propagation_delay"],
            "lowpass": ["cutoff_frequency_hz"],
            "highpass": ["cutoff_frequency_hz"],
            "bandpass": ["cutoff_frequency_hz"],
            "bandstop": ["cutoff_frequency_hz"],
            "opamp": ["dc_gain_db", "phase_margin", "quiescent_current"],
            "oscillator": ["oscillator_frequency", "startup_amplitude"],
            "integrator": ["slew_rate", "settling_time"],
            "differentiator": ["slew_rate"],
            "adder": ["operating_point"],
            "subtractor": ["operating_point"],
            "schmitt": ["propagation_delay", "hysteresis_width"],
        }
        implemented_metrics = {
            "operating_point",
            "vout_dc",
            "quiescent_current",
            "idd",
            "power",
            "dc_gain",
            "dc_gain_db",
            "cutoff_frequency_hz",
            "bandwidth",
            "unity_gain_frequency",
            "ugbw",
            "phase_margin",
            "slew_rate",
            "settling_time",
            "propagation_delay",
            "oscillator_frequency",
            "startup_amplitude",
            "hysteresis_width",
        }
        lookup = re.sub(r"[^a-z]", "", declared_type.lower())
        candidates = metric_matrix.get(lookup, [])
        rows: list[dict[str, Any]] = []
        for metric in candidates:
            if metric in implemented_metrics:
                status = "IMPLEMENTED_AND_COMPATIBLE"
            else:
                status = "TOPOLOGICALLY_COMPATIBLE_NOT_IMPLEMENTED"
            rows.append({"metric_name": metric, "status": status, "topology": inferred_topology})
        return rows

    def _build_canonical_dut(
        self,
        *,
        source_path: Path,
        line_classifications: list[LineClassification],
        components: list[ParsedComponent],
        source_records: list[SourceRecord],
    ) -> str:
        allowed_categories = {
            "COMMENT",
            "MODEL_DEFINITION",
            "SUBCIRCUIT_DEFINITION",
            "SUBCIRCUIT_END",
            "SUBCIRCUIT_INSTANCE",
            "SUPPLY_SOURCE",
            "BIAS_SOURCE",
            "INTERNAL_BIAS_SOURCE",
            "SIGNAL_SOURCE",
            "DUT_DEVICE",
            "DUT_LOAD",
        }
        selected_lines: list[str] = [
            f"* Canonical DUT generated from {source_path.as_posix()}",
            "* Embedded analyses and output directives were externalized into metadata.",
        ]
        component_by_line = {component.line_number: component for component in components}
        source_by_name = {record.name: record for record in source_records}
        for classification in line_classifications:
            if classification.selected_category not in allowed_categories:
                continue
            component = component_by_line.get(classification.line_number)
            if component is None:
                selected_lines.append(classification.raw_line)
                continue
            if classification.selected_category == "SIGNAL_SOURCE":
                record = source_by_name[component.name]
                selected_lines.append(f"* original signal source: {record.original_definition}")
                selected_lines.append(f"{component.name} {component.nodes[0]} {component.nodes[1]} 0")
                continue
            selected_lines.append(classification.raw_line)
        return "\n".join(selected_lines).rstrip() + "\n"

    def _parse_canonical_components(self, canonical_dut_text: str) -> list[ParsedComponent]:
        components: list[ParsedComponent] = []
        for index, line in enumerate(canonical_dut_text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("*") or stripped.startswith("."):
                continue
            component = self._parse_component_line(index, line)
            if component is not None:
                components.append(component)
        return components

    def _logical_dut_hash(
        self,
        line_classifications: tuple[LineClassification, ...] | list[LineClassification],
        components: list[ParsedComponent],
        source_records: list[SourceRecord],
    ) -> str:
        source_roles = {record.name: record.role for record in source_records}
        normalized_entries: list[str] = []
        for component in components:
            if component.component_type in {"V", "I"}:
                category = source_roles.get(component.name, "BIAS_SOURCE")
            elif component.component_type in {"R", "C", "L"}:
                category = "DUT_LOAD"
            elif component.component_type == "X":
                category = "SUBCIRCUIT_INSTANCE"
            else:
                category = "DUT_DEVICE"
            if category == "SIGNAL_SOURCE":
                role = source_roles.get(component.name, "SIGNAL_SOURCE")
                normalized_entries.append(
                    "|".join(
                        [
                            category,
                            role,
                            component.name.lower(),
                            component.nodes[0].lower(),
                            component.nodes[1].lower(),
                        ]
                    )
                )
                continue
            normalized_entries.append("|".join([category, *component.normalized_tokens()]))
        return _stable_json_sha(sorted(normalized_entries))

    def _harness_metadata(self, source_records: list[SourceRecord], node_records: list[NodeRecord]) -> dict[str, Any]:
        return {
            "sources": [item.to_dict() for item in source_records],
            "ground_node": "0",
            "all_nodes": [item.node_name for item in node_records],
            "signal_input_nodes": [item.node_name for item in node_records if item.inferred_role == "signal_input"],
            "bias_nodes": [item.node_name for item in node_records if item.inferred_role == "bias"],
            "supply_nodes": [item.node_name for item in node_records if item.inferred_role == "supply"],
            "output_nodes": [item.node_name for item in node_records if item.inferred_role == "output"],
            "internal_nodes": [item.node_name for item in node_records if item.inferred_role == "internal"],
            "bulk_nodes": [item.node_name for item in node_records if item.bulk_terminal],
            "floating_candidates": [item.node_name for item in node_records if item.degree <= 1 and item.inferred_role == "internal"],
        }

    def _circuit_metadata(
        self,
        case_id: str,
        declared_type: str,
        declared_topology: str,
        description: str,
        node_records: list[NodeRecord],
        source_records: list[SourceRecord],
        inferred_topology: str,
        topology_match_status: str,
        anomalies: list[dict[str, Any]],
        compatible_metrics: list[dict[str, Any]],
        analyses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "declared_type": declared_type,
            "declared_topology": declared_topology,
            "description": description,
            "inferred_topology": inferred_topology,
            "topology_match_status": topology_match_status,
            "signal_inputs": [item.node_name for item in node_records if item.inferred_role == "signal_input"],
            "bias_inputs": [item.node_name for item in node_records if item.inferred_role == "bias"],
            "supplies": [item.node_name for item in node_records if item.inferred_role == "supply"],
            "outputs": [item.node_name for item in node_records if item.inferred_role == "output"],
            "internal_nodes": [item.node_name for item in node_records if item.inferred_role == "internal"],
            "sources": [item.to_dict() for item in source_records],
            "replaceable_sources": [item.name for item in source_records if item.replaceable_by_testbench],
            "nonreplaceable_sources": [item.name for item in source_records if not item.replaceable_by_testbench],
            "embedded_analyses": [item["raw_line"] for item in analyses],
            "embedded_measurements": [item["raw_line"] for item in analyses if item["directive"] in {".MEASURE", ".MEAS"}],
            "compatible_metrics": compatible_metrics,
            "anomalies": anomalies,
            "manual_review_required": any(item.get("code") == "MANUAL_REVIEW_REQUIRED" for item in anomalies),
            "audit_status": "READY" if topology_match_status != "UNCONFIRMED" else "MANUAL_REVIEW_REQUIRED",
        }
