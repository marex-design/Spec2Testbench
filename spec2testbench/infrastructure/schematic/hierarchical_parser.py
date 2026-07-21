"""Hierarchical SPICE parsing for publication schematic generation.

The simulation parser intentionally ignores directives.  A publication
schematic needs more context: includes must be resolved and local subcircuit
instances must be expanded before connectivity can be validated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .netlist_parser import Component, NetlistParser


_INCLUDE_RE = re.compile(r"^\s*\.(?:include|inc)\s+(.+?)\s*$", re.IGNORECASE)
_MODEL_RE = re.compile(r"^\s*\.model\s+(\S+)\s+(\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class PinRef:
    """One component terminal connected to one normalized net."""

    component_id: str
    pin_index: int
    pin_name: str
    net: str


@dataclass
class NormalizedComponent:
    """A flattened component whose terminal order remains SPICE-compatible."""

    component_id: str
    name: str
    kind: str
    pins: list[PinRef]
    value: str | None = None
    model: str | None = None
    variant: str | None = None
    hierarchy: str = "top"

    @property
    def nodes(self) -> list[str]:
        return [pin.net for pin in self.pins]


@dataclass
class ParseDiagnostics:
    """Traceability information collected while resolving hierarchy."""

    source_file: str | None = None
    resolved_includes: list[str] = field(default_factory=list)
    unresolved_includes: list[str] = field(default_factory=list)
    resolved_instances: list[str] = field(default_factory=list)
    expanded_instances: list[str] = field(default_factory=list)
    unresolved_instances: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class NormalizedCircuitGraph:
    """Canonical component-pin-net representation used by the renderer."""

    components: list[NormalizedComponent]
    nets: dict[str, list[PinRef]]
    diagnostics: ParseDiagnostics

    @property
    def pin_count(self) -> int:
        return sum(len(component.pins) for component in self.components)

    def by_kind(self, kind: str) -> list[NormalizedComponent]:
        return [component for component in self.components if component.kind == kind.upper()]


@dataclass
class _Subcircuit:
    name: str
    formal_nodes: list[str]
    body: list[str]


class HierarchicalNetlistParser:
    """Resolve includes and flatten locally available SPICE subcircuits."""

    def __init__(self, max_depth: int = 20):
        self.max_depth = max_depth
        self._component_parser = NetlistParser()

    def parse_path(
        self, path: Path, *, flatten_subcircuits: bool = True
    ) -> NormalizedCircuitGraph:
        path = path.resolve()
        diagnostics = ParseDiagnostics(source_file=str(path))
        lines = self._load_with_includes(path, diagnostics, stack=[])
        return self._normalize(lines, diagnostics, flatten_subcircuits=flatten_subcircuits)

    def parse_text(
        self,
        netlist: str,
        *,
        base_dir: Path | None = None,
        source_name: str | None = None,
        flatten_subcircuits: bool = True,
    ) -> NormalizedCircuitGraph:
        diagnostics = ParseDiagnostics(source_file=source_name)
        lines = self._merge_continuations(netlist.splitlines())
        if base_dir is not None:
            lines = self._resolve_inline_includes(lines, base_dir.resolve(), diagnostics, stack=[])
        elif any(_INCLUDE_RE.match(line) for line in lines):
            diagnostics.unresolved_includes.extend(
                self._include_target(line) for line in lines if _INCLUDE_RE.match(line)
            )
        return self._normalize(lines, diagnostics, flatten_subcircuits=flatten_subcircuits)

    def _load_with_includes(
        self,
        path: Path,
        diagnostics: ParseDiagnostics,
        stack: list[Path],
    ) -> list[str]:
        if path in stack:
            diagnostics.warnings.append(f"Include cycle skipped: {path}")
            return []
        if not path.exists():
            diagnostics.unresolved_includes.append(str(path))
            return []

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")
        lines = self._merge_continuations(text.splitlines())
        return self._resolve_inline_includes(lines, path.parent, diagnostics, stack + [path])

    def _resolve_inline_includes(
        self,
        lines: Iterable[str],
        base_dir: Path,
        diagnostics: ParseDiagnostics,
        stack: list[Path],
    ) -> list[str]:
        resolved: list[str] = []
        for line in lines:
            match = _INCLUDE_RE.match(line)
            if not match:
                resolved.append(line)
                continue
            target = self._clean_path_token(match.group(1))
            include_path = Path(target)
            if not include_path.is_absolute():
                include_path = (base_dir / include_path).resolve()
            if include_path.exists():
                diagnostics.resolved_includes.append(str(include_path))
                resolved.extend(self._load_with_includes(include_path, diagnostics, stack))
            else:
                diagnostics.unresolved_includes.append(str(include_path))
        return resolved

    def _normalize(
        self,
        lines: list[str],
        diagnostics: ParseDiagnostics,
        *,
        flatten_subcircuits: bool,
    ) -> NormalizedCircuitGraph:
        subcircuits, top_level = self._extract_subcircuits(lines, diagnostics)
        model_types = self._extract_model_types(lines)
        components: list[NormalizedComponent] = []
        self._expand_lines(
            top_level,
            subcircuits,
            model_types,
            components,
            diagnostics,
            scope="top",
            node_bindings={},
            depth=0,
            flatten_subcircuits=flatten_subcircuits,
        )

        nets: dict[str, list[PinRef]] = {}
        for component in components:
            for pin in component.pins:
                nets.setdefault(pin.net, []).append(pin)
        return NormalizedCircuitGraph(components=components, nets=nets, diagnostics=diagnostics)

    def _expand_lines(
        self,
        lines: Iterable[str],
        subcircuits: dict[str, _Subcircuit],
        model_types: dict[str, str],
        output: list[NormalizedComponent],
        diagnostics: ParseDiagnostics,
        *,
        scope: str,
        node_bindings: dict[str, str],
        depth: int,
        flatten_subcircuits: bool,
    ) -> None:
        if depth > self.max_depth:
            diagnostics.warnings.append(f"Maximum subcircuit depth exceeded at {scope}")
            return

        for line in lines:
            parsed = self._component_parser.parse(line).components
            if not parsed:
                continue
            component = parsed[0]
            if component.type == "X":
                component = self._normalize_subcircuit_instance(line, component, subcircuits)
                subckt = subcircuits.get((component.model or "").lower())
                if subckt is None:
                    diagnostics.unresolved_instances.append(self._scoped_name(scope, component.name))
                    self._append_component(
                        component,
                        output,
                        model_types,
                        scope=scope,
                        node_bindings=node_bindings,
                    )
                    continue
                if len(component.nodes) != len(subckt.formal_nodes):
                    diagnostics.warnings.append(
                        f"{self._scoped_name(scope, component.name)} maps "
                        f"{len(component.nodes)} nodes to {len(subckt.formal_nodes)} formal nodes"
                    )
                    diagnostics.unresolved_instances.append(self._scoped_name(scope, component.name))
                    self._append_component(
                        component,
                        output,
                        model_types,
                        scope=scope,
                        node_bindings=node_bindings,
                    )
                    continue

                child_scope = self._scoped_name(scope, component.name)
                diagnostics.resolved_instances.append(child_scope)
                if not flatten_subcircuits:
                    self._append_component(
                        component,
                        output,
                        model_types,
                        scope=scope,
                        node_bindings=node_bindings,
                    )
                    continue
                actual_nodes = [self._map_node(node, node_bindings, scope) for node in component.nodes]
                child_bindings = dict(zip(subckt.formal_nodes, actual_nodes))
                diagnostics.expanded_instances.append(child_scope)
                self._expand_lines(
                    subckt.body,
                    subcircuits,
                    model_types,
                    output,
                    diagnostics,
                    scope=child_scope,
                    node_bindings=child_bindings,
                    depth=depth + 1,
                    flatten_subcircuits=flatten_subcircuits,
                )
                continue

            self._append_component(
                component,
                output,
                model_types,
                scope=scope,
                node_bindings=node_bindings,
            )

    def _append_component(
        self,
        component: Component,
        output: list[NormalizedComponent],
        model_types: dict[str, str],
        *,
        scope: str,
        node_bindings: dict[str, str],
    ) -> None:
        component_id = self._scoped_name(scope, component.name)
        pin_names = self._pin_names(component.type, len(component.nodes))
        pins = [
            PinRef(
                component_id=component_id,
                pin_index=index,
                pin_name=pin_names[index],
                net=self._map_node(node, node_bindings, scope),
            )
            for index, node in enumerate(component.nodes)
        ]
        output.append(
            NormalizedComponent(
                component_id=component_id,
                name=component.name,
                kind=component.type.upper(),
                pins=pins,
                value=component.value,
                model=component.model,
                variant=self._device_variant(component, model_types),
                hierarchy=scope,
            )
        )

    @staticmethod
    def _extract_subcircuits(
        lines: list[str], diagnostics: ParseDiagnostics
    ) -> tuple[dict[str, _Subcircuit], list[str]]:
        definitions: dict[str, _Subcircuit] = {}
        top_level: list[str] = []
        current_name: str | None = None
        formal_nodes: list[str] = []
        body: list[str] = []

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()
            if lower.startswith(".subckt"):
                if current_name is not None:
                    diagnostics.warnings.append(f"Nested .SUBCKT ignored inside {current_name}")
                tokens = stripped.split()
                if len(tokens) < 2:
                    diagnostics.warnings.append(f"Malformed .SUBCKT directive: {stripped}")
                    continue
                current_name = tokens[1]
                formal_nodes = [token for token in tokens[2:] if "=" not in token]
                body = []
                continue
            if lower.startswith(".ends"):
                if current_name is not None:
                    definitions[current_name.lower()] = _Subcircuit(
                        name=current_name,
                        formal_nodes=formal_nodes,
                        body=body,
                    )
                current_name = None
                formal_nodes = []
                body = []
                continue
            if current_name is None:
                top_level.append(line)
            else:
                body.append(line)

        if current_name is not None:
            diagnostics.warnings.append(f"Unterminated .SUBCKT: {current_name}")
            definitions[current_name.lower()] = _Subcircuit(current_name, formal_nodes, body)
        return definitions, top_level

    @staticmethod
    def _extract_model_types(lines: Iterable[str]) -> dict[str, str]:
        models: dict[str, str] = {}
        for line in lines:
            match = _MODEL_RE.match(line)
            if match:
                models[match.group(1).lower()] = match.group(2).lower()
        return models

    @staticmethod
    def _normalize_subcircuit_instance(
        line: str,
        component: Component,
        subcircuits: dict[str, _Subcircuit],
    ) -> Component:
        """Locate the subcircuit name before optional instance parameters."""
        tokens = line.split(";", 1)[0].split()
        for index, token in enumerate(tokens[2:], start=2):
            if token.lower() in subcircuits:
                return Component(
                    name=tokens[0],
                    type="X",
                    nodes=tokens[1:index],
                    model=token,
                    value=" ".join(tokens[index + 1 :]) or None,
                )
        return component

    @staticmethod
    def _map_node(node: str, bindings: dict[str, str], scope: str) -> str:
        if node in bindings:
            return bindings[node]
        if node == "0":
            return "0"
        if scope == "top":
            return node
        return f"{scope}:{node}"

    @staticmethod
    def _device_variant(component: Component, model_types: dict[str, str]) -> str | None:
        if component.type != "M":
            return None
        model = (component.model or "").lower()
        model_type = model_types.get(model, "")
        combined = f"{model} {model_type}"
        if "pmos" in combined or "pfet" in combined:
            return "pmos"
        if "nmos" in combined or "nfet" in combined:
            return "nmos"
        return "mos"

    @staticmethod
    def _pin_names(kind: str, count: int) -> list[str]:
        standard = {
            "M": ["D", "G", "S", "B"],
            "Q": ["C", "B", "E"],
            "J": ["D", "G", "S"],
            "R": ["1", "2"],
            "C": ["1", "2"],
            "L": ["1", "2"],
            "V": ["+", "-"],
            "I": ["+", "-"],
            "D": ["A", "K"],
            "E": ["+", "-", "C+", "C-"],
            "G": ["+", "-", "C+", "C-"],
        }.get(kind.upper(), [])
        return [standard[index] if index < len(standard) else f"P{index + 1}" for index in range(count)]

    @staticmethod
    def _scoped_name(scope: str, name: str) -> str:
        return name if scope == "top" else f"{scope}/{name}"

    @staticmethod
    def _merge_continuations(lines: Iterable[str]) -> list[str]:
        merged: list[str] = []
        for line in lines:
            if line.lstrip().startswith("+") and merged:
                merged[-1] = merged[-1].rstrip() + " " + line.lstrip()[1:].strip()
            else:
                merged.append(line)
        return merged

    @staticmethod
    def _clean_path_token(token: str) -> str:
        token = token.strip()
        if token and token[0] in {'"', "'"}:
            closing = token.find(token[0], 1)
            if closing != -1:
                return token[1:closing]
        return token.split()[0]

    @classmethod
    def _include_target(cls, line: str) -> str:
        match = _INCLUDE_RE.match(line)
        return cls._clean_path_token(match.group(1)) if match else line.strip()
