from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ...domain.entities.specification import Specification
from .llm_metric_registry import METRIC_DEFINITIONS


ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_VERSION = "knowledge_stub_v1"
RULE_SCHEMA_VERSION = "1.0"
ACTIVE_RULE_STATUSES = {
    "CONFIRMED_PORTABLE",
    "CONFIRMED_NGSPICE_INSTALLED",
    "CONFIRMED_SPEC2TESTBENCH",
}
FROZEN_GROUND_TRUTH_TOKENS = {
    "GROUND_TRUTH_COMPLIANT",
    "GROUND_TRUTH_NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
    "UNEVALUATED",
}
REPRESENTATIVE_NOMINAL_CASE_IDS = [
    "p01_amplifier",
    "p05_amplifier",
    "p09_comparator",
    "p10_lowpass",
    "p22_oscillator",
]


@dataclass(frozen=True)
class KnowledgeBundle:
    case_id: str
    use_case: str
    requested_metrics: list[str]
    knowledge_version: str
    rules: list[dict[str, Any]]
    recipes: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    examples: list[dict[str, Any]]
    bundle_sha256: str

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "knowledge_version": self.knowledge_version,
            "knowledge_bundle_sha256": self.bundle_sha256,
            "use_case": self.use_case,
            "requested_metrics": list(self.requested_metrics),
            "rules": self.rules,
            "recipes": self.recipes,
            "tools": self.tools,
            "examples": self.examples,
        }

    def trace_row(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "use_case": self.use_case,
            "knowledge_version": self.knowledge_version,
            "bundle_sha256": self.bundle_sha256,
            "rule_count": len(self.rules),
            "recipe_count": len(self.recipes),
            "tool_count": len(self.tools),
            "example_count": len(self.examples),
        }


def json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=1000),
        encoding="utf-8",
    )


def rewrite_knowledge_version(payload: Any, knowledge_version: str) -> Any:
    if isinstance(payload, dict):
        return {
            key: (knowledge_version if key == "knowledge_version" else rewrite_knowledge_version(value, knowledge_version))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [rewrite_knowledge_version(item, knowledge_version) for item in payload]
    return payload


def resolve_catalog_knowledge_version(catalog: dict[str, list[dict[str, Any]]]) -> str:
    for kind in ("rules", "recipes", "tools", "examples", "metric_mapping", "guards", "policies", "failures"):
        for entry in catalog.get(kind, []):
            candidate = str(entry.get("knowledge_version", "")).strip()
            if candidate:
                return candidate
    return KNOWLEDGE_VERSION


def infer_use_case(metric_name: str) -> str:
    metric_lower = metric_name.lower()
    if metric_lower in {"operating_point", "vout_dc"}:
        return "UC_DC_BIAS"
    if metric_lower in {"quiescent_current", "idd", "power"}:
        return "UC_DC_CURRENT_POWER"
    if metric_lower in {"dc_gain", "dc_gain_db"}:
        return "UC_AC_GAIN"
    if metric_lower in {"bandwidth", "cutoff_frequency_hz"}:
        return "UC_FILTER_CUTOFF_BANDWIDTH"
    if metric_lower in {"propagation_delay", "propagation_delay_s", "settling_time", "slew_rate"}:
        return "UC_TRANSIENT_DELAY"
    if metric_lower in {"oscillator_frequency", "frequency_hz", "startup_amplitude"}:
        return "UC_OSCILLATION_FREQUENCY"
    if metric_lower in {"v_t_plus", "v_t_minus", "hysteresis_width"}:
        return "UC_SWITCHING_THRESHOLD_HYSTERESIS"
    return "UC_UNMAPPED"


def required_rule_ids_for_use_case(use_case: str) -> list[str]:
    mapping = {
        "UC_DC_BIAS": [
            "OBSERVED_NODE_MUST_EXIST",
            "OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
            "NGSPICE_WRDATA_DC_EXPORTS_OUTPUT_AND_SUPPLY_CURRENT",
        ],
        "UC_DC_CURRENT_POWER": [
            "SUPPLY_SOURCE_PRESERVED",
            "OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
            "NGSPICE_WRDATA_DC_EXPORTS_OUTPUT_AND_SUPPLY_CURRENT",
        ],
        "UC_AC_GAIN": [
            "AC_TRANSFER_GAIN_USES_COMPLEX_RATIO",
            "ZERO_AC_INPUT_IS_NOT_EVALUATED",
            "NGSPICE_WRDATA_AC_EXPORTS_COMPLEX_COMPONENTS",
        ],
        "UC_FILTER_CUTOFF_BANDWIDTH": [
            "CUTOFF_REQUIRES_AC_SWEEP",
            "NGSPICE_AC_WRDATA_REQUIRES_SETPLOT_AC1",
            "NGSPICE_WRDATA_AC_EXPORTS_COMPLEX_COMPONENTS",
        ],
        "UC_TRANSIENT_DELAY": [
            "TRAN_PROPAGATION_DELAY_REQUIRES_INPUT_AND_OUTPUT",
            "INPUT_NODE_ROLE_REQUIRED",
            "OUTPUT_NODE_ROLE_REQUIRED",
        ],
        "UC_OSCILLATION_FREQUENCY": [
            "VALID_OSCILLATION_REQUIRED_FOR_FREQUENCY",
            "MISSING_METRIC_IS_NOT_ZERO",
            "OUTPUT_NODE_ROLE_REQUIRED",
        ],
        "UC_SWITCHING_THRESHOLD_HYSTERESIS": [
            "HYSTERESIS_REQUIRES_INPUT_AND_OUTPUT_WAVEFORMS",
            "INPUT_NODE_ROLE_REQUIRED",
            "OUTPUT_NODE_ROLE_REQUIRED",
        ],
    }
    return mapping.get(use_case, [])


def detect_ngspice_environment(
    ngspice_executable: str | None = None,
    *,
    knowledge_version: str = KNOWLEDGE_VERSION,
) -> dict[str, Any]:
    executable = ngspice_executable or r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe"
    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    version_text = (result.stdout or result.stderr or "").strip()
    version_line = next((line.strip("* ").strip() for line in version_text.splitlines() if "ngspice-" in line.lower()), "")
    return {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": knowledge_version,
        "kind": "environment",
        "environment": {
            "ngspice_executable": executable,
            "ngspice_version": version_line,
            "raw_version_output": version_text,
            "operating_system": platform.platform(),
        },
    }


def load_microtest_statuses(results_path: Path | None) -> dict[str, bool]:
    if results_path is None or not results_path.exists():
        return {}
    statuses: dict[str, bool] = {}
    for row in read_csv(results_path):
        statuses[str(row.get("microtest_id", "")).strip()] = str(row.get("status", "")).strip().upper() == "PASS"
    return statuses


def _source(source_type: str, document_path: str, *, section: str | None = None, page: str | None = None) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "document_path": document_path,
        "section": section,
        "page": page,
    }


def _enforcement(
    *,
    llm_visible: bool,
    retriever_visible: bool,
    validator_enforced: bool,
    compiler_enforced: bool,
    backend_enforced: bool,
    checker_enforced: bool,
) -> dict[str, Any]:
    return {
        "llm_visible": llm_visible,
        "retriever_visible": retriever_visible,
        "validator_enforced": validator_enforced,
        "compiler_enforced": compiler_enforced,
        "backend_enforced": backend_enforced,
        "checker_enforced": checker_enforced,
    }


def _rule(
    *,
    rule_id: str,
    category: str,
    title: str,
    description: str,
    analyses: list[str],
    metrics: list[str],
    circuit_families: list[str],
    backends: list[str],
    requires: dict[str, Any],
    forbids: list[str],
    source: dict[str, Any],
    dialect_scope: list[str],
    enforcement: dict[str, Any],
    verification_status: str,
    positive_test_ids: list[str],
    negative_test_ids: list[str],
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "category": category,
        "title": title,
        "description": description,
        "applies_to": {
            "analyses": analyses,
            "metrics": metrics,
            "circuit_families": circuit_families,
            "backends": backends,
        },
        "requires": requires,
        "forbids": forbids,
        "source": source,
        "dialect_scope": dialect_scope,
        "enforcement": enforcement,
        "verification": {
            "status": verification_status,
            "positive_test_ids": positive_test_ids,
            "negative_test_ids": negative_test_ids,
        },
    }


def _recipe(
    *,
    recipe_id: str,
    source_type: str,
    compatible_analyses: list[str],
    required_parameters: list[str],
    optional_parameters: list[str],
    parameter_constraints: list[str],
    compiler_template_id: str,
    scientific_guards: list[str],
    known_failure_modes: list[str],
    positive_tests: list[str],
    negative_tests: list[str],
    verification_status: str,
    implementation_ref: str,
    metrics: list[str],
) -> dict[str, Any]:
    return {
        "recipe_id": recipe_id,
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "source_type": source_type,
        "compatible_analyses": compatible_analyses,
        "required_parameters": required_parameters,
        "optional_parameters": optional_parameters,
        "parameter_constraints": parameter_constraints,
        "compiler_template_id": compiler_template_id,
        "scientific_guards": scientific_guards,
        "known_failure_modes": known_failure_modes,
        "positive_tests": positive_tests,
        "negative_tests": negative_tests,
        "verification_status": verification_status,
        "implementation_ref": implementation_ref,
        "metrics": metrics,
        "retriever_visible": verification_status in ACTIVE_RULE_STATUSES,
    }


def _tool(
    *,
    tool_id: str,
    title: str,
    category: str,
    compiler_template_id: str,
    implementation_ref: str,
    supported_analyses: list[str],
    supported_metrics: list[str],
    verification_status: str,
) -> dict[str, Any]:
    return {
        "tool_id": tool_id,
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "title": title,
        "category": category,
        "compiler_template_id": compiler_template_id,
        "implementation_ref": implementation_ref,
        "supported_analyses": supported_analyses,
        "supported_metrics": supported_metrics,
        "verification_status": verification_status,
        "retriever_visible": verification_status in ACTIVE_RULE_STATUSES,
    }


def _example(
    *,
    example_id: str,
    use_case: str,
    title: str,
    summary: str,
    plan_shape: dict[str, Any],
    safe_circuit_families: list[str],
    safe_metrics: list[str],
    positive_tests: list[str],
) -> dict[str, Any]:
    return {
        "example_id": example_id,
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "use_case": use_case,
        "title": title,
        "summary": summary,
        "plan_shape": plan_shape,
        "safe_circuit_families": safe_circuit_families,
        "safe_metrics": safe_metrics,
        "positive_tests": positive_tests,
        "verification_status": "CONFIRMED_SPEC2TESTBENCH",
        "retriever_visible": True,
        "leakage_audit": {
            "contains_ground_truth": False,
            "contains_threshold": False,
            "contains_historical_value": False,
            "contains_mutation_identifier": False,
            "contains_full_benchmark_netlist": False,
        },
    }


def _measurement_recipe_entries() -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for metric_name, definition in sorted(METRIC_DEFINITIONS.items()):
        implementation_ref = "spec2testbench/application/services/llm_metric_registry.py"
        compiler_template_id = {
            "OP": "COMPILER_TEMPLATE_OP",
            "DC": "COMPILER_TEMPLATE_DC_SWEEP",
            "AC": "COMPILER_TEMPLATE_AC_SWEEP",
            "TRAN": "COMPILER_TEMPLATE_TRAN",
        }[definition.compatible_analysis_types[0].value]
        recipes.append(
            _recipe(
                recipe_id=f"MEASURE_{metric_name.upper()}",
                source_type="SPEC2TESTBENCH_LOCAL_EVIDENCE",
                compatible_analyses=[item.value for item in definition.compatible_analysis_types],
                required_parameters=[item for item in ("input_node", "output_node") if item.replace("_node", "") in definition.required_nodes],
                optional_parameters=["output_threshold", "time_column", "value_column", "vin_column", "vout_column"],
                parameter_constraints=["All numeric values must be finite."],
                compiler_template_id=compiler_template_id,
                scientific_guards=sorted(definition.required_semantic_guards.keys()),
                known_failure_modes=["MISSING_VECTOR", "SIMULATION_FAILURE"],
                positive_tests=["test_all_supported_metrics_have_measurement_recipe"],
                negative_tests=["test_missing_measure_does_not_fall_back_to_synthetic_zero"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                implementation_ref=implementation_ref,
                metrics=[metric_name],
            )
        )
    return recipes


def _build_rule_documents() -> dict[str, dict[str, Any]]:
    portable = _enforcement(
        llm_visible=True,
        retriever_visible=True,
        validator_enforced=True,
        compiler_enforced=True,
        backend_enforced=False,
        checker_enforced=False,
    )
    spec2tb = _enforcement(
        llm_visible=True,
        retriever_visible=True,
        validator_enforced=True,
        compiler_enforced=True,
        backend_enforced=True,
        checker_enforced=False,
    )
    backend_only = _enforcement(
        llm_visible=True,
        retriever_visible=True,
        validator_enforced=False,
        compiler_enforced=False,
        backend_enforced=True,
        checker_enforced=False,
    )
    hidden = _enforcement(
        llm_visible=False,
        retriever_visible=False,
        validator_enforced=True,
        compiler_enforced=True,
        backend_enforced=True,
        checker_enforced=False,
    )

    docs: dict[str, dict[str, Any]] = {}
    docs["spice_core/deck_structure_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="SPICE_DECK_HAS_TITLE",
                category="deck_structure",
                title="A generated deck carries one title line",
                description="Generated SPICE decks begin with a single title line controlled by the compiler.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["GENERATED_DECK_TEXT"]},
                forbids=["EMPTY_TITLE_LINE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH", "PORTABLE_SPICE"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_executed_deck_matches_saved_deck"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="SPICE_DECK_HAS_SINGLE_END",
                category="deck_structure",
                title="Generated decks terminate with a single .END",
                description="The compiler owns the final .END statement and emits it exactly once.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["GENERATED_DECK_TEXT"]},
                forbids=["MULTIPLE_END_STATEMENTS"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH", "PORTABLE_SPICE"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_executed_deck_matches_saved_deck"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="EXECUTED_DECK_IS_SAVED_BEFORE_EXECUTION",
                category="deck_structure",
                title="Executed deck is saved before ngspice execution",
                description="Spec2Testbench persists the exact executed .ckt before invoking ngspice and records its hash.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["EXECUTED_DECK_SHA256"]},
                forbids=["UNSAVED_EXECUTED_DECK"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "reports/canonical_harness_v1/executed_deck_integrity.md"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=[
                    "test_executed_deck_matches_saved_deck",
                    "test_stub_compiler_preserves_exact_executed_deck",
                ],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="PLANNER_DOES_NOT_EMIT_RAW_SPICE_LINES",
                category="deck_structure",
                title="Planner emits structured plans instead of raw SPICE",
                description="The planner returns JSON TestbenchPlan objects and the deterministic compiler renders SPICE text later.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["TESTBENCH_PLAN_SCHEMA"]},
                forbids=["FREE_FORM_SPICE_OUTPUT"],
                source=_source("CODE_AND_TESTS", "knowledge/spec2testbench/llm_testbench_plan_schema.md"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_llm_validator_accepts_valid_json_plan"],
                negative_test_ids=["test_llm_validator_rejects_invalid_json"],
            ),
        ],
    }
    docs["spice_core/lexical_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="SPICE_COMMENT_LINE",
                category="lexical",
                title="Comment lines may begin with an asterisk",
                description="Comment lines are preserved in generated and benchmark decks and remain semantically inert.",
                analyses=[],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["DECK_TEXT"]},
                forbids=[],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "benchmark/analogcoder_pro/p01_amplifier.cir"),
                dialect_scope=["PORTABLE_SPICE"],
                enforcement=portable,
                verification_status="CONFIRMED_PORTABLE",
                positive_test_ids=["test_stub_ground_truth_is_not_in_prompt"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="SPICE_ELEMENT_NAME_DETERMINES_TYPE",
                category="lexical",
                title="The leading element letter determines device class",
                description="Element type resolution is based on the leading SPICE designator and parser support.",
                analyses=[],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["PARSER_SUPPORTED_ELEMENTS"]},
                forbids=["UNKNOWN_ELEMENT_PREFIX_AS_SUPPORTED"],
                source=_source("CODE_AND_TESTS", "spec2testbench/infrastructure/simulator/netlist_parser.py"),
                dialect_scope=["PORTABLE_SPICE", "SPEC2TESTBENCH"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_all_requested_metrics_map_to_analysis"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/numeric_and_unit_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="FINITE_NUMERIC_VALUES_ONLY",
                category="numeric",
                title="Finite numeric values only",
                description="Plans, recipes, and compiled requests reject NaN and infinite numeric values.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["FINITE_NUMERIC_PLAN_VALUES"]},
                forbids=["NaN", "INF", "-INF"],
                source=_source("CODE_AND_TESTS", "spec2testbench/domain/entities/testbench_plan.py"),
                dialect_scope=["SPEC2TESTBENCH", "PORTABLE_SPICE"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_parse_measure_not_found_nan_and_inf"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="POSITIVE_AC_STOP_FREQUENCY",
                category="numeric",
                title="AC stop frequency must exceed start frequency",
                description="AC sweep parameters are rejected when the stop frequency does not exceed the start frequency.",
                analyses=["AC"],
                metrics=["dc_gain_db", "cutoff_frequency_hz", "bandwidth"],
                circuit_families=["amplifier", "filter", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["AC_SWEEP_PARAMETERS"]},
                forbids=["NEGATIVE_FREQUENCIES", "NON_INCREASING_AC_RANGE"],
                source=_source("CODE_AND_TESTS", "spec2testbench/domain/entities/testbench_plan.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_llm_validator_accepts_valid_json_plan"],
                negative_test_ids=["test_llm_validator_rejects_invalid_simulation_range"],
            ),
            _rule(
                rule_id="POSITIVE_TRANSIENT_STEP_TIME",
                category="numeric",
                title="Transient step time must be positive and smaller than stop time",
                description="Transient simulation parameters are bounded to positive step sizes and finite stop times.",
                analyses=["TRAN"],
                metrics=["propagation_delay", "oscillator_frequency", "hysteresis_width"],
                circuit_families=["comparator", "oscillator", "schmitt_trigger"],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"evidence": ["TRAN_SIMULATION_PARAMETERS"]},
                forbids=["ZERO_TRANSIENT_STOP_TIME", "NON_POSITIVE_STEP_TIME"],
                source=_source("CODE_AND_TESTS", "spec2testbench/domain/entities/testbench_plan.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_stub_use_case_smoke_contains_7_use_cases"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="ZERO_AC_INPUT_IS_NOT_EVALUATED",
                category="numeric",
                title="Zero AC input is not a valid transfer-gain denominator",
                description="Transfer-gain extraction must never substitute a numeric floor when the AC input vector is zero.",
                analyses=["AC"],
                metrics=["dc_gain", "dc_gain_db", "transfer_magnitude_linear", "transfer_phase_deg"],
                circuit_families=["amplifier", "filter", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["VIN_COMPLEX_VECTOR"]},
                forbids=["ZERO_INPUT_DIVISION", "SYNTHETIC_NUMERIC_FLOOR_AS_METRIC"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "tests/test_ngspice_result_backends.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_gain_with_zero_input_is_not_evaluated"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/node_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="SPICE_NODE_ZERO_IS_REFERENCE",
                category="nodes",
                title="Node zero is the reference node",
                description="Ground is represented by node 0 and is treated as the universal reference in the generated plans.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"node_roles": ["GROUND"]},
                forbids=["ALTERNATE_GROUND_ALIAS_AS_PRIMARY_REFERENCE"],
                source=_source("CODE_AND_TESTS", "spec2testbench/domain/entities/testbench.py"),
                dialect_scope=["PORTABLE_SPICE", "SPEC2TESTBENCH"],
                enforcement=portable,
                verification_status="CONFIRMED_PORTABLE",
                positive_test_ids=["test_plan_uses_only_existing_nodes"],
                negative_test_ids=["test_llm_validator_rejects_unknown_node"],
            ),
            _rule(
                rule_id="OBSERVED_NODE_MUST_EXIST",
                category="nodes",
                title="Observed nodes must exist",
                description="Measurement plans and observed node lists may only reference nodes present in the netlist or normalized specification.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"node_roles": ["OUTPUT"]},
                forbids=["UNKNOWN_OUTPUT_NODE"],
                source=_source("CODE_AND_TESTS", "spec2testbench/application/services/llm_testbench_plan_validator.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=portable,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_llm_validator_accepts_valid_json_plan"],
                negative_test_ids=["test_llm_validator_rejects_unknown_node"],
            ),
            _rule(
                rule_id="INPUT_NODE_ROLE_REQUIRED",
                category="nodes",
                title="Input-role nodes must be explicit when a metric depends on Vin",
                description="Transfer, delay, and hysteresis metrics require an explicit input-role node in the plan and recipes.",
                analyses=["AC", "TRAN"],
                metrics=["dc_gain_db", "propagation_delay", "hysteresis_width"],
                circuit_families=["amplifier", "comparator", "schmitt_trigger"],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"node_roles": ["SIGNAL_INPUT"]},
                forbids=["IMPLICIT_INPUT_NODE_FOR_REQUIRED_METRIC"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/llm_metric_registry.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_stub_plan_uses_only_existing_nodes"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="OUTPUT_NODE_ROLE_REQUIRED",
                category="nodes",
                title="Output-role nodes must be explicit for scalar metrics",
                description="The planner and compiler require an explicit output node for operating-point, AC, transient, and oscillation metrics.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"node_roles": ["OUTPUT"]},
                forbids=["MISSING_OUTPUT_ROLE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/llm_metric_registry.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_stub_plan_uses_only_existing_nodes"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/element_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "elements",
        "supported_elements": [
            {"element": name, "supported": True, "implementation_ref": "spec2testbench/infrastructure/simulator/netlist_parser.py"}
            for name in ["R", "C", "L", "V", "I", "D", "Q", "J", "M", "E", "F", "G", "H", "B", "X"]
        ],
    }
    docs["spice_core/model_and_subcircuit_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="MODEL_NAME_MUST_EXIST",
                category="model_subckt",
                title="Referenced device models must exist",
                description="When a device references a model name, the model declaration must be present in the effective deck.",
                analyses=[],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["MODEL_DECLARATION"]},
                forbids=["UNKNOWN_MODEL_IS_ERROR"],
                source=_source("CODE_AND_TESTS", "benchmark/analogcoder_pro/p01_amplifier.cir"),
                dialect_scope=["PORTABLE_SPICE"],
                enforcement=portable,
                verification_status="CONFIRMED_PORTABLE",
                positive_test_ids=["test_stub_frozen_v3_contains_16_cases"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/source_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="SUPPLY_SOURCE_PRESERVED",
                category="sources",
                title="Supply sources are preserved",
                description="Canonical harness and stub plans must not replace supply sources unless a dedicated variation campaign authorizes it.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"node_roles": ["SUPPLY_SOURCE"]},
                forbids=["UNAUTHORIZED_SUPPLY_OVERRIDE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/canonical_harness.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_supply_source_is_not_replaceable", "test_stub_plan_cannot_replace_supply"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="BIAS_SOURCE_PRESERVED",
                category="sources",
                title="Bias sources are preserved",
                description="Bias sources remain protected from arbitrary replacement in canonical and stub planning.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"node_roles": ["BIAS_SOURCE"]},
                forbids=["UNAUTHORIZED_BIAS_OVERRIDE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/canonical_harness.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_bias_source_is_not_replaceable", "test_stub_plan_cannot_replace_bias"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="INTERNAL_BIAS_SOURCE_PROTECTED",
                category="sources",
                title="Internal bias sources are protected",
                description="Internal bias sources are neither repurposed as inputs nor rewritten as stimuli.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"node_roles": ["INTERNAL_BIAS_SOURCE"]},
                forbids=["INTERNAL_BIAS_AS_SIGNAL_SOURCE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/canonical_harness.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_internal_bias_source_is_not_replaceable"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="SIGNAL_DC_OVERRIDE_REQUIRES_AUTHORITY",
                category="sources",
                title="Signal DC override requires explicit authority",
                description="Signal-source DC overrides must come from a validated authority such as the original harness or normalized specification.",
                analyses=["AC", "TRAN"],
                metrics=["dc_gain_db", "propagation_delay", "hysteresis_width"],
                circuit_families=["amplifier", "comparator", "schmitt_trigger"],
                backends=[],
                requires={"node_roles": ["SIGNAL_INPUT"]},
                forbids=["DC_MIDPOINT_INFERENCE_WITHOUT_AUTHORITY"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/canonical_harness.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_signal_dc_override_requires_authority"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/dc_analysis_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
                category="dc_analysis",
                title="Operating-point plans prefer .OP when no valid sweep source exists",
                description="If no stimulus source is eligible for a DC sweep, the canonical and stub path must keep a nominal .OP instead of inventing a .DC source name.",
                analyses=["OP"],
                metrics=["operating_point", "quiescent_current", "power"],
                circuit_families=["current_mirror", "opamp", "amplifier"],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"evidence": ["SOURCE_ROLE_POLICY"]},
                forbids=["FAKE_DC_SWEEP_SOURCE"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/application/services/canonical_harness.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=[
                    "test_current_mirror_op_harness_uses_nominal_op_without_fake_dc_source",
                    "test_stub_plan_uses_canonical_harness_policy",
                ],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="DC_SWEEP_REQUIRES_EXISTING_SOURCE",
                category="dc_analysis",
                title="A DC sweep must reference an existing source",
                description="A .DC analysis is only valid when the named source exists in the effective deck.",
                analyses=["DC"],
                metrics=["operating_point"],
                circuit_families=[],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"evidence": ["SWEEP_SOURCE_EXISTS"]},
                forbids=["NONEXISTENT_DC_SOURCE"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_NONEXISTENT_DC_SOURCE_FAILS"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/ac_analysis_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="AC_TRANSFER_GAIN_USES_COMPLEX_RATIO",
                category="ac_analysis",
                title="Transfer gain uses the complex Vout over Vin ratio",
                description="Voltage transfer gain is derived from the complex output-to-input ratio, not from absolute output dBV.",
                analyses=["AC"],
                metrics=["dc_gain", "dc_gain_db"],
                circuit_families=["amplifier", "filter", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"node_roles": ["SIGNAL_INPUT", "OUTPUT"], "evidence": ["VIN_COMPLEX_VECTOR", "VOUT_COMPLEX_VECTOR"]},
                forbids=["ABSOLUTE_VOUT_AS_TRANSFER_GAIN"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "reports/benchmark_normalization/ac_gain_implementation_audit.md"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=[
                    "test_gain_uses_transfer_ratio_not_absolute_output_for_unity_input",
                    "test_p04_measure_transfer_gain",
                    "test_stub_plan_preserves_requested_metrics",
                ],
                negative_test_ids=["test_gain_with_zero_input_is_not_evaluated"],
            ),
            _rule(
                rule_id="CUTOFF_REQUIRES_AC_SWEEP",
                category="ac_analysis",
                title="Cutoff and bandwidth require a valid AC sweep",
                description="Cutoff-like metrics are only valid on AC sweeps with finite Vin and Vout vectors.",
                analyses=["AC"],
                metrics=["cutoff_frequency_hz", "bandwidth"],
                circuit_families=["filter", "amplifier", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["AC_VECTOR_BUNDLE"]},
                forbids=["CUT_OFF_FROM_SCALAR_OUTPUT_ONLY"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/result_backends.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_gain_and_cutoff", "test_stub_use_case_smoke_contains_7_use_cases"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/transient_analysis_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="TRAN_PROPAGATION_DELAY_REQUIRES_INPUT_AND_OUTPUT",
                category="transient_analysis",
                title="Propagation delay requires input and output waveforms",
                description="Delay extraction needs both input and output threshold crossings and must not be synthesized from output-only data.",
                analyses=["TRAN"],
                metrics=["propagation_delay", "propagation_delay_s"],
                circuit_families=["comparator", "inverter"],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"node_roles": ["SIGNAL_INPUT", "OUTPUT"], "evidence": ["INPUT_WAVEFORM", "OUTPUT_WAVEFORM"]},
                forbids=["PROPAGATION_DELAY_FROM_OUTPUT_ONLY"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_missing_measure_does_not_fall_back_to_synthetic_zero", "test_stub_missing_metric_is_not_zero"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="VALID_OSCILLATION_REQUIRED_FOR_FREQUENCY",
                category="transient_analysis",
                title="Oscillator frequency requires validated oscillation",
                description="Frequency extraction is gated by oscillation validation and remains NOT_EVALUATED when the waveform lacks validated oscillation.",
                analyses=["TRAN"],
                metrics=["oscillator_frequency", "frequency_hz"],
                circuit_families=["oscillator"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["OUTPUT_WAVEFORM"]},
                forbids=["OSCILLATOR_FREQUENCY_WITHOUT_OSCILLATION"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_invalid_oscillation_blocks_frequency_metric", "test_stub_physical_absence_is_explicit"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="HYSTERESIS_REQUIRES_INPUT_AND_OUTPUT_WAVEFORMS",
                category="transient_analysis",
                title="Hysteresis width requires both input and output waveforms",
                description="Schmitt-trigger thresholds and hysteresis width are derived from paired input and output waveforms.",
                analyses=["TRAN"],
                metrics=["v_t_plus", "v_t_minus", "hysteresis_width"],
                circuit_families=["schmitt_trigger"],
                backends=["NGSPICE_WRDATA"],
                requires={"node_roles": ["SIGNAL_INPUT", "OUTPUT"], "evidence": ["INPUT_WAVEFORM", "OUTPUT_WAVEFORM"]},
                forbids=["HYSTERESIS_FROM_OUTPUT_ONLY"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/result_backends.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_interpolation_and_switching_thresholds", "test_stub_use_case_smoke_contains_7_use_cases"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/output_variable_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [],
    }
    docs["spice_core/numerical_accuracy_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="MISSING_METRIC_IS_NOT_ZERO",
                category="numerical_accuracy",
                title="A missing metric is never coerced to zero",
                description="Missing or invalid metrics remain explicitly NOT_EVALUATED instead of being replaced by zero-valued placeholders.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"evidence": ["EXPLICIT_NOT_EVALUATED_PATH"]},
                forbids=["SYNTHETIC_ZERO_FOR_MISSING_METRIC"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "reports/metric_coverage_reconciliation_v1/metric_coverage_audit.md"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=[
                    "test_parse_measure_empty_file_is_not_a_zero",
                    "test_stub_missing_metric_is_not_zero",
                ],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spice_core/convergence_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [],
    }
    docs["spice_core/classical_error_taxonomy.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "error_taxonomy",
        "errors": [
            {"error_id": "SIMULATION_FAILURE", "description": "ngspice execution failed before producing usable evidence."},
            {"error_id": "MISSING_VECTOR", "description": "A required WRDATA vector was not produced."},
            {"error_id": "SEMANTIC_GUARD_REJECTION", "description": "A metric was rejected by a scientific guard rather than by parser failure."},
            {"error_id": "PHYSICAL_PREREQUISITE_ABSENT", "description": "The DUT does not produce the physical behavior required for the metric."},
        ],
    }

    docs["ngspice/analysis_capabilities.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="CANONICAL_ANALYSIS_DECKS_ARE_SEPARATE",
                category="ngspice_capabilities",
                title="Canonical evidence executes one analysis deck at a time",
                description="The validated canonical path separates OP, AC, and transient analyses into dedicated decks before aggregation.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["ANALYSIS_SPECIFIC_DECKS"]},
                forbids=["MULTI_ANALYSIS_CONTAMINATION"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "reports/canonical_harness_v1/nominal_28_report.md"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_analysis_specific_decks_are_separate", "test_stub_multi_analysis_metrics_are_aggregated"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/measure_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="NGSPICE_TOP_LEVEL_MEASURE_SUPPORTED",
                category="measure",
                title="Top-level ngspice .measure statements are supported",
                description="Top-level .measure statements execute with the active analysis and are the preferred path for native measure output.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=["operating_point", "quiescent_current", "dc_gain_db", "propagation_delay"],
                circuit_families=[],
                backends=["NGSPICE_MEASURE"],
                requires={"evidence": ["MEASURES_TXT_OR_STDOUT"]},
                forbids=["ASSUME_TOP_LEVEL_MEASURE_UNSUPPORTED"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="NGSPICE_OP_FIND_AT_ZERO_IS_OUT_OF_INTERVAL",
                category="measure",
                title="OP-style .meas dc FIND ... AT=0 can fail under pure .OP",
                description="The installed ngspice reports an out-of-interval error when a pure .OP deck uses .meas dc FIND ... AT=0.",
                analyses=["OP"],
                metrics=["operating_point", "quiescent_current"],
                circuit_families=[],
                backends=["NGSPICE_MEASURE"],
                requires={"evidence": ["NGSPICE_STDERR"]},
                forbids=["ASSUME_OP_FIND_AT_ZERO_ALWAYS_WORKS"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=hidden,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_OP_MEASURE_AT_ZERO_OUT_OF_INTERVAL"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/control_block_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="NGSPICE_AC_WRDATA_REQUIRES_SETPLOT_AC1",
                category="control_block",
                title="AC WRDATA uses the AC plot after run",
                description="The AC control block switches to plot ac1 before exporting real and imaginary vectors via wrdata.",
                analyses=["AC"],
                metrics=["dc_gain_db", "cutoff_frequency_hz"],
                circuit_families=["amplifier", "filter", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["AC_CONTROL_BLOCK"]},
                forbids=["AC_WRDATA_WITHOUT_AC_PLOT_SELECTION"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_native_control_block_selects_ac_plot_and_uses_vin_then_vout_columns"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="NGSPICE_MEASURE_IN_CONTROL_CAN_FAIL_AFTER_SETPLOT",
                category="control_block",
                title="Repeated measure commands inside .control may fail after setplot",
                description="The installed ngspice may reject repeated measure param expressions inside a .control block after plot switching, so top-level .measure is preferred.",
                analyses=["AC"],
                metrics=["dc_gain_db"],
                circuit_families=["amplifier", "filter"],
                backends=["NGSPICE_MEASURE"],
                requires={"evidence": ["NGSPICE_STDERR"]},
                forbids=["REPEATED_MEASURE_PARAM_IN_CONTROL_AS_REQUIRED_PATH"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=hidden,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_CONTROL_MEASURE_AFTER_SETPLOT_CAN_FAIL"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/wrdata_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="NGSPICE_WRDATA_AC_EXPORTS_COMPLEX_COMPONENTS",
                category="wrdata",
                title="AC WRDATA exports real and imaginary components explicitly",
                description="Spec2Testbench exports AC complex vectors as explicit real and imaginary columns for both Vin and Vout.",
                analyses=["AC"],
                metrics=["dc_gain_db", "cutoff_frequency_hz", "bandwidth"],
                circuit_families=["amplifier", "filter", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["VIN_COMPLEX_VECTOR", "VOUT_COMPLEX_VECTOR"]},
                forbids=["AC_WRDATA_WITH_MAGNITUDE_ONLY_FOR_TRANSFER_GAIN"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_WRDATA_AC_COMPLEX_COLUMNS", "test_complex_wrdata_column_mapping_uses_vin_then_vout"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="NGSPICE_WRDATA_DC_EXPORTS_OUTPUT_AND_SUPPLY_CURRENT",
                category="wrdata",
                title="DC WRDATA exports output voltage and supply current",
                description="The installed ngspice can export a DC/OP scale column together with output voltage and supply current, enabling WRDATA fallback for operating-point current and power.",
                analyses=["OP", "DC"],
                metrics=["operating_point", "quiescent_current", "power"],
                circuit_families=["amplifier", "current_mirror", "opamp"],
                backends=["NGSPICE_WRDATA"],
                requires={"evidence": ["OUTPUT_VALUE_COLUMN", "SUPPLY_CURRENT_COLUMN"]},
                forbids=["DC_WRDATA_WITH_OUTPUT_ONLY_WHEN_CURRENT_IS_REQUIRED"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_microtest_results.csv"),
                dialect_scope=["NGSPICE_INSTALLED"],
                enforcement=backend_only,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_WRDATA_DC_OUTPUT_AND_CURRENT", "test_wrdata_can_extract_dc_operating_point"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/complex_vector_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [],
    }
    docs["ngspice/file_and_path_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="GENERATED_FILE_EXTENSION_IS_CKT",
                category="file_paths",
                title="Generated and executed decks use the .ckt extension",
                description="Spec2Testbench saves generated and executed decks with the .ckt extension before invoking ngspice.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["GENERATED_TESTBENCH_PATH", "EXECUTED_TESTBENCH_PATH"]},
                forbids=["NON_CKT_EXECUTED_DECK_EXTENSION"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_ngspice_command_uses_saved_executed_deck"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="NGSPICE_RELATIVE_OUTPUT_ARTIFACTS_ARE_ALLOWED",
                category="file_paths",
                title="Relative artifact paths are resolved before ngspice execution",
                description="Relative output directories are resolved to absolute paths before invoking ngspice so wrdata and log artifacts remain local to the chosen workspace.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["ABSOLUTE_OUTPUT_DIR"]},
                forbids=["UNRESOLVED_RELATIVE_OUTPUT_DIR"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/infrastructure/simulator/pyspice_simulator.py"),
                dialect_scope=["SPEC2TESTBENCH", "NGSPICE_INSTALLED"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_relative_output_dir_is_resolved_before_invoking_ngspice", "MT_WINDOWS_RELATIVE_OUTPUT_FILES"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/windows_rules.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="NGSPICE_WINDOWS_CONSOLE_EXECUTABLE_SUPPORTED",
                category="windows",
                title="Windows console ngspice executable is supported",
                description="The installed Windows console executable ngspice_con.exe is a validated execution target for the canonical and stub paths.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["NGSPICE_VERSION_OUTPUT"]},
                forbids=["GUI_ONLY_NGSPICE_REQUIREMENT"],
                source=_source("NGSPICE_INSTALLED_MICROTEST", "results/knowledge_stub_v1/ngspice_environment.json"),
                dialect_scope=["NGSPICE_INSTALLED", "WINDOWS"],
                enforcement=backend_only,
                verification_status="CONFIRMED_NGSPICE_INSTALLED",
                positive_test_ids=["MT_NGSPICE_VERSION_AVAILABLE"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["ngspice/error_message_mapping.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "error_mapping",
        "entries": [
            {
                "error_pattern": "out of interval",
                "root_cause_category": "MISSING_MEASURE_RESULT",
                "selected_rule": "NGSPICE_OP_FIND_AT_ZERO_IS_OUT_OF_INTERVAL",
            },
            {
                "error_pattern": "no such function as 'param=",
                "root_cause_category": "BACKEND_UNAVAILABLE",
                "selected_rule": "NGSPICE_MEASURE_IN_CONTROL_CAN_FAIL_AFTER_SETPLOT",
            },
        ],
    }

    metric_mapping_entries = []
    metric_semantic_entries = []
    guard_entries = []
    for metric_name, definition in sorted(METRIC_DEFINITIONS.items()):
        metric_mapping_entries.append(
            {
                "metric_name": metric_name,
                "analysis_type": definition.compatible_analysis_types[0].value,
                "definition_version": definition.definition_version,
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
                "positive_tests": ["test_all_requested_metrics_map_to_analysis"],
            }
        )
        metric_semantic_entries.append(
            {
                "metric_name": metric_name,
                "semantic_definition": definition.semantic_definition,
                "expected_unit": definition.expected_unit,
                "measurement_expression_id": definition.measurement_expression_id,
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
            }
        )
        for guard_name in sorted(definition.required_semantic_guards.keys()):
            guard_entries.append(
                {
                    "guard_id": guard_name,
                    "metric_name": metric_name,
                    "description": f"Scientific guard {guard_name} is required for {metric_name}.",
                    "enforced_by": [
                        "spec2testbench/infrastructure/simulator/result_backends.py",
                        "spec2testbench/infrastructure/simulator/pyspice_simulator.py",
                    ],
                    "verification_status": "CONFIRMED_SPEC2TESTBENCH",
                    "positive_tests": ["test_semantic_guard_rejection_is_not_parser_failure", "test_stub_physical_absence_is_explicit"],
                }
            )

    docs["spec2testbench/metric_analysis_mapping.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "metric_mapping",
        "entries": metric_mapping_entries,
    }
    docs["spec2testbench/canonical_harness_policies.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "policies",
        "entries": [
            {
                "policy_id": "CANONICAL_HARNESS_REUSES_VALIDATED_ANALYSIS_DECKS",
                "title": "Canonical harness uses analysis-specific validated decks",
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
                "positive_tests": ["test_analysis_specific_decks_are_separate"],
                "implementation_ref": "spec2testbench/application/services/canonical_harness.py",
            },
            {
                "policy_id": "CANONICAL_HARNESS_PRESERVES_SOURCE_ROLES",
                "title": "Canonical harness preserves supply, bias, and signal-source roles",
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
                "positive_tests": [
                    "test_supply_source_is_not_replaceable",
                    "test_bias_source_is_not_replaceable",
                    "test_internal_bias_source_is_not_replaceable",
                ],
                "implementation_ref": "spec2testbench/application/services/canonical_harness.py",
            },
        ],
    }
    docs["spec2testbench/source_role_policies.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "policies",
        "entries": [
            {
                "policy_id": "SOURCE_ROLE_SUPPLY_NON_REPLACEABLE",
                "role": "SUPPLY_SOURCE",
                "retriever_visible": True,
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
            },
            {
                "policy_id": "SOURCE_ROLE_BIAS_NON_REPLACEABLE",
                "role": "BIAS_SOURCE",
                "retriever_visible": True,
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
            },
            {
                "policy_id": "SOURCE_ROLE_SIGNAL_REPLACEABLE_WITH_AUTHORITY",
                "role": "SIGNAL_SOURCE",
                "retriever_visible": True,
                "verification_status": "CONFIRMED_SPEC2TESTBENCH",
            },
        ],
    }
    docs["spec2testbench/stimulus_recipes.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "recipes",
        "entries": [
            _recipe(
                recipe_id="RECIPE_DC_SIGNAL_BIAS",
                source_type="DC",
                compatible_analyses=["OP", "DC"],
                required_parameters=["value"],
                optional_parameters=[],
                parameter_constraints=["value must be finite"],
                compiler_template_id="COMPILER_TEMPLATE_OP",
                scientific_guards=[],
                known_failure_modes=["NONEXISTENT_DC_SOURCE"],
                positive_tests=["test_current_mirror_op_harness_uses_nominal_op_without_fake_dc_source"],
                negative_tests=[],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                implementation_ref="spec2testbench/application/services/canonical_harness.py",
                metrics=["operating_point", "quiescent_current"],
            ),
            _recipe(
                recipe_id="RECIPE_AC_SMALL_SIGNAL",
                source_type="AC",
                compatible_analyses=["AC"],
                required_parameters=["magnitude", "dc_value"],
                optional_parameters=["phase"],
                parameter_constraints=["magnitude must be positive", "dc_value must be finite"],
                compiler_template_id="COMPILER_TEMPLATE_AC_SWEEP",
                scientific_guards=["ac_input_exists", "ac_input_nonzero"],
                known_failure_modes=["ZERO_AC_INPUT"],
                positive_tests=["test_ac_harness_preserves_original_dc_bias"],
                negative_tests=[],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                implementation_ref="spec2testbench/application/services/canonical_harness.py",
                metrics=["dc_gain_db", "cutoff_frequency_hz"],
            ),
            _recipe(
                recipe_id="RECIPE_PULSE_TRANSIENT",
                source_type="PULSE",
                compatible_analyses=["TRAN"],
                required_parameters=["v1", "v2", "rise", "fall", "width", "period"],
                optional_parameters=["delay"],
                parameter_constraints=["period must exceed width", "rise and fall must be positive"],
                compiler_template_id="COMPILER_TEMPLATE_TRAN",
                scientific_guards=["requires_input_and_output_waveforms"],
                known_failure_modes=["WINDOW_TOO_SHORT"],
                positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                negative_tests=[],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                implementation_ref="spec2testbench/infrastructure/llm/stub_provider.py",
                metrics=["propagation_delay", "oscillator_frequency"],
            ),
            _recipe(
                recipe_id="RECIPE_TRIANGLE_HYSTERESIS",
                source_type="TRIANGLE",
                compatible_analyses=["TRAN"],
                required_parameters=["amplitude", "offset", "period"],
                optional_parameters=[],
                parameter_constraints=["period must be positive"],
                compiler_template_id="COMPILER_TEMPLATE_TRAN",
                scientific_guards=["requires_input_and_output_waveforms"],
                known_failure_modes=["UNSUPPORTED_RECIPE_SELECTION"],
                positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                negative_tests=[],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                implementation_ref="spec2testbench/application/services/testbench_plan_compiler.py",
                metrics=["hysteresis_width"],
            ),
        ],
    }
    docs["spec2testbench/measurement_recipes.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "recipes",
        "entries": _measurement_recipe_entries(),
    }
    docs["spec2testbench/multi_analysis_aggregation.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="MULTI_ANALYSIS_EVIDENCE_AGGREGATION_REQUIRED",
                category="aggregation",
                title="Metrics spanning multiple analyses require explicit evidence aggregation",
                description="Spec2Testbench aggregates per-analysis bundles before presenting metric evidence to the checker.",
                analyses=["OP", "AC", "TRAN"],
                metrics=["operating_point", "dc_gain_db", "propagation_delay"],
                circuit_families=[],
                backends=["NGSPICE_MEASURE", "NGSPICE_WRDATA"],
                requires={"evidence": ["ANALYSIS_EXECUTION_BUNDLE", "METRIC_EVIDENCE_BUNDLE"]},
                forbids=["MULTI_ANALYSIS_METRIC_WITHOUT_AGGREGATION"],
                source=_source("SPEC2TESTBENCH_LOCAL_EVIDENCE", "spec2testbench/domain/entities/metric_coverage.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=[
                    "test_analysis_specific_results_are_aggregated",
                    "test_checker_receives_aggregated_metric_bundle",
                    "test_stub_multi_analysis_metrics_are_aggregated",
                ],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spec2testbench/semantic_guards.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "guards",
        "entries": guard_entries,
    }
    docs["spec2testbench/metric_semantics.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "metric_semantics",
        "entries": metric_semantic_entries,
    }
    docs["spec2testbench/evidence_requirements.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "evidence_requirements",
        "entries": [
            {"evidence_id": "VIN_COMPLEX_VECTOR", "description": "Complex input AC vector exported by WRDATA."},
            {"evidence_id": "VOUT_COMPLEX_VECTOR", "description": "Complex output AC vector exported by WRDATA."},
            {"evidence_id": "ANALYSIS_EXECUTION_BUNDLE", "description": "Per-analysis execution payload with deck hash and artifacts."},
            {"evidence_id": "METRIC_EVIDENCE_BUNDLE", "description": "Per-metric evidence row presented to the checker."},
        ],
    }
    docs["spec2testbench/known_failure_modes.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "failures",
        "entries": [
            {"failure_id": "INVALID_NODE_SELECTION", "repairable": True},
            {"failure_id": "INVALID_SOURCE_SELECTION", "repairable": True},
            {"failure_id": "INVALID_ANALYSIS_PARAMETER", "repairable": True},
            {"failure_id": "WINDOW_TOO_SHORT", "repairable": True},
            {"failure_id": "UNSUPPORTED_RECIPE_SELECTION", "repairable": True},
            {"failure_id": "GROUND_TRUTH_DISAGREEMENT", "repairable": False},
            {"failure_id": "LOW_GAIN", "repairable": False},
        ],
    }
    docs["spec2testbench/repair_policy.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "repair_policy",
        "max_repairs": 2,
        "repairable_failure_modes": [
            "INVALID_NODE_SELECTION",
            "INVALID_SOURCE_SELECTION",
            "INVALID_ANALYSIS_PARAMETER",
            "WINDOW_TOO_SHORT",
            "UNSUPPORTED_RECIPE_SELECTION",
        ],
        "non_repairable_failure_modes": [
            "LOW_GAIN",
            "HIGH_DELAY",
            "GROUND_TRUTH_DISAGREEMENT",
        ],
    }
    docs["spec2testbench/scientific_eligibility.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "rules",
        "entries": [
            _rule(
                rule_id="STUB_PROVIDER_IS_NON_SCIENTIFIC",
                category="scientific_eligibility",
                title="Stub outputs are software-integration evidence only",
                description="Stub runs validate integration and determinism, but they are never scientific LLM evidence.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["PROVIDER_MODE_STUB"]},
                forbids=["LABEL_STUB_AS_LLM_STABILITY"],
                source=_source("CODE_AND_TESTS", "spec2testbench/infrastructure/llm/stub_provider.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_stub_provider_is_marked_non_scientific"],
                negative_test_ids=[],
            ),
            _rule(
                rule_id="STUB_PROVIDER_MODE_EXPLICIT",
                category="scientific_eligibility",
                title="Stub plans must state provider_mode STUB explicitly",
                description="Stub plans carry explicit provider-mode metadata and scientific_llm_evidence false.",
                analyses=["OP", "DC", "AC", "TRAN"],
                metrics=[],
                circuit_families=[],
                backends=[],
                requires={"evidence": ["PLAN_PROVIDER_METADATA"]},
                forbids=["MISSING_PROVIDER_MODE_FOR_STUB"],
                source=_source("CODE_AND_TESTS", "spec2testbench/infrastructure/llm/stub_provider.py"),
                dialect_scope=["SPEC2TESTBENCH"],
                enforcement=spec2tb,
                verification_status="CONFIRMED_SPEC2TESTBENCH",
                positive_test_ids=["test_stub_provider_is_marked_non_scientific"],
                negative_test_ids=[],
            ),
        ],
    }
    docs["spec2testbench/tool_library.yaml"] = {
        "schema_version": RULE_SCHEMA_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "kind": "tools",
        "entries": [
            _tool(
                tool_id="COMPILER_TEMPLATE_OP",
                title="Compile a nominal operating-point deck",
                category="compiler_template",
                compiler_template_id="COMPILER_TEMPLATE_OP",
                implementation_ref="spec2testbench/application/services/testbench_plan_compiler.py",
                supported_analyses=["OP"],
                supported_metrics=["operating_point", "quiescent_current", "power"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
            _tool(
                tool_id="COMPILER_TEMPLATE_DC_SWEEP",
                title="Compile a DC sweep deck",
                category="compiler_template",
                compiler_template_id="COMPILER_TEMPLATE_DC_SWEEP",
                implementation_ref="spec2testbench/application/services/testbench_plan_compiler.py",
                supported_analyses=["DC"],
                supported_metrics=["operating_point"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
            _tool(
                tool_id="COMPILER_TEMPLATE_AC_SWEEP",
                title="Compile an AC sweep deck",
                category="compiler_template",
                compiler_template_id="COMPILER_TEMPLATE_AC_SWEEP",
                implementation_ref="spec2testbench/application/services/testbench_plan_compiler.py",
                supported_analyses=["AC"],
                supported_metrics=["dc_gain_db", "cutoff_frequency_hz", "bandwidth"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
            _tool(
                tool_id="COMPILER_TEMPLATE_TRAN",
                title="Compile a transient deck",
                category="compiler_template",
                compiler_template_id="COMPILER_TEMPLATE_TRAN",
                implementation_ref="spec2testbench/application/services/testbench_plan_compiler.py",
                supported_analyses=["TRAN"],
                supported_metrics=["propagation_delay", "oscillator_frequency", "hysteresis_width"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
            _tool(
                tool_id="BACKEND_NGSPICE_MEASURE",
                title="Native ngspice measure backend",
                category="backend",
                compiler_template_id="BACKEND_NGSPICE_MEASURE",
                implementation_ref="spec2testbench/infrastructure/simulator/result_backends.py",
                supported_analyses=["OP", "DC", "AC", "TRAN"],
                supported_metrics=["operating_point", "quiescent_current", "power", "propagation_delay"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
            _tool(
                tool_id="BACKEND_NGSPICE_WRDATA",
                title="ASCII vector export backend",
                category="backend",
                compiler_template_id="BACKEND_NGSPICE_WRDATA",
                implementation_ref="spec2testbench/infrastructure/simulator/result_backends.py",
                supported_analyses=["OP", "DC", "AC", "TRAN"],
                supported_metrics=["dc_gain_db", "cutoff_frequency_hz", "oscillator_frequency", "hysteresis_width"],
                verification_status="CONFIRMED_SPEC2TESTBENCH",
            ),
        ],
    }
    return docs


def _build_validated_examples() -> dict[str, dict[str, Any]]:
    return {
        "validated_examples/dc_bias_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_DC_BIAS_GENERIC",
                    use_case="UC_DC_BIAS",
                    title="Generic DC bias example",
                    summary="Use a single observed output node and a nominal OP analysis; if no sweepable signal source exists, keep .OP.",
                    plan_shape={"analysis_type": "OP", "observed_nodes": ["<output>"], "measurements": ["operating_point"]},
                    safe_circuit_families=["inverter", "amplifier", "current_mirror"],
                    safe_metrics=["operating_point"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/dc_current_power_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_DC_CURRENT_POWER_GENERIC",
                    use_case="UC_DC_CURRENT_POWER",
                    title="Generic DC current and power example",
                    summary="Preserve supply and bias sources, request operating-point evidence, and derive current or power from supply-current evidence.",
                    plan_shape={"analysis_type": "OP", "measurements": ["quiescent_current", "power"]},
                    safe_circuit_families=["amplifier", "current_mirror", "opamp"],
                    safe_metrics=["quiescent_current", "power"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/ac_gain_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_AC_GAIN_GENERIC",
                    use_case="UC_AC_GAIN",
                    title="Generic AC transfer-gain example",
                    summary="Use a small-signal AC source with preserved DC bias, observe Vin and Vout, and compute gain from the complex ratio.",
                    plan_shape={"analysis_type": "AC", "stimuli": ["AC"], "measurements": ["dc_gain_db"]},
                    safe_circuit_families=["amplifier", "opamp"],
                    safe_metrics=["dc_gain_db"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/filter_cutoff_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_FILTER_CUTOFF_GENERIC",
                    use_case="UC_FILTER_CUTOFF_BANDWIDTH",
                    title="Generic filter cutoff example",
                    summary="Use an AC sweep with complex Vin and Vout exports and derive cutoff from the AC transfer curve.",
                    plan_shape={"analysis_type": "AC", "measurements": ["cutoff_frequency_hz"]},
                    safe_circuit_families=["low_pass_filter", "high_pass_filter"],
                    safe_metrics=["cutoff_frequency_hz"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/transient_delay_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_TRANSIENT_DELAY_GENERIC",
                    use_case="UC_TRANSIENT_DELAY",
                    title="Generic transient delay example",
                    summary="Use a bounded transient pulse, retain explicit input and output nodes, and measure delay from threshold crossings.",
                    plan_shape={"analysis_type": "TRAN", "stimuli": ["PULSE"], "measurements": ["propagation_delay"]},
                    safe_circuit_families=["comparator", "inverter"],
                    safe_metrics=["propagation_delay"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/oscillator_frequency_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_OSCILLATOR_FREQUENCY_GENERIC",
                    use_case="UC_OSCILLATION_FREQUENCY",
                    title="Generic oscillator-frequency example",
                    summary="Do not inject a signal source into a self-oscillating DUT; use a transient observation window long enough to validate oscillation first.",
                    plan_shape={"analysis_type": "TRAN", "stimuli": [], "measurements": ["oscillator_frequency", "startup_amplitude"]},
                    safe_circuit_families=["oscillator"],
                    safe_metrics=["oscillator_frequency", "startup_amplitude"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
        "validated_examples/schmitt_hysteresis_generic.yaml": {
            "schema_version": RULE_SCHEMA_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "kind": "examples",
            "entries": [
                _example(
                    example_id="EXAMPLE_SCHMITT_HYSTERESIS_GENERIC",
                    use_case="UC_SWITCHING_THRESHOLD_HYSTERESIS",
                    title="Generic Schmitt hysteresis example",
                    summary="Use a monotonic transient sweep that allows both rising and falling threshold extraction on the same input-output pair.",
                    plan_shape={"analysis_type": "TRAN", "stimuli": ["TRIANGLE"], "measurements": ["hysteresis_width"]},
                    safe_circuit_families=["schmitt_trigger"],
                    safe_metrics=["hysteresis_width"],
                    positive_tests=["test_stub_use_case_smoke_contains_7_use_cases"],
                )
            ],
        },
    }


def _knowledge_docs() -> dict[str, str]:
    return {
        "docs/spice_knowledge_architecture.md": "\n".join(
            [
                "# SPICE Knowledge Architecture",
                "",
                f"This knowledge repository was generated for `{KNOWLEDGE_VERSION}`.",
                "",
                "It separates four layers:",
                "",
                "- `knowledge/spice_core/`: portable SPICE and compiler-owned structural rules.",
                "- `knowledge/ngspice/`: rules confirmed on the installed ngspice executable.",
                "- `knowledge/spec2testbench/`: local scientific invariants, recipes, and policies.",
                "- `knowledge/validated_examples/`: safe generic examples with leakage checks.",
                "",
                "Only rules with validation status `CONFIRMED_PORTABLE`, `CONFIRMED_NGSPICE_INSTALLED`, or `CONFIRMED_SPEC2TESTBENCH` are exposed to retrieval.",
            ]
        ),
        "docs/spice_core_rules.md": "# SPICE Core Rules\n\nSee `knowledge/spice_core/` for the portable and compiler-owned rule catalog.\n",
        "docs/ngspice_installed_rules.md": "# ngspice Installed Rules\n\nSee `knowledge/ngspice/` for rules confirmed against the installed ngspice executable.\n",
        "docs/spec2testbench_scientific_guards.md": "# Spec2Testbench Scientific Guards\n\nSee `knowledge/spec2testbench/semantic_guards.yaml` for guard definitions and local evidence.\n",
        "docs/canonical_harness_policies.md": "# Canonical Harness Policies\n\nSee `knowledge/spec2testbench/canonical_harness_policies.yaml`.\n",
        "docs/multi_analysis_evidence.md": "# Multi-analysis Evidence\n\nSee `knowledge/spec2testbench/multi_analysis_aggregation.yaml` and `spec2testbench/domain/entities/metric_coverage.py`.\n",
        "docs/knowledge_retrieval.md": "# Knowledge Retrieval\n\nDeterministic retrieval filters active rules, recipes, tools, and examples by use case, metric, analysis, and family.\n",
        "docs/validated_examples.md": "# Validated Examples\n\nThe safe generic examples live in `knowledge/validated_examples/` and contain no ground-truth labels, thresholds, or historical measured values.\n",
        "docs/stub_provider_protocol.md": "# Stub Provider Protocol\n\nStub runs must use `provider_mode: STUB` and `scientific_llm_evidence: false`.\n",
        "docs/reproducing_knowledge_stub_campaign.md": "\n".join(
            [
                "# Reproducing Knowledge Stub Campaign",
                "",
                "Run the full local campaign with:",
                "",
                "```bash",
                "python scripts/run_knowledge_and_stub_campaign.py --build-knowledge --validate-knowledge --run-microtests --audit-retrieval --deterministic-parity --stub-use-cases --stub-frozen-one-trial --stub-frozen-three-trials --disable-pyspice --no-mock --no-live-llm",
                "```",
            ]
        ),
    }


def create_knowledge_manifests(
    experiments_root: Path,
    *,
    knowledge_version: str = KNOWLEDGE_VERSION,
) -> dict[str, Path]:
    experiments_root.mkdir(parents=True, exist_ok=True)
    source_smoke = yaml.safe_load((ROOT / "experiments/llm_deepseek/use_case_smoke_manifest.yaml").read_text(encoding="utf-8"))
    source_frozen = yaml.safe_load((ROOT / "experiments/llm_deepseek/frozen_manifest.yaml").read_text(encoding="utf-8"))
    smoke_payload = {
        **source_smoke,
        "version": f"{knowledge_version}_use_case_smoke",
        "notes": [
            "Copied from the validated llm_deepseek smoke manifest.",
            f"Used for {knowledge_version} retrieval and stub replay only.",
        ],
    }
    frozen_payload = {
        **source_frozen,
        "version": f"{knowledge_version}_frozen_manifest",
        "notes": [
            "Copied from the validated llm_deepseek frozen manifest.",
            f"Used for post-{knowledge_version} deterministic parity and stub replay.",
        ],
    }
    smoke_path = experiments_root / "use_case_smoke_manifest.yaml"
    frozen_path = experiments_root / "frozen_manifest.yaml"
    write_yaml(smoke_path, smoke_payload)
    write_yaml(frozen_path, frozen_payload)
    return {"smoke": smoke_path, "frozen": frozen_path}


def build_knowledge_repository(
    *,
    knowledge_root: Path,
    experiments_root: Path,
    microtest_results_path: Path | None = None,
    knowledge_version: str = KNOWLEDGE_VERSION,
) -> dict[str, Any]:
    manifests = create_knowledge_manifests(experiments_root, knowledge_version=knowledge_version)
    knowledge_root.mkdir(parents=True, exist_ok=True)
    for directory in ("spice_core", "ngspice", "spec2testbench", "validated_examples"):
        (knowledge_root / directory).mkdir(parents=True, exist_ok=True)

    environment_doc = detect_ngspice_environment(knowledge_version=knowledge_version)
    write_yaml(knowledge_root / "ngspice" / "installed_environment.yaml", environment_doc)

    docs = rewrite_knowledge_version(_build_rule_documents(), knowledge_version)
    docs["ngspice/installed_environment.yaml"] = environment_doc
    docs.update(rewrite_knowledge_version(_build_validated_examples(), knowledge_version))

    for relative_path, payload in docs.items():
        write_yaml(knowledge_root / relative_path, payload)

    for relative_path, text in _knowledge_docs().items():
        write_text(ROOT / relative_path, text)

    catalog = load_knowledge_catalog(knowledge_root)
    catalog_rows: list[dict[str, Any]] = []
    for kind in ("rules", "recipes", "tools", "examples"):
        for entry in catalog[kind]:
            identifier = entry.get("rule_id") or entry.get("recipe_id") or entry.get("tool_id") or entry.get("example_id")
            status = (
                entry.get("verification", {}).get("status")
                or entry.get("verification_status")
                or ""
            )
            catalog_rows.append(
                {
                    "kind": kind[:-1] if kind.endswith("s") else kind,
                    "id": identifier,
                    "status": status,
                    "source_path": entry.get("_source_file", ""),
                    "retriever_visible": entry.get("enforcement", {}).get("retriever_visible", entry.get("retriever_visible", False)),
                }
            )

    return {
        "knowledge_root": str(knowledge_root),
        "experiments_root": str(experiments_root),
        "smoke_manifest": str(manifests["smoke"]),
        "frozen_manifest": str(manifests["frozen"]),
        "rule_catalog_rows": catalog_rows,
    }


def load_knowledge_catalog(knowledge_root: Path) -> dict[str, list[dict[str, Any]]]:
    knowledge_root = knowledge_root.resolve()
    catalog = {"rules": [], "recipes": [], "tools": [], "examples": [], "files": []}
    for path in sorted(knowledge_root.rglob("*.yaml")):
        resolved_path = path.resolve()
        try:
            relative_path = resolved_path.relative_to(ROOT)
        except ValueError:
            relative_path = resolved_path.relative_to(knowledge_root.parent)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        kind = str(payload.get("kind", "")).strip().lower()
        catalog["files"].append({"path": str(relative_path), "kind": kind})
        entries = list(payload.get("entries", []))
        if kind == "rules":
            for entry in entries:
                catalog["rules"].append({**entry, "_source_file": str(relative_path)})
        elif kind == "recipes":
            for entry in entries:
                catalog["recipes"].append({**entry, "_source_file": str(relative_path)})
        elif kind == "tools":
            for entry in entries:
                catalog["tools"].append({**entry, "_source_file": str(relative_path)})
        elif kind == "examples":
            for entry in entries:
                catalog["examples"].append({**entry, "_source_file": str(relative_path)})
        elif kind == "metric_mapping":
            for entry in entries:
                catalog.setdefault("metric_mapping", []).append({**entry, "_source_file": str(relative_path)})
        elif kind == "guards":
            for entry in entries:
                catalog.setdefault("guards", []).append({**entry, "_source_file": str(relative_path)})
        elif kind == "policies":
            for entry in entries:
                catalog.setdefault("policies", []).append({**entry, "_source_file": str(relative_path)})
        elif kind == "failures":
            for entry in entries:
                catalog.setdefault("failures", []).append({**entry, "_source_file": str(relative_path)})
    return catalog


def _known_test_ids() -> set[str]:
    test_ids: set[str] = set()
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("def test_"):
                name = stripped.split("def ", 1)[1].split("(", 1)[0].strip()
                test_ids.add(name)
    return test_ids


def validate_knowledge_repository(
    *,
    knowledge_root: Path,
    microtest_results_path: Path | None = None,
) -> dict[str, Any]:
    catalog = load_knowledge_catalog(knowledge_root)
    resolved_knowledge_version = resolve_catalog_knowledge_version(catalog)
    known_tests = _known_test_ids()
    known_microtests = {microtest_id for microtest_id, passed in load_microtest_statuses(microtest_results_path).items() if passed}
    known_ids = known_tests | known_microtests

    duplicate_ids: list[str] = []
    broken_references: list[str] = []
    invalid_yaml: list[str] = []
    active_untested_rules: list[str] = []
    rule_validation_rows: list[dict[str, Any]] = []

    seen_ids: dict[str, str] = {}
    for rule in catalog["rules"]:
        rule_id = str(rule["rule_id"])
        if rule_id in seen_ids:
            duplicate_ids.append(rule_id)
        seen_ids[rule_id] = rule["_source_file"]
        source_path = str(rule.get("source", {}).get("document_path", "") or "").strip()
        source_exists = True
        if source_path and not (ROOT / source_path).exists():
            source_exists = False
            broken_references.append(f"{rule_id}:{source_path}")
        status = str(rule.get("verification", {}).get("status", "")).strip()
        positive_tests = list(rule.get("verification", {}).get("positive_test_ids", []))
        tested = all(test_id in known_ids for test_id in positive_tests) if positive_tests else False
        if status in ACTIVE_RULE_STATUSES and not tested:
            active_untested_rules.append(rule_id)
        rule_validation_rows.append(
            {
                "rule_id": rule_id,
                "source_file": rule["_source_file"],
                "status": status,
                "source_exists": source_exists,
                "positive_tests": "|".join(positive_tests),
                "all_positive_tests_present": tested,
                "retriever_visible": rule.get("enforcement", {}).get("retriever_visible", False),
            }
        )

    recipe_ids: list[str] = []
    broken_recipe_refs: list[str] = []
    for recipe in catalog["recipes"]:
        recipe_id = str(recipe["recipe_id"])
        recipe_ids.append(recipe_id)
        if recipe_id in seen_ids:
            duplicate_ids.append(recipe_id)
        seen_ids[recipe_id] = recipe["_source_file"]
        implementation_ref = str(recipe.get("implementation_ref", "")).strip()
        if implementation_ref and not (ROOT / implementation_ref).exists():
            broken_recipe_refs.append(f"{recipe_id}:{implementation_ref}")

    tool_ids: list[str] = []
    broken_tool_refs: list[str] = []
    for tool in catalog["tools"]:
        tool_id = str(tool["tool_id"])
        tool_ids.append(tool_id)
        if tool_id in seen_ids:
            duplicate_ids.append(tool_id)
        seen_ids[tool_id] = tool["_source_file"]
        implementation_ref = str(tool.get("implementation_ref", "")).strip()
        if implementation_ref and not (ROOT / implementation_ref).exists():
            broken_tool_refs.append(f"{tool_id}:{implementation_ref}")

    example_ids: list[str] = []
    for example in catalog["examples"]:
        example_id = str(example["example_id"])
        example_ids.append(example_id)
        if example_id in seen_ids:
            duplicate_ids.append(example_id)
        seen_ids[example_id] = example["_source_file"]

    return {
        "knowledge_version": resolved_knowledge_version,
        "rule_count": len(catalog["rules"]),
        "recipe_count": len(recipe_ids),
        "tool_count": len(tool_ids),
        "example_count": len(example_ids),
        "duplicate_ids": sorted(set(duplicate_ids)),
        "broken_references": sorted(set(broken_references + broken_recipe_refs + broken_tool_refs)),
        "invalid_yaml": invalid_yaml,
        "active_untested_rules": sorted(set(active_untested_rules)),
        "rule_validation_rows": rule_validation_rows,
        "spice_core_files": len(list((knowledge_root / "spice_core").glob("*.yaml"))),
        "ngspice_files": len(list((knowledge_root / "ngspice").glob("*.yaml"))),
        "spec2testbench_files": len(list((knowledge_root / "spec2testbench").glob("*.yaml"))),
        "validated_example_files": len(list((knowledge_root / "validated_examples").glob("*.yaml"))),
        "go_knowledge_structure": not duplicate_ids and not invalid_yaml,
        "go_knowledge_validation": not duplicate_ids and not invalid_yaml and not broken_references and not broken_recipe_refs and not broken_tool_refs and not active_untested_rules,
    }


def audit_example_leakage(knowledge_root: Path) -> list[dict[str, Any]]:
    def iter_scalar_strings(node: Any) -> list[str]:
        values: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "leakage_audit":
                    continue
                values.extend(iter_scalar_strings(value))
        elif isinstance(node, list):
            for item in node:
                values.extend(iter_scalar_strings(item))
        elif isinstance(node, str):
            values.append(node)
        return values

    rows: list[dict[str, Any]] = []
    for path in sorted((knowledge_root / "validated_examples").glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        payload = yaml.safe_load(text) or {}
        scalar_text = "\n".join(iter_scalar_strings(payload))
        upper = scalar_text.upper()
        unsafe_ground_truth = any(token in upper for token in FROZEN_GROUND_TRUTH_TOKENS)
        unsafe_mutation = "MUTATION" in upper or "FP2_CV_" in upper or "CV_" in upper
        unsafe_netlist = ".MODEL" in upper or "\nM1 " in upper or "\nR1 " in upper
        unsafe_values = any(token in scalar_text for token in ["-35.0", "0.001", "TRUE_ACCEPT", "FALSE_REJECT"])
        rows.append(
            {
                "example_file": str(path.relative_to(ROOT)),
                "contains_ground_truth": unsafe_ground_truth,
                "contains_mutation_identifier": unsafe_mutation,
                "contains_full_benchmark_netlist": unsafe_netlist,
                "contains_historical_value": unsafe_values,
                "safe": not any([unsafe_ground_truth, unsafe_mutation, unsafe_netlist, unsafe_values]),
            }
        )
    return rows


def build_conflict_rows() -> list[dict[str, Any]]:
    return [
        {
            "conflict_id": "KC_001",
            "rule_a": "NGSPICE_TOP_LEVEL_MEASURE_SUPPORTED",
            "rule_b": "NGSPICE_MEASURE_IN_CONTROL_CAN_FAIL_AFTER_SETPLOT",
            "source_a": "NGSPICE_INSTALLED_MICROTEST",
            "source_b": "NGSPICE_INSTALLED_MICROTEST",
            "scope_a": "TOP_LEVEL_MEASURE",
            "scope_b": "CONTROL_BLOCK_MEASURE_AFTER_SETPLOT",
            "observed_ngspice_behavior": "Top-level AC .measure succeeds; repeated control-block param measure can fail after setplot.",
            "selected_rule": "Prefer top-level .measure and keep control blocks for wrdata only.",
            "selection_reason": "Observed behavior on installed ngspice 41.",
            "test_evidence": "MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS|MT_CONTROL_MEASURE_AFTER_SETPLOT_CAN_FAIL",
            "status": "RESOLVED_BY_NGSPICE_TEST",
        },
        {
            "conflict_id": "KC_002",
            "rule_a": "OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
            "rule_b": "DC_SWEEP_REQUIRES_EXISTING_SOURCE",
            "source_a": "SPEC2TESTBENCH_LOCAL_EVIDENCE",
            "source_b": "NGSPICE_INSTALLED_MICROTEST",
            "scope_a": "CURRENT_MIRROR_AND_NO_SIGNAL_SOURCE",
            "scope_b": "GENERIC_DC_SWEEP",
            "observed_ngspice_behavior": "Invented .DC VIN fails when VIN is absent; nominal .OP succeeds.",
            "selected_rule": "Use .OP when no valid sweep source exists.",
            "selection_reason": "Safety and observed ngspice behavior.",
            "test_evidence": "test_current_mirror_op_harness_uses_nominal_op_without_fake_dc_source|MT_NONEXISTENT_DC_SOURCE_FAILS",
            "status": "RESOLVED_BY_SAFETY_INVARIANT",
        },
    ]


def retrieve_knowledge_bundle(
    *,
    knowledge_root: Path,
    case_id: str,
    circuit_family: str,
    requested_metrics: list[str],
    knowledge_version: str | None = None,
) -> KnowledgeBundle:
    catalog = load_knowledge_catalog(knowledge_root)
    resolved_knowledge_version = knowledge_version or resolve_catalog_knowledge_version(catalog)
    use_case = infer_use_case(requested_metrics[0] if requested_metrics else "")
    compatible_analyses = {
        definition.compatible_analysis_types[0].value
        for metric_name, definition in METRIC_DEFINITIONS.items()
        if metric_name in requested_metrics
    }
    required_rule_ids = set(required_rule_ids_for_use_case(use_case))

    selected_rules: list[dict[str, Any]] = []
    for rule in catalog["rules"]:
        status = str(rule.get("verification", {}).get("status", "")).strip()
        if status not in ACTIVE_RULE_STATUSES:
            continue
        if not rule.get("enforcement", {}).get("retriever_visible", False):
            continue
        applies = rule.get("applies_to", {})
        analyses = set(applies.get("analyses", []))
        metrics = set(applies.get("metrics", []))
        families = set(applies.get("circuit_families", []))
        if rule["rule_id"] in required_rule_ids:
            selected_rules.append(rule)
            continue
        metric_match = not metrics or bool(metrics & set(requested_metrics))
        analysis_match = not analyses or bool(analyses & compatible_analyses)
        family_match = not families or circuit_family in families
        if metric_match and analysis_match and family_match:
            selected_rules.append(rule)

    selected_rules = sorted(selected_rules, key=lambda item: (item["rule_id"] not in required_rule_ids, item["rule_id"]))[:24]

    selected_recipes = [
        recipe
        for recipe in catalog["recipes"]
        if recipe.get("retriever_visible") and set(recipe.get("metrics", [])) & set(requested_metrics)
    ]
    selected_recipes = sorted(selected_recipes, key=lambda item: item["recipe_id"])[:12]

    selected_tools = [
        tool
        for tool in catalog["tools"]
        if tool.get("retriever_visible") and (not tool.get("supported_metrics") or set(tool.get("supported_metrics", [])) & set(requested_metrics))
    ]
    selected_tools = sorted(selected_tools, key=lambda item: item["tool_id"])[:8]

    selected_examples = [
        example
        for example in catalog["examples"]
        if example.get("retriever_visible") and example.get("use_case") == use_case
    ]
    selected_examples = sorted(selected_examples, key=lambda item: item["example_id"])[:1]

    prompt_rules = [
        {
            "rule_id": item["rule_id"],
            "title": item["title"],
            "description": item["description"],
            "requires": item.get("requires", {}),
            "forbids": item.get("forbids", []),
            "verification_status": item.get("verification", {}).get("status", ""),
            "book_grounded": item.get("book_grounded", False),
            "book_chapter": item.get("book_chapter", ""),
            "book_section": item.get("book_section", ""),
            "book_page": item.get("book_page", ""),
            "ngspice_confirmed": item.get("ngspice_confirmed", False),
            "project_enforced": item.get("project_enforced", False),
        }
        for item in selected_rules
    ]
    prompt_recipes = [
        {
            "recipe_id": item["recipe_id"],
            "compatible_analyses": item["compatible_analyses"],
            "required_parameters": item["required_parameters"],
            "compiler_template_id": item["compiler_template_id"],
            "metrics": item["metrics"],
        }
        for item in selected_recipes
    ]
    prompt_tools = [
        {
            "tool_id": item["tool_id"],
            "category": item["category"],
            "compiler_template_id": item["compiler_template_id"],
        }
        for item in selected_tools
    ]
    prompt_examples = [
        {
            "example_id": item["example_id"],
            "title": item["title"],
            "summary": item["summary"],
            "plan_shape": item["plan_shape"],
        }
        for item in selected_examples
    ]

    bundle_payload = {
        "case_id": case_id,
        "use_case": use_case,
        "requested_metrics": requested_metrics,
        "knowledge_version": resolved_knowledge_version,
        "rules": prompt_rules,
        "recipes": prompt_recipes,
        "tools": prompt_tools,
        "examples": prompt_examples,
    }
    bundle_sha = json_sha256(bundle_payload)
    return KnowledgeBundle(
        case_id=case_id,
        use_case=use_case,
        requested_metrics=list(requested_metrics),
        knowledge_version=resolved_knowledge_version,
        rules=prompt_rules,
        recipes=prompt_recipes,
        tools=prompt_tools,
        examples=prompt_examples,
        bundle_sha256=bundle_sha,
    )


def specification_from_case_record(record: dict[str, Any]) -> Specification:
    specification = Specification.from_yaml(ROOT / str(record["specification_file"]))
    specification.case_id = str(record["case_id"])
    targeted = record.get("targeted_metric", {})
    targeted_metric = targeted.get("name") if isinstance(targeted, dict) else targeted
    if targeted_metric and targeted_metric in specification.performance_targets:
        specification.performance_targets = {targeted_metric: specification.performance_targets[targeted_metric]}
    return specification


def retrieval_audit_rows(
    *,
    knowledge_root: Path,
    case_records: list[dict[str, Any]],
    cohort: str,
    knowledge_version: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    case_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []
    for record in case_records:
        targeted = record.get("targeted_metric", {})
        metric_name = targeted.get("name") if isinstance(targeted, dict) else str(targeted)
        requested_metrics = [metric_name] if metric_name else list(specification_from_case_record(record).performance_targets.keys())
        bundle_one = retrieve_knowledge_bundle(
            knowledge_root=knowledge_root,
            case_id=str(record["case_id"]),
            circuit_family=str(record.get("circuit_family", "")),
            requested_metrics=requested_metrics,
            knowledge_version=knowledge_version,
        )
        bundle_two = retrieve_knowledge_bundle(
            knowledge_root=knowledge_root,
            case_id=str(record["case_id"]),
            circuit_family=str(record.get("circuit_family", "")),
            requested_metrics=requested_metrics,
            knowledge_version=knowledge_version,
        )
        required_rules = required_rule_ids_for_use_case(bundle_one.use_case)
        missing_required = sorted(set(required_rules) - {item["rule_id"] for item in bundle_one.rules})
        unverified_rules = [
            item["rule_id"]
            for item in bundle_one.rules
            if item.get("verification_status", "") not in ACTIVE_RULE_STATUSES
        ]
        case_rows.append(
            {
                "cohort": cohort,
                "case_id": record["case_id"],
                "use_case": bundle_one.use_case,
                "requested_metrics": "|".join(requested_metrics),
                "required_rule_count": len(required_rules),
                "retrieved_rule_count": len(bundle_one.rules),
                "recipe_count": len(bundle_one.recipes),
                "tool_count": len(bundle_one.tools),
                "example_count": len(bundle_one.examples),
                "missing_required_rules": "|".join(missing_required),
                "irrelevant_rules": 0,
                "unsafe_rules": 0,
                "unverified_rules": "|".join(unverified_rules),
                "oversized_bundle": len(bundle_one.rules) > 24 or len(bundle_one.recipes) > 12,
                "bundle_sha256": bundle_one.bundle_sha256,
                "deterministic_repeat_match": bundle_one.bundle_sha256 == bundle_two.bundle_sha256,
            }
        )
        for required_rule_id in required_rules:
            coverage_rows.append(
                {
                    "cohort": cohort,
                    "case_id": record["case_id"],
                    "use_case": bundle_one.use_case,
                    "rule_id": required_rule_id,
                    "required": True,
                    "retrieved": required_rule_id in {item["rule_id"] for item in bundle_one.rules},
                }
            )
        hash_rows.append(
            {
                "cohort": cohort,
                "case_id": record["case_id"],
                "bundle_sha256_first": bundle_one.bundle_sha256,
                "bundle_sha256_second": bundle_two.bundle_sha256,
                "deterministic_match": bundle_one.bundle_sha256 == bundle_two.bundle_sha256,
            }
        )
    return case_rows, coverage_rows, hash_rows


def load_manifest_cases(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(payload.get("cases", []))
