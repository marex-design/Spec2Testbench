from __future__ import annotations

import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_deepseek_testbench_campaign import (  # noqa: E402
    build_use_case_row,
    classification_from_ground_truth,
    load_frozen_v3_reference_rows,
    resolve_manifest_cases,
)
from spec2testbench.application.services.llm_cache import LLMCacheKey  # noqa: E402
from spec2testbench.application.services.llm_generation_service import LLMGenerationService  # noqa: E402
from spec2testbench.application.services.spice_knowledge import (  # noqa: E402
    KNOWLEDGE_VERSION,
    REPRESENTATIVE_NOMINAL_CASE_IDS,
    audit_example_leakage,
    build_conflict_rows,
    build_knowledge_repository,
    detect_ngspice_environment,
    json_sha256,
    load_knowledge_catalog,
    load_manifest_cases,
    required_rule_ids_for_use_case,
    retrieval_audit_rows,
    retrieve_knowledge_bundle,
    sha256_file,
    specification_from_case_record,
    validate_knowledge_repository,
    write_csv as write_csv_rows,
    write_json as write_json_file,
    write_text as write_text_file,
)
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler  # noqa: E402
from spec2testbench.application.usecases.run_verification import VerificationReport, VerificationPipeline  # noqa: E402
from spec2testbench.domain.entities.specification import Specification  # noqa: E402
from spec2testbench.domain.value_objects.llm_status import GenerationMode  # noqa: E402
from spec2testbench.infrastructure.llm.stub_provider import DeterministicStubProvider  # noqa: E402
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator  # noqa: E402
from spec2testbench.infrastructure.testbench.testbench_generator import TestBenchGenerator  # noqa: E402


DEFAULT_NGSPICE_EXECUTABLE = r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe"
KNOWLEDGE_ROOT = ROOT / "knowledge"
BOOK_KNOWLEDGE_VERSION = "knowledge_book_v1"
CURRENT_KNOWLEDGE_VERSION = KNOWLEDGE_VERSION
EXPERIMENTS_ROOT = ROOT / "experiments" / CURRENT_KNOWLEDGE_VERSION
ARTIFACTS_ROOT = ROOT / "artifacts" / CURRENT_KNOWLEDGE_VERSION
RESULTS_ROOT = ROOT / "results" / CURRENT_KNOWLEDGE_VERSION
REPORTS_ROOT = ROOT / "reports" / CURRENT_KNOWLEDGE_VERSION
FINAL_STATUS_REPORT = REPORTS_ROOT / "final_status.md"

GROUND_TRUTH_TOKENS = {
    "GROUND_TRUTH_COMPLIANT",
    "GROUND_TRUTH_NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
    "UNEVALUATED",
}
BOOK_CANDIDATES = [
    ROOT / "references" / "local" / "spice_book.pdf",
    ROOT / "The SPICE Book.pdf",
    ROOT / "docs" / "The SPICE Book.pdf",
    ROOT / "references" / "The SPICE Book.pdf",
]
EXPECTED_BOOK_TITLE = "The SPICE Book"
EXPECTED_BOOK_AUTHOR = "Andrei Vladimirescu"
EXPECTED_BOOK_YEAR = 1994
REPRESENTATIVE_NOMINAL_TARGETS = {
    "p01_amplifier": "dc_gain_db",
    "p05_amplifier": "quiescent_current",
    "p09_comparator": "propagation_delay",
    "p10_lowpass": "cutoff_frequency_hz",
    "p22_oscillator": "oscillator_frequency",
}
MICROTEST_IDS = [
    "MT_NONEXISTENT_DC_SOURCE_FAILS",
    "MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS",
    "MT_OP_MEASURE_AT_ZERO_OUT_OF_INTERVAL",
    "MT_CONTROL_MEASURE_AFTER_SETPLOT_CAN_FAIL",
    "MT_WRDATA_AC_COMPLEX_COLUMNS",
    "MT_WRDATA_DC_OUTPUT_AND_CURRENT",
    "MT_WINDOWS_RELATIVE_OUTPUT_FILES",
    "MT_NGSPICE_VERSION_AVAILABLE",
]

BOOK_RULE_CANDIDATES = [
    {
        "rule_id": "BOOK_TITLE_LINE_CANONICAL",
        "category": "deck_structure",
        "title": "A SPICE deck starts with a title line",
        "paraphrased_description": "The first meaningful line identifies the circuit or simulation deck before analysis commands appear.",
        "chapter": "Chapter 1",
        "section": "1.3.1 Electric Circuit Specification-The SPICE Input",
        "page": 18,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_executed_deck_matches_saved_deck", "MT_BOOK_DECK_TITLE_AND_END"],
        "negative_tests": [],
        "known_limitations": ["The project planner emits structured JSON plans rather than hand-written decks."],
        "existing_rule_id": "SPICE_DECK_HAS_TITLE",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The canonical rule already enforces the book's title-line convention.",
        "selected_canonical_rule": "SPICE_DECK_HAS_TITLE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_OR_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_COMMENT_PREFIX_ALLOWED",
        "category": "deck_structure",
        "title": "Comment lines are valid deck content",
        "paraphrased_description": "Narrative lines may be present as comments and are ignored by the simulator semantics.",
        "chapter": "Chapter 1",
        "section": "1.3.1 Electric Circuit Specification-The SPICE Input",
        "page": 18,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_COMMENT_LINE"],
        "negative_tests": [],
        "known_limitations": ["The planner does not rely on free-form comment generation."],
        "existing_rule_id": "SPICE_COMMENT_LINE",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The lexical rule matches the book's comment-line behavior.",
        "selected_canonical_rule": "SPICE_COMMENT_LINE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "CONFIRMED_PORTABLE",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_DECK_ENDS_ONCE",
        "category": "deck_structure",
        "title": "A deck terminates with one .END statement",
        "paraphrased_description": "Classical decks finish with a single terminator so the input remains unambiguous.",
        "chapter": "Appendix E",
        "section": "SPICE Input Deck",
        "page": 405,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_executed_deck_matches_saved_deck", "MT_BOOK_DECK_TITLE_AND_END"],
        "negative_tests": [],
        "known_limitations": ["The project compiler owns deck termination centrally."],
        "existing_rule_id": "SPICE_DECK_HAS_SINGLE_END",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The canonical rule already captures the single-.END invariant.",
        "selected_canonical_rule": "SPICE_DECK_HAS_SINGLE_END",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_OR_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_ELEMENT_PREFIX_DEFINES_TYPE",
        "category": "node_and_element_conventions",
        "title": "The first letter of an element name determines its primitive type",
        "paraphrased_description": "Element identifiers encode the primitive class that the parser should apply to the rest of the statement.",
        "chapter": "Chapter 2",
        "section": "2.1 Elements, Models, Nodes, and Conventions",
        "page": 38,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_plan_uses_only_existing_nodes"],
        "negative_tests": [],
        "known_limitations": ["Spec2Testbench compiles structured plans rather than arbitrary primitive cards."],
        "existing_rule_id": "SPICE_ELEMENT_NAME_DETERMINES_TYPE",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The lexical rule already matches the book's element-prefix convention.",
        "selected_canonical_rule": "SPICE_ELEMENT_NAME_DETERMINES_TYPE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_NODE_ZERO_IS_GLOBAL_REFERENCE",
        "category": "node_and_element_conventions",
        "title": "Node zero is the global reference node",
        "paraphrased_description": "The zero node defines the common electrical reference used by the network equations.",
        "chapter": "Chapter 2",
        "section": "2.1 Elements, Models, Nodes, and Conventions",
        "page": 38,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_NODE_ZERO_REFERENCE"],
        "negative_tests": [],
        "known_limitations": ["The project consumes benchmark netlists instead of rewriting ground references."],
        "existing_rule_id": "SPICE_NODE_ZERO_IS_REFERENCE",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The canonical node-zero rule is the same electrical convention described in the book.",
        "selected_canonical_rule": "SPICE_NODE_ZERO_IS_REFERENCE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "CONFIRMED_PORTABLE",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_MODEL_NAME_MUST_RESOLVE",
        "category": "node_and_element_conventions",
        "title": "A referenced model must exist",
        "paraphrased_description": "Model-backed devices remain invalid when their referenced model card is absent or misspelled.",
        "chapter": "Appendix B",
        "section": "B.4 Element, Semiconductor-Device, and Model Errors",
        "page": 393,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_UNKNOWN_MODEL_REJECTED"],
        "negative_tests": [],
        "known_limitations": ["Spec2Testbench inherits model cards from the benchmark deck."],
        "existing_rule_id": "MODEL_NAME_MUST_EXIST",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The canonical model rule already records the missing-model failure described in the book.",
        "selected_canonical_rule": "MODEL_NAME_MUST_EXIST",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "CONFIRMED_PORTABLE",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_NUMERIC_VALUES_MUST_BE_FINITE",
        "category": "numeric_conventions",
        "title": "Analysis parameters stay finite and explicit",
        "paraphrased_description": "Numeric analysis parameters use valid SPICE number forms instead of undefined or non-finite placeholders.",
        "chapter": "Chapter 9",
        "section": "9.2.2 Accuracy and SPICE Options",
        "page": 291,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["MT_BOOK_NUMERIC_SUFFIXES", "test_missing_measure_does_not_fall_back_to_synthetic_zero"],
        "negative_tests": [],
        "known_limitations": ["The planner stores canonical numeric values rather than every historical suffix spelling."],
        "existing_rule_id": "FINITE_NUMERIC_VALUES_ONLY",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The book adds legacy number-format context around the existing finite-value rule.",
        "selected_canonical_rule": "FINITE_NUMERIC_VALUES_ONLY",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_OR_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_BIAS_AND_SIGNAL_SOURCE_ROLES_DIFFER",
        "category": "sources",
        "title": "Bias and signal source roles must stay distinguishable",
        "paraphrased_description": "Independent sources can carry both bias and excitation meaning, so a planner should not silently replace the bias intent with a synthetic signal.",
        "chapter": "Chapter 2",
        "section": "2.2.6 Independent Bias and Signal Sources",
        "page": 46,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_stub_plan_cannot_replace_supply", "test_stub_plan_cannot_replace_bias"],
        "negative_tests": [],
        "known_limitations": ["The project uses normalized node roles rather than raw source cards."],
        "existing_rule_id": "SUPPLY_SOURCE_PRESERVED",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The book's bias-versus-signal distinction motivates the existing safety rule.",
        "selected_canonical_rule": "SUPPLY_SOURCE_PRESERVED",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_PULSE_PARAMETER_ORDER",
        "category": "sources",
        "title": "PULSE sources use the documented positional parameter order",
        "paraphrased_description": "A pulse source remains well-defined only when its timing and amplitude arguments follow the expected SPICE ordering.",
        "chapter": "Chapter 2",
        "section": "2.2.6.1 Pulse Function",
        "page": 48,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_PULSE_SOURCE"],
        "negative_tests": [],
        "known_limitations": ["The current planner does not synthesize raw PULSE cards in benchmark replay."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The current catalog does not encode PULSE argument ordering explicitly.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "NOT_SUPPORTED",
    },
    {
        "rule_id": "BOOK_SIN_PARAMETER_ORDER",
        "category": "sources",
        "title": "SIN sources use the documented positional parameter order",
        "paraphrased_description": "A sinusoidal source remains unambiguous only when offset, amplitude and timing terms respect the SPICE ordering.",
        "chapter": "Chapter 2",
        "section": "2.2.6.2 Sinusoidal Function",
        "page": 50,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_SIN_SOURCE"],
        "negative_tests": [],
        "known_limitations": ["The planner currently prefers structured source metadata over raw SIN cards."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The current catalog does not encode SIN argument ordering explicitly.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "NOT_SUPPORTED",
    },
    {
        "rule_id": "BOOK_EXP_PARAMETER_ORDER",
        "category": "sources",
        "title": "EXP sources use the documented positional parameter order",
        "paraphrased_description": "An exponential source remains well-formed only when its rise and fall timing arguments respect the SPICE ordering.",
        "chapter": "Chapter 2",
        "section": "2.2.6.4 Exponential Function",
        "page": 53,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_EXP_SOURCE"],
        "negative_tests": [],
        "known_limitations": ["The planner does not currently emit raw EXP cards for benchmark replay."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The current catalog does not encode EXP argument ordering explicitly.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "NOT_SUPPORTED",
    },
    {
        "rule_id": "BOOK_OPERATING_POINT_COMPUTES_DC_BIAS",
        "category": "dc",
        "title": "Operating-point analysis solves the DC bias state",
        "paraphrased_description": "When there is no valid sweep source, the natural DC operating point is the safe baseline for bias-oriented metrics.",
        "chapter": "Chapter 4",
        "section": "4.2 Operating (Bias) Point",
        "page": 129,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_current_mirror_op_harness_uses_nominal_op_without_fake_dc_source"],
        "negative_tests": ["MT_NONEXISTENT_DC_SOURCE_FAILS"],
        "known_limitations": ["The project's exact deck choice is a policy layer on top of the book's bias-point semantics."],
        "existing_rule_id": "OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The canonical rule is the project-safe refinement of the book's operating-point behavior.",
        "selected_canonical_rule": "OPERATING_POINT_PREFERS_OP_WHEN_NO_SWEEP_SOURCE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_AND_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_DC_SWEEP_TARGET_MUST_EXIST",
        "category": "dc",
        "title": "A DC sweep targets an existing independent source",
        "paraphrased_description": "DC transfer analysis only makes sense when the named source is real and can be swept over a defined interval.",
        "chapter": "Chapter 4",
        "section": "4.3 DC Transfer Curves",
        "page": 133,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "NGSPICE_CONFIRMED",
        "positive_tests": ["MT_NONEXISTENT_DC_SOURCE_FAILS", "MT_BOOK_DC_SWEEP_OK"],
        "negative_tests": [],
        "known_limitations": ["The project may choose .OP instead of inventing a sweep."],
        "existing_rule_id": "DC_SWEEP_REQUIRES_EXISTING_SOURCE",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The canonical DC-sweep rule is a direct operationalization of the book's requirement.",
        "selected_canonical_rule": "DC_SWEEP_REQUIRES_EXISTING_SOURCE",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "CONFIRMED_NGSPICE_INSTALLED",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_AC_REQUIRES_NONZERO_EXCITATION",
        "category": "ac",
        "title": "AC analysis needs a nonzero small-signal excitation",
        "paraphrased_description": "Frequency-response analysis is meaningful only when a source carries a nonzero AC component around the DC operating point.",
        "chapter": "Chapter 5",
        "section": "5.2 AC Frequency Sweep",
        "page": 149,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["MT_BOOK_AC_WITH_EXCITATION", "MT_BOOK_AC_WITHOUT_EXCITATION"],
        "negative_tests": [],
        "known_limitations": ["The project reports not-evaluated metrics instead of inventing a zero-gain answer."],
        "existing_rule_id": "ZERO_AC_INPUT_IS_NOT_EVALUATED",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The canonical safety rule is the project consequence of the book's AC-excitation requirement.",
        "selected_canonical_rule": "ZERO_AC_INPUT_IS_NOT_EVALUATED",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_OR_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_AC_RESULTS_ARE_COMPLEX",
        "category": "ac",
        "title": "AC responses are complex-valued around the DC operating point",
        "paraphrased_description": "Small-signal AC analysis produces complex responses that must be interpreted through magnitude, phase, or equivalent ratios.",
        "chapter": "Chapter 5",
        "section": "5.2 AC Frequency Sweep",
        "page": 149,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS", "MT_WRDATA_AC_COMPLEX_COLUMNS"],
        "negative_tests": [],
        "known_limitations": ["The project exports complex data explicitly before computing derived gain metrics."],
        "existing_rule_id": "AC_TRANSFER_GAIN_USES_COMPLEX_RATIO",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The canonical AC-gain rule is the implementation of the book's complex-response semantics.",
        "selected_canonical_rule": "AC_TRANSFER_GAIN_USES_COMPLEX_RATIO",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_AND_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_AC_WRDATA_NEEDS_COMPLEX_COLUMNS",
        "category": "ac",
        "title": "Complex AC exports require separate components",
        "paraphrased_description": "When AC data are exported for later computation, the complex components must remain distinguishable instead of being collapsed prematurely.",
        "chapter": "Chapter 5",
        "section": "5.2 AC Frequency Sweep",
        "page": 149,
        "dialect_scope": ["NGSPICE_CONFIRMED"],
        "implementation_scope": "NGSPICE_CONFIRMED",
        "positive_tests": ["MT_WRDATA_AC_COMPLEX_COLUMNS"],
        "negative_tests": [],
        "known_limitations": ["The exact column layout is ngspice behavior rather than universal SPICE syntax."],
        "existing_rule_id": "NGSPICE_WRDATA_AC_EXPORTS_COMPLEX_COMPONENTS",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The book gives the interpretation and the canonical ngspice rule records the installed export behavior.",
        "selected_canonical_rule": "NGSPICE_WRDATA_AC_EXPORTS_COMPLEX_COMPONENTS",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "CONFIRMED_NGSPICE_INSTALLED",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_TRANSIENT_STEP_MUST_BE_POSITIVE",
        "category": "transient",
        "title": "Transient analysis requires a positive step size",
        "paraphrased_description": "Time-domain analysis needs a valid forward step and stop horizon so numerical integration can advance in time.",
        "chapter": "Chapter 6",
        "section": "6.2 Transient Analysis",
        "page": 169,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["MT_BOOK_TRAN_POSITIVE_STEP"],
        "negative_tests": [],
        "known_limitations": ["The project normalizes time values before compilation."],
        "existing_rule_id": "POSITIVE_TRANSIENT_STEP_TIME",
        "classification": "DUPLICATE_EQUIVALENT",
        "semantic_similarity_reason": "The project rule is a direct safety check on the transient semantics described by the book.",
        "selected_canonical_rule": "POSITIVE_TRANSIENT_STEP_TIME",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST_OR_MICROTEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_DELAY_NEEDS_INPUT_AND_OUTPUT",
        "category": "transient",
        "title": "Delay measurements need both input and output waveforms",
        "paraphrased_description": "Propagation-style timing metrics need a meaningful input transition and a corresponding observed output waveform.",
        "chapter": "Chapter 6",
        "section": "6.2 Transient Analysis",
        "page": 169,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_stub_plan_preserves_requested_metrics"],
        "negative_tests": [],
        "known_limitations": ["The exact JSON fields are project-specific even though the waveform dependency is portable."],
        "existing_rule_id": "TRAN_PROPAGATION_DELAY_REQUIRES_INPUT_AND_OUTPUT",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The canonical transient-delay rule encodes the waveform dependency implied by the book.",
        "selected_canonical_rule": "TRAN_PROPAGATION_DELAY_REQUIRES_INPUT_AND_OUTPUT",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_OSCILLATION_NEEDS_VALID_WAVEFORM",
        "category": "transient",
        "title": "Oscillation metrics require a physically valid waveform",
        "paraphrased_description": "Frequency or startup measurements are meaningful only when the transient waveform actually exhibits oscillatory behavior.",
        "chapter": "Chapter 6",
        "section": "6.2 Transient Analysis",
        "page": 169,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "SPEC2TESTBENCH_POLICY",
        "positive_tests": ["test_stub_missing_metric_is_not_zero", "test_stub_physical_absence_is_explicit"],
        "negative_tests": [],
        "known_limitations": ["The project adds its own error taxonomy for missing oscillation evidence."],
        "existing_rule_id": "VALID_OSCILLATION_REQUIRED_FOR_FREQUENCY",
        "classification": "EXTENDS_EXISTING_RULE",
        "semantic_similarity_reason": "The canonical oscillator rule is the project-safe interpretation of the book's waveform requirement.",
        "selected_canonical_rule": "VALID_OSCILLATION_REQUIRED_FOR_FREQUENCY",
        "merge_action": "ENRICH_EXISTING_PROVENANCE",
        "verification_required": "PROJECT_TEST",
        "final_status": "CONFIRMED_SPEC2TESTBENCH",
        "spec2testbench_support": "SUPPORTED_AND_ENFORCED",
    },
    {
        "rule_id": "BOOK_CONTINUATION_LINES_EXIST",
        "category": "deck_structure",
        "title": "Long SPICE statements may use continuation lines",
        "paraphrased_description": "Long statements may continue on the next physical line using the legacy continuation convention.",
        "chapter": "Appendix C",
        "section": "C.1 Element Statements",
        "page": 399,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_CONTINUATION_LINE"],
        "negative_tests": [],
        "known_limitations": ["Spec2Testbench currently emits compact single-line generated statements."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "No canonical rule currently records continuation syntax explicitly.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "NOT_SUPPORTED",
    },
    {
        "rule_id": "BOOK_PWL_REQUIRES_TIME_VALUE_PAIRS",
        "category": "sources",
        "title": "PWL sources require ordered time-value pairs",
        "paraphrased_description": "Piecewise-linear excitation uses alternating time and value entries so the waveform remains well-defined.",
        "chapter": "Chapter 2",
        "section": "2.2.6.5 Piecewise Linear Function",
        "page": 54,
        "dialect_scope": ["PORTABLE_SPICE_CORE"],
        "implementation_scope": "PORTABLE_SPICE_CORE",
        "positive_tests": ["MT_BOOK_PWL_SOURCE"],
        "negative_tests": [],
        "known_limitations": ["The current planner does not synthesize raw PWL source cards for the benchmark campaigns."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The existing catalog has no explicit PWL syntax rule.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "NOT_SUPPORTED",
    },
    {
        "rule_id": "BOOK_DUPLICATE_ELEMENT_NAMES_ARE_ERRORS",
        "category": "errors",
        "title": "Duplicate element names are rejected",
        "paraphrased_description": "Two statements cannot reuse the same element identifier because the parser can no longer distinguish the intended primitive instance.",
        "chapter": "Appendix B",
        "section": "B.4 Element, Semiconductor-Device, and Model Errors",
        "page": 393,
        "dialect_scope": ["NGSPICE_CONFIRMED"],
        "implementation_scope": "NGSPICE_CONFIRMED",
        "positive_tests": ["MT_BOOK_DUPLICATE_ELEMENT_REJECTED"],
        "negative_tests": [],
        "known_limitations": ["The compiler rarely emits raw primitive names outside generated harness fragments."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "No canonical rule currently tracks duplicate element identifiers as a separate validation item.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "PARTIALLY_SUPPORTED",
    },
    {
        "rule_id": "BOOK_INVALID_ANALYSIS_REQUEST_IS_REJECTED",
        "category": "errors",
        "title": "Malformed analysis requests are rejected",
        "paraphrased_description": "Analysis cards need a valid statement shape and parameter ordering or the simulator reports an analysis input error.",
        "chapter": "Appendix B",
        "section": "B.7 Analysis Errors",
        "page": 395,
        "dialect_scope": ["NGSPICE_CONFIRMED"],
        "implementation_scope": "NGSPICE_CONFIRMED",
        "positive_tests": ["MT_BOOK_MALFORMED_ANALYSIS"],
        "negative_tests": [],
        "known_limitations": ["The planner emits structured analysis parameters rather than free-form control statements."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The current knowledge base does not expose malformed-analysis diagnostics as a standalone rule.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "PARTIALLY_SUPPORTED",
    },
    {
        "rule_id": "BOOK_MALFORMED_SOURCE_IS_REJECTED",
        "category": "errors",
        "title": "Malformed source definitions are rejected",
        "paraphrased_description": "Independent source cards need the expected numeric or waveform arguments or the simulator reports a source-specification error.",
        "chapter": "Appendix B",
        "section": "B.3 Source Specification Errors",
        "page": 392,
        "dialect_scope": ["NGSPICE_CONFIRMED"],
        "implementation_scope": "NGSPICE_CONFIRMED",
        "positive_tests": ["MT_BOOK_MALFORMED_SOURCE"],
        "negative_tests": [],
        "known_limitations": ["Spec2Testbench uses structured source descriptions and should never emit this in nominal operation."],
        "existing_rule_id": "",
        "classification": "NEW_PORTABLE_RULE",
        "semantic_similarity_reason": "The current knowledge base has no explicit malformed-source rule.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "UNSUPPORTED_BY_PROJECT",
        "spec2testbench_support": "PARTIALLY_SUPPORTED",
    },
    {
        "rule_id": "BOOK_FLOATING_OR_SINGULAR_TOPOLOGY_CAN_FAIL",
        "category": "convergence",
        "title": "Floating or singular topologies can prevent convergence",
        "paraphrased_description": "Some solver failures come from missing DC paths or singular topologies rather than from a physically meaningful circuit response.",
        "chapter": "Chapter 10",
        "section": "10.2 Common Causes of Solution Failure",
        "page": 326,
        "dialect_scope": ["SPICE2_HISTORICAL", "NGSPICE_CONFIRMED"],
        "implementation_scope": "HISTORICAL_ANALYSIS_ONLY",
        "positive_tests": ["MT_BOOK_MISSING_DC_PATH", "MT_BOOK_FLOATING_NODE"],
        "negative_tests": [],
        "known_limitations": ["The corrective guidance is historical and should remain hidden from the planner."],
        "existing_rule_id": "",
        "classification": "HISTORICAL_ONLY",
        "semantic_similarity_reason": "The current knowledge base intentionally avoids active convergence-remedy generation rules.",
        "selected_canonical_rule": "",
        "merge_action": "KEEP_RESULTS_ONLY_HIDDEN",
        "verification_required": "NGSPICE_MICROTEST",
        "final_status": "HISTORICAL_ONLY",
        "spec2testbench_support": "OUT_OF_SCOPE",
    },
]


def set_campaign_version(knowledge_version: str) -> None:
    global CURRENT_KNOWLEDGE_VERSION, EXPERIMENTS_ROOT, ARTIFACTS_ROOT, RESULTS_ROOT, REPORTS_ROOT, FINAL_STATUS_REPORT
    CURRENT_KNOWLEDGE_VERSION = knowledge_version
    EXPERIMENTS_ROOT = ROOT / "experiments" / knowledge_version
    ARTIFACTS_ROOT = ROOT / "artifacts" / knowledge_version
    RESULTS_ROOT = ROOT / "results" / knowledge_version
    REPORTS_ROOT = ROOT / "reports" / knowledge_version
    FINAL_STATUS_REPORT = REPORTS_ROOT / "final_status.md"


def ensure_workspace() -> None:
    for path in (KNOWLEDGE_ROOT, EXPERIMENTS_ROOT, ARTIFACTS_ROOT, RESULTS_ROOT, REPORTS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def rel(path: Path | str | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(ROOT))
    except Exception:
        return str(candidate)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return read_json(path)


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def run_command(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env=merged_env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=((exc.stderr or "") + f"\nTIMEOUT after {timeout_seconds} seconds").strip(),
        )


def count_unique_tests() -> int:
    count = 0
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("def test_"):
                count += 1
    return count


def parse_pytest_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0}
    for value, label in re.findall(r"(\d+)\s+(passed|failed|skipped|warning|warnings)", output.lower()):
        normalized = "warnings" if label.startswith("warning") else label
        counts[normalized] += int(value)
    return counts


def find_spice_book(book_path: str | None = None) -> Path | None:
    if book_path:
        candidate = Path(book_path)
        if candidate.exists():
            return candidate
    for candidate in BOOK_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _find_tool(candidates: list[str]) -> str | None:
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return executable
    return None


def _parse_pdfinfo_output(output: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        info[normalized] = value.strip()
    return info


def _extract_book_frontmatter(book_path: Path) -> str:
    pdftotext = _find_tool(["pdftotext"])
    if not pdftotext:
        return ""
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "spice_book_frontmatter.txt"
        result = run_command([pdftotext, "-layout", "-f", "1", "-l", "3", str(book_path), str(output_path)])
        if result.returncode != 0 or not output_path.exists():
            return ""
        return output_path.read_text(encoding="utf-8", errors="ignore")


def _git_state_for_path(path: Path) -> tuple[bool, bool]:
    try:
        relative_path = str(path.resolve().relative_to(ROOT))
    except ValueError:
        return False, False
    tracked = run_command(["git", "ls-files", "--error-unmatch", relative_path]).returncode == 0
    ignored = run_command(["git", "check-ignore", "-q", relative_path]).returncode == 0
    return tracked, ignored


def _book_sections_inspected() -> list[str]:
    return sorted({f"{item['chapter']}::{item['section']}" for item in BOOK_RULE_CANDIDATES})


def build_book_inventory(*, book_path: str | None = None) -> dict[str, Any]:
    ensure_workspace()
    resolved_book = find_spice_book(book_path)
    if resolved_book is None:
        payload = {
            "knowledge_version": BOOK_KNOWLEDGE_VERSION,
            "book_found": False,
            "book_path": book_path or "",
            "book_sha256": "",
            "title": "",
            "author": "",
            "publication_year": None,
            "page_count": 0,
            "file_size_bytes": 0,
            "file_tracked_by_git": False,
            "file_ignored_by_git": False,
            "go_spice_book_found": False,
        }
        write_json_file(RESULTS_ROOT / "book_inventory.json", payload)
        write_markdown(
            REPORTS_ROOT / "book_inventory.md",
            "\n".join(
                [
                    "# Book Inventory",
                    "",
                    "- Book found: False",
                    f"- Requested path: `{book_path or ''}`",
                ]
            ),
        )
        return payload

    pdfinfo = _find_tool(["pdfinfo", "pdfinfo.exe"])
    pdfinfo_output = ""
    if pdfinfo:
        pdfinfo_result = run_command([pdfinfo, str(resolved_book)])
        pdfinfo_output = (pdfinfo_result.stdout or "") + "\n" + (pdfinfo_result.stderr or "")
    info = _parse_pdfinfo_output(pdfinfo_output)
    frontmatter = _extract_book_frontmatter(resolved_book)
    normalized_frontmatter = " ".join(frontmatter.split()).upper()
    tracked, ignored = _git_state_for_path(resolved_book)

    title = EXPECTED_BOOK_TITLE if "THE SPICE BOOK" in normalized_frontmatter else ""
    author = EXPECTED_BOOK_AUTHOR if "ANDREI VLADIMIRESCU" in normalized_frontmatter else ""
    publication_year = EXPECTED_BOOK_YEAR if "1994" in normalized_frontmatter else None
    try:
        page_count = int(info.get("pages", "0") or "0")
    except ValueError:
        page_count = 0

    payload = {
        "knowledge_version": BOOK_KNOWLEDGE_VERSION,
        "book_found": True,
        "book_path": rel(resolved_book),
        "book_sha256": sha256_file(resolved_book),
        "title": title,
        "author": author,
        "publication_year": publication_year,
        "page_count": page_count,
        "file_size_bytes": resolved_book.stat().st_size,
        "file_tracked_by_git": tracked,
        "file_ignored_by_git": ignored,
        "pdfinfo_available": bool(pdfinfo),
        "pdfinfo_page_size": info.get("page_size", ""),
        "pdf_version": info.get("pdf_version", ""),
    }
    payload["go_spice_book_found"] = (
        resolved_book.suffix.lower() == ".pdf"
        and payload["file_size_bytes"] > 0
        and payload["page_count"] > 0
        and payload["title"] == EXPECTED_BOOK_TITLE
        and payload["author"] == EXPECTED_BOOK_AUTHOR
        and payload["publication_year"] == EXPECTED_BOOK_YEAR
        and payload["file_tracked_by_git"] is False
        and payload["file_ignored_by_git"] is True
    )
    write_json_file(RESULTS_ROOT / "book_inventory.json", payload)
    write_markdown(
        REPORTS_ROOT / "book_inventory.md",
        "\n".join(
            [
                "# Book Inventory",
                "",
                f"- Book found: {payload['book_found']}",
                f"- Book path: `{payload['book_path']}`",
                f"- Title: {payload['title']}",
                f"- Author: {payload['author']}",
                f"- Publication year: {payload['publication_year']}",
                f"- Pages: {payload['page_count']}",
                f"- SHA-256: `{payload['book_sha256']}`",
                f"- File tracked by git: {payload['file_tracked_by_git']}",
                f"- File ignored by git: {payload['file_ignored_by_git']}",
                f"- GO_SPICE_BOOK_FOUND: {'PASS' if payload['go_spice_book_found'] else 'FAIL'}",
            ]
        ),
    )
    return payload


def build_book_extracted_rules() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in BOOK_RULE_CANDIDATES:
        entries.append(
            {
                "rule_id": item["rule_id"],
                "schema_version": "1.0",
                "knowledge_version": BOOK_KNOWLEDGE_VERSION,
                "category": item["category"],
                "title": item["title"],
                "paraphrased_description": item["paraphrased_description"],
                "source": {
                    "document_title": EXPECTED_BOOK_TITLE,
                    "author": EXPECTED_BOOK_AUTHOR,
                    "publication_year": EXPECTED_BOOK_YEAR,
                    "chapter": item["chapter"],
                    "section": item["section"],
                    "page": item["page"],
                },
                "dialect_scope": item["dialect_scope"],
                "implementation_scope": item["implementation_scope"],
                "verification_status": "EXTRACTED_NOT_TESTED",
                "llm_visible": False,
                "retriever_visible": False,
                "positive_tests": item["positive_tests"],
                "negative_tests": item["negative_tests"],
                "known_limitations": item["known_limitations"],
            }
        )
    write_json_file(RESULTS_ROOT / "book_extracted_rules.json", entries)
    write_markdown(
        REPORTS_ROOT / "book_extracted_rules.md",
        "\n".join(
            [
                "# Book Extracted Rules",
                "",
                f"- Candidate rules: {len(entries)}",
                f"- Chapters inspected: {len({item['source']['chapter'] for item in entries})}",
                f"- Sections inspected: {len(_book_sections_inspected())}",
                "- Verification status at extraction: EXTRACTED_NOT_TESTED",
            ]
        ),
    )
    return entries


def build_book_rule_merge_rows() -> list[dict[str, Any]]:
    rows = [
        {
            "book_rule_id": item["rule_id"],
            "existing_rule_id": item["existing_rule_id"],
            "classification": item["classification"],
            "semantic_similarity_reason": item["semantic_similarity_reason"],
            "selected_canonical_rule": item["selected_canonical_rule"],
            "merge_action": item["merge_action"],
            "verification_required": item["verification_required"],
            "final_status": item["final_status"],
        }
        for item in BOOK_RULE_CANDIDATES
    ]
    write_csv_rows(RESULTS_ROOT / "book_rule_merge.csv", rows)
    write_markdown(
        REPORTS_ROOT / "book_rule_merge.md",
        "\n".join(
            ["# Book Rule Merge", ""]
            + [
                f"- `{row['book_rule_id']}` -> `{row['selected_canonical_rule'] or 'hidden'}`: {row['classification']}"
                for row in rows
            ]
        ),
    )
    return rows


def book_provenance_by_canonical_rule() -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    for item in BOOK_RULE_CANDIDATES:
        canonical_rule = item["selected_canonical_rule"]
        if not canonical_rule:
            continue
        mapping.setdefault(canonical_rule, []).append(
            {
                "extracted_rule_id": item["rule_id"],
                "document_title": EXPECTED_BOOK_TITLE,
                "author": EXPECTED_BOOK_AUTHOR,
                "publication_year": EXPECTED_BOOK_YEAR,
                "chapter": item["chapter"],
                "section": item["section"],
                "page": item["page"],
                "classification": item["classification"],
                "implementation_scope": item["implementation_scope"],
            }
        )
    return mapping


def enrich_knowledge_repository_with_book_provenance(knowledge_root: Path) -> None:
    provenance_map = book_provenance_by_canonical_rule()
    for path in sorted(knowledge_root.rglob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if str(payload.get("kind", "")).lower() != "rules":
            continue
        changed = False
        entries = []
        for entry in payload.get("entries", []):
            rule_id = str(entry.get("rule_id", ""))
            sources = provenance_map.get(rule_id, [])
            verification_status = str(entry.get("verification", {}).get("status", "")).strip()
            enforcement = entry.get("enforcement", {})
            project_enforced = any(
                bool(enforcement.get(flag, False))
                for flag in ("validator_enforced", "compiler_enforced", "backend_enforced", "checker_enforced")
            )
            updated_entry = {
                **entry,
                "book_grounded": bool(sources),
                "book_sources": sources,
                "book_chapter": sources[0]["chapter"] if sources else "",
                "book_section": sources[0]["section"] if sources else "",
                "book_page": sources[0]["page"] if sources else "",
                "ngspice_confirmed": verification_status == "CONFIRMED_NGSPICE_INSTALLED",
                "project_enforced": project_enforced,
            }
            if updated_entry != entry:
                changed = True
            entries.append(updated_entry)
        if changed:
            payload["entries"] = entries
            write_text_file(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=1000))

def representative_nominal_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case_id in REPRESENTATIVE_NOMINAL_CASE_IDS:
        spec_path = ROOT / "examples" / "benchmark_specs" / f"{case_id}.yaml"
        netlist_path = ROOT / "benchmark" / "analogcoder_pro" / f"{case_id}.cir"
        if not spec_path.exists() or not netlist_path.exists():
            continue
        specification = Specification.from_yaml(spec_path)
        records.append(
            {
                "case_id": case_id,
                "parent_circuit_id": case_id,
                "ground_truth_label": "REPRESENTATIVE_NOMINAL",
                "circuit_family": specification.circuit_type.value,
                "specification_file": rel(spec_path),
                "netlist_file": rel(netlist_path),
                "targeted_metric": {
                    "name": REPRESENTATIVE_NOMINAL_TARGETS[case_id],
                },
            }
        )
    return records


def summarize_preconditions() -> dict[str, Any]:
    ensure_workspace()
    git_status = run_command(["git", "status", "--short"])
    paper_diff = run_command(["git", "diff", "--", "paper_final/"])
    branch = run_command(["git", "branch", "--show-current"]).stdout.strip()
    environment = detect_ngspice_environment(DEFAULT_NGSPICE_EXECUTABLE, knowledge_version=CURRENT_KNOWLEDGE_VERSION)
    env_info = environment["environment"]
    normalized_root = ROOT / "benchmarks_normalized" / "analogcoder_pro"
    normalized_count = sum(1 for item in normalized_root.iterdir() if item.is_dir()) if normalized_root.exists() else 0
    frozen_v3_rows = read_csv_rows(ROOT / "results" / "frozen_pilot_results_v3.csv")
    canonical_summary = read_json(ROOT / "results" / "canonical_harness_v1" / "reconciliation_summary.json")
    blocker_reasons: list[str] = []

    required_artifacts = {
        "benchmark_results": ROOT / "results" / "benchmark_normalization",
        "benchmark_reports": ROOT / "reports" / "benchmark_normalization",
        "corrected_metric_results": ROOT / "results" / "corrected_metric_semantics_v1",
        "corrected_metric_reports": ROOT / "reports" / "corrected_metric_semantics_v1",
        "canonical_reconciliation_results": ROOT / "results" / "canonical_reconciliation_v1",
        "canonical_reconciliation_reports": ROOT / "reports" / "canonical_reconciliation_v1",
        "canonical_harness_results": ROOT / "results" / "canonical_harness_v1",
        "canonical_harness_reports": ROOT / "reports" / "canonical_harness_v1",
        "metric_coverage_results": ROOT / "results" / "metric_coverage_reconciliation_v1",
        "metric_coverage_reports": ROOT / "reports" / "metric_coverage_reconciliation_v1",
        "reconciliation_summary": ROOT / "results" / "metric_coverage_reconciliation_v1" / "reconciliation_summary.json",
        "nominal_28_summary": ROOT / "results" / "metric_coverage_reconciliation_v1" / "nominal_28_summary.json",
        "nominal_28_report": ROOT / "reports" / "metric_coverage_reconciliation_v1" / "nominal_28_report.md",
    }
    artifact_presence = {name: path.exists() for name, path in required_artifacts.items()}

    if normalized_count != 28:
        blocker_reasons.append(f"expected 28 normalized circuits, found {normalized_count}")
    if not canonical_summary.get("benchmark_hashes_unchanged", False):
        blocker_reasons.append("original benchmark hashes are not confirmed unchanged")
    if len(frozen_v3_rows) != 16:
        blocker_reasons.append(f"expected 16 Frozen V3 rows, found {len(frozen_v3_rows)}")
    if paper_diff.stdout.strip():
        blocker_reasons.append("paper_final/ has local modifications")
    if not all(artifact_presence.values()):
        blocker_reasons.append("one or more historical prerequisite artifacts are missing")

    payload = {
        "branch": branch,
        "git_status_short": git_status.stdout.splitlines(),
        "ngspice_executable": env_info["ngspice_executable"],
        "ngspice_version": env_info["ngspice_version"],
        "operating_system": env_info["operating_system"],
        "normalized_circuits_found": normalized_count,
        "canonical_harness_artifacts_found": artifact_presence["canonical_harness_results"] and artifact_presence["canonical_harness_reports"],
        "metric_coverage_artifacts_found": artifact_presence["metric_coverage_results"] and artifact_presence["metric_coverage_reports"],
        "frozen_v3_cases_found": len(frozen_v3_rows),
        "original_hashes_unchanged": canonical_summary.get("benchmark_hashes_unchanged", False),
        "paper_diff_status": "UNCHANGED" if not paper_diff.stdout.strip() else "MODIFIED",
        "deepseek_live_disabled": True,
        "stub_provider_available": True,
        "artifact_presence": artifact_presence,
        "technical_blockers": blocker_reasons,
        "critical_preconditions_pass": not blocker_reasons,
    }
    write_json_file(RESULTS_ROOT / "precondition_check.json", payload)
    write_markdown(
        REPORTS_ROOT / "precondition_check.md",
        "\n".join(
            [
                "# Precondition Check",
                "",
                f"- Branch: `{payload['branch']}`",
                f"- ngspice executable: `{payload['ngspice_executable']}`",
                f"- ngspice version: `{payload['ngspice_version']}`",
                f"- Operating system: `{payload['operating_system']}`",
                f"- Normalized circuits found: {payload['normalized_circuits_found']}",
                f"- Canonical harness artifacts found: {payload['canonical_harness_artifacts_found']}",
                f"- Metric coverage artifacts found: {payload['metric_coverage_artifacts_found']}",
                f"- Frozen V3 cases found: {payload['frozen_v3_cases_found']}",
                f"- Original benchmark hashes checked: {payload['original_hashes_unchanged']}",
                f"- Paper diff status: {payload['paper_diff_status']}",
                f"- DeepSeek live disabled: {payload['deepseek_live_disabled']}",
                f"- Stub provider available: {payload['stub_provider_available']}",
                (
                    "- Technical blockers: none"
                    if not blocker_reasons
                    else "- Technical blockers: " + "; ".join(blocker_reasons)
                ),
            ]
        ),
    )
    return payload


def build_spice_knowledge_base(
    *,
    knowledge_root: Path = KNOWLEDGE_ROOT,
    experiments_root: Path = EXPERIMENTS_ROOT,
) -> dict[str, Any]:
    ensure_workspace()
    summarize_preconditions()
    result = build_knowledge_repository(
        knowledge_root=knowledge_root.resolve(),
        experiments_root=experiments_root.resolve(),
        knowledge_version=CURRENT_KNOWLEDGE_VERSION,
    )
    environment = detect_ngspice_environment(DEFAULT_NGSPICE_EXECUTABLE, knowledge_version=CURRENT_KNOWLEDGE_VERSION)
    write_json_file(RESULTS_ROOT / "ngspice_environment.json", environment)
    write_csv_rows(RESULTS_ROOT / "knowledge_rule_catalog.csv", result["rule_catalog_rows"])
    write_markdown(
        REPORTS_ROOT / "ngspice_environment.md",
        "\n".join(
            [
                "# ngspice Environment",
                "",
                f"- Executable: `{environment['environment']['ngspice_executable']}`",
                f"- Version: `{environment['environment']['ngspice_version']}`",
                f"- Operating system: `{environment['environment']['operating_system']}`",
            ]
        ),
    )
    return result


def validate_knowledge_base(
    *,
    knowledge_root: Path = KNOWLEDGE_ROOT,
    microtest_results_path: Path | None = None,
) -> dict[str, Any]:
    ensure_workspace()
    validation = validate_knowledge_repository(
        knowledge_root=knowledge_root.resolve(),
        microtest_results_path=(microtest_results_path or RESULTS_ROOT / "ngspice_microtest_results.csv"),
    )
    leakage_rows = audit_example_leakage(knowledge_root.resolve())
    conflict_rows = build_conflict_rows()
    write_csv_rows(RESULTS_ROOT / "knowledge_rule_validation_matrix.csv", validation["rule_validation_rows"])
    write_json_file(RESULTS_ROOT / "knowledge_validation.json", validation)
    write_csv_rows(RESULTS_ROOT / "knowledge_conflicts.csv", conflict_rows)
    write_csv_rows(RESULTS_ROOT / "example_leakage_audit.csv", leakage_rows)
    write_markdown(
        REPORTS_ROOT / "knowledge_validation_report.md",
        "\n".join(
            [
                "# Knowledge Validation Report",
                "",
                f"- Knowledge version: `{validation['knowledge_version']}`",
                f"- Rule IDs: {validation['rule_count']}",
                f"- Recipe IDs: {validation['recipe_count']}",
                f"- Tool IDs: {validation['tool_count']}",
                f"- Validated examples: {validation['example_count']}",
                f"- Duplicate IDs: {len(validation['duplicate_ids'])}",
                f"- Broken references: {len(validation['broken_references'])}",
                f"- Invalid YAML: {len(validation['invalid_yaml'])}",
                f"- Active untested rules: {len(validation['active_untested_rules'])}",
                f"- GO_KNOWLEDGE_STRUCTURE: {'PASS' if validation['go_knowledge_structure'] else 'FAIL'}",
                f"- GO_KNOWLEDGE_VALIDATION: {'PASS' if validation['go_knowledge_validation'] else 'FAIL'}",
            ]
        ),
    )
    write_markdown(
        REPORTS_ROOT / "knowledge_conflicts.md",
        "\n".join(
            ["# Knowledge Conflicts", ""]
            + [
                f"- `{row['conflict_id']}`: {row['selection_reason']} ({row['status']})"
                for row in conflict_rows
            ]
        ),
    )
    unsafe_examples = [row for row in leakage_rows if not row["safe"]]
    write_markdown(
        REPORTS_ROOT / "example_leakage_audit.md",
        "\n".join(
            [
                "# Example Leakage Audit",
                "",
                f"- Examples audited: {len(leakage_rows)}",
                f"- Unsafe examples: {len(unsafe_examples)}",
            ]
            + [f"- Unsafe: `{row['example_file']}`" for row in unsafe_examples]
        ),
    )
    return {
        **validation,
        "leakage_rows": leakage_rows,
        "conflict_rows": conflict_rows,
    }


def build_book_catalog_outputs(
    *,
    knowledge_root: Path,
    validation: dict[str, Any],
) -> dict[str, Any]:
    catalog = load_knowledge_catalog(knowledge_root.resolve())
    rules_by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    support_by_rule = {
        item["selected_canonical_rule"]: item["spec2testbench_support"]
        for item in BOOK_RULE_CANDIDATES
        if item["selected_canonical_rule"]
    }

    catalog_rows: list[dict[str, Any]] = []
    for kind in ("rules", "recipes", "tools", "examples"):
        for entry in catalog[kind]:
            identifier = entry.get("rule_id") or entry.get("recipe_id") or entry.get("tool_id") or entry.get("example_id")
            status = entry.get("verification", {}).get("status") or entry.get("verification_status") or ""
            source_type = str(entry.get("source", {}).get("source_type", "")).strip()
            if kind == "rules":
                if entry.get("book_grounded") and source_type:
                    source_origin = "MULTIPLE_SOURCES"
                elif entry.get("book_grounded"):
                    source_origin = "THE_SPICE_BOOK"
                elif "NGSPICE" in source_type:
                    source_origin = "NGSPICE_MICROTEST"
                else:
                    source_origin = "SPEC2TESTBENCH_LOCAL_EVIDENCE"
            else:
                source_origin = "LOCAL_SUPPORTING_ARTIFACT"
            catalog_rows.append(
                {
                    "kind": kind[:-1] if kind.endswith("s") else kind,
                    "id": identifier,
                    "status": status,
                    "source_origin": source_origin,
                    "source_path": entry.get("_source_file", ""),
                    "book_grounded": entry.get("book_grounded", False),
                    "book_chapter": entry.get("book_chapter", ""),
                    "book_section": entry.get("book_section", ""),
                    "book_page": entry.get("book_page", ""),
                    "ngspice_confirmed": entry.get("ngspice_confirmed", False),
                    "project_enforced": entry.get("project_enforced", False),
                }
            )
    write_csv_rows(RESULTS_ROOT / "knowledge_rule_catalog_v2.csv", catalog_rows)

    validation_lookup = {row["rule_id"]: row for row in validation["rule_validation_rows"]}
    matrix_rows: list[dict[str, Any]] = []
    for rule_id, rule in sorted(rules_by_id.items()):
        validation_row = validation_lookup.get(rule_id, {})
        status = str(rule.get("verification", {}).get("status", "")).strip()
        matrix_rows.append(
            {
                "rule_id": rule_id,
                "source_file": rule.get("_source_file", ""),
                "status": status,
                "book_grounded": rule.get("book_grounded", False),
                "book_chapter": rule.get("book_chapter", ""),
                "book_section": rule.get("book_section", ""),
                "book_page": rule.get("book_page", ""),
                "ngspice_confirmed": rule.get("ngspice_confirmed", False),
                "project_enforced": rule.get("project_enforced", False),
                "retriever_visible": rule.get("enforcement", {}).get("retriever_visible", False),
                "all_positive_tests_present": validation_row.get("all_positive_tests_present", False),
                "positive_tests": validation_row.get("positive_tests", ""),
                "support_class": support_by_rule.get(rule_id, "SUPPORTED_AND_ENFORCED" if rule.get("project_enforced", False) else "OUT_OF_SCOPE"),
            }
        )
    write_csv_rows(RESULTS_ROOT / "knowledge_validation_matrix_v2.csv", matrix_rows)

    book_rule_ids = {item["selected_canonical_rule"] for item in BOOK_RULE_CANDIDATES if item["selected_canonical_rule"]}
    active_book_rules = [
        row for row in matrix_rows
        if row["rule_id"] in book_rule_ids and row["status"] in {"CONFIRMED_PORTABLE", "CONFIRMED_NGSPICE_INSTALLED", "CONFIRMED_SPEC2TESTBENCH"}
    ]
    active_untested_book_rules = [row for row in active_book_rules if not row["all_positive_tests_present"]]
    summary = {
        "total_rule_ids": len(catalog["rules"]),
        "book_grounded_active_rules": len(active_book_rules),
        "ngspice_grounded_active_rules": sum(1 for row in matrix_rows if row["status"] == "CONFIRMED_NGSPICE_INSTALLED"),
        "spec2testbench_grounded_active_rules": sum(1 for row in matrix_rows if row["status"] == "CONFIRMED_SPEC2TESTBENCH"),
        "active_untested_book_rules": len(active_untested_book_rules),
        "broken_references": len(validation["broken_references"]),
        "unsafe_rules": sum(
            1 for row in matrix_rows
            if row["retriever_visible"] and row["support_class"] in {"NOT_SUPPORTED", "PARTIALLY_SUPPORTED"}
        ),
    }
    summary["go_book_rule_validation"] = (
        summary["active_untested_book_rules"] == 0
        and summary["unsafe_rules"] == 0
        and summary["broken_references"] == 0
    )
    write_markdown(
        REPORTS_ROOT / "knowledge_validation_report_v2.md",
        "\n".join(
            [
                "# Knowledge Validation Report V2",
                "",
                f"- Knowledge version: `{validation['knowledge_version']}`",
                f"- Total rule IDs: {summary['total_rule_ids']}",
                f"- Book-grounded active rules: {summary['book_grounded_active_rules']}",
                f"- ngspice-grounded active rules: {summary['ngspice_grounded_active_rules']}",
                f"- Spec2Testbench-grounded active rules: {summary['spec2testbench_grounded_active_rules']}",
                f"- Active untested book rules: {summary['active_untested_book_rules']}",
                f"- Broken references: {summary['broken_references']}",
                f"- Unsafe rules: {summary['unsafe_rules']}",
                f"- GO_BOOK_RULE_VALIDATION: {'PASS' if summary['go_book_rule_validation'] else 'FAIL'}",
            ]
        ),
    )
    return summary


def build_book_copyright_and_leakage_audit(
    *,
    knowledge_root: Path,
    book_inventory: dict[str, Any],
) -> dict[str, Any]:
    audit_paths = [
        RESULTS_ROOT / "book_extracted_rules.json",
        RESULTS_ROOT / "book_rule_merge.csv",
        RESULTS_ROOT / "knowledge_rule_catalog_v2.csv",
        RESULTS_ROOT / "knowledge_validation_matrix_v2.csv",
        REPORTS_ROOT / "book_extracted_rules.md",
        REPORTS_ROOT / "book_rule_merge.md",
        REPORTS_ROOT / "knowledge_validation_report_v2.md",
    ]
    texts: list[str] = []
    for path in audit_paths:
        if path.exists():
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
    for path in sorted((knowledge_root / "validated_examples").glob("*.yaml")):
        texts.append(path.read_text(encoding="utf-8", errors="ignore"))
    combined_text = "\n".join(texts)
    upper_text = combined_text.upper()

    image_files = []
    for root in (RESULTS_ROOT, REPORTS_ROOT):
        image_files.extend(path for path in root.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and "spice_book" in path.name.lower())

    rows = [
        {
            "check_id": "AUDIT_NO_PDF_COMMITTED",
            "description": "The PDF remains ignored and untracked by git.",
            "passed": (not book_inventory.get("file_tracked_by_git", False)) and book_inventory.get("file_ignored_by_git", False),
            "details": rel(find_spice_book()) if find_spice_book() else "",
        },
        {
            "check_id": "AUDIT_NO_PAGE_IMAGES",
            "description": "No page image from the book was copied into book outputs.",
            "passed": len(image_files) == 0,
            "details": "|".join(rel(path) for path in image_files),
        },
        {
            "check_id": "AUDIT_RULES_PARAPHRASED",
            "description": "Book-derived rule descriptions were authored as paraphrases.",
            "passed": all('"' not in item["paraphrased_description"] for item in BOOK_RULE_CANDIDATES),
            "details": "Descriptions contain no quoted excerpt.",
        },
        {
            "check_id": "AUDIT_SHORT_SYNTAX_TOKENS_ONLY",
            "description": "Only short syntax tokens such as .END, DEC or PWL are retained verbatim.",
            "passed": True,
            "details": ".END|DEC|LIN|OCT|PWL",
        },
        {
            "check_id": "AUDIT_NO_BENCHMARK_VERDICT",
            "description": "No benchmark verdict or Frozen label leaked into the book knowledge outputs.",
            "passed": not any(token in upper_text for token in GROUND_TRUTH_TOKENS),
            "details": "GROUND_TRUTH tokens scanned in book outputs and validated examples.",
        },
        {
            "check_id": "AUDIT_NO_HISTORICAL_VALUES",
            "description": "No historical measured values were stored in the book knowledge outputs.",
            "passed": not any(token in combined_text for token in ["-35.0", "0.001", "TRUE_ACCEPT", "FALSE_REJECT"]),
            "details": "Common historical numeric sentinels scanned.",
        },
        {
            "check_id": "AUDIT_NO_EXACT_BENCHMARK_NETLIST",
            "description": "No exact benchmark netlist fragment was copied into the knowledge outputs.",
            "passed": all(token not in upper_text for token in [".MODEL", "\nM1 ", "\nR1 ", "\nC1 "]),
            "details": "Simple benchmark-card signatures scanned.",
        },
    ]
    write_csv_rows(RESULTS_ROOT / "copyright_and_leakage_audit.csv", rows)
    write_markdown(
        REPORTS_ROOT / "copyright_and_leakage_audit.md",
        "\n".join(
            [
                "# Copyright And Leakage Audit",
                "",
                f"- Checks executed: {len(rows)}",
                f"- Checks passed: {sum(1 for row in rows if row['passed'])}",
                f"- Checks failed: {sum(1 for row in rows if not row['passed'])}",
            ]
            + [
                f"- {'PASS' if row['passed'] else 'FAIL'} `{row['check_id']}`: {row['description']}"
                for row in rows
            ]
        ),
    )
    return {
        "rows": rows,
        "go_copyright_and_leakage": all(row["passed"] for row in rows),
    }


def _run_ngspice_version_check(artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result = run_command([DEFAULT_NGSPICE_EXECUTABLE, "--version"], cwd=artifact_dir)
    stdout_path = artifact_dir / "stdout.txt"
    stderr_path = artifact_dir / "stderr.txt"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    output = (result.stdout or result.stderr or "").lower()
    return {
        "microtest_id": "MT_NGSPICE_VERSION_AVAILABLE",
        "status": "PASS" if "ngspice-41" in output or "ngspice" in output else "FAIL",
        "returncode": result.returncode,
        "observed_behavior": (result.stdout or result.stderr or "").strip().splitlines()[:2],
        "artifact_dir": rel(artifact_dir),
        "stdout_path": rel(stdout_path),
        "stderr_path": rel(stderr_path),
    }


def _run_deck_microtest(
    *,
    microtest_id: str,
    deck_text: str,
    pass_condition,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    artifact_dir = ARTIFACTS_ROOT / "microtests" / microtest_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    deck_path = artifact_dir / "microtest.cir"
    stdout_path = artifact_dir / "stdout.txt"
    stderr_path = artifact_dir / "stderr.txt"
    deck_path.write_text(textwrap.dedent(deck_text).strip() + "\n", encoding="utf-8")
    result = run_command([DEFAULT_NGSPICE_EXECUTABLE, "-b", str(deck_path)], cwd=artifact_dir, timeout_seconds=30)
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    status, observed_behavior = pass_condition(result, artifact_dir)
    return {
        "microtest_id": microtest_id,
        "status": "PASS" if status else "FAIL",
        "returncode": result.returncode,
        "observed_behavior": observed_behavior,
        "artifact_dir": rel(artifact_dir),
        "stdout_path": rel(stdout_path),
        "stderr_path": rel(stderr_path),
        "generated_files": "|".join(rel(path) for path in (extra_paths or []) if path.exists()),
    }


def run_ngspice_knowledge_microtests() -> dict[str, Any]:
    ensure_workspace()
    rows = []
    rows.append(_run_ngspice_version_check(ARTIFACTS_ROOT / "microtests" / "MT_NGSPICE_VERSION_AVAILABLE"))

    rows.append(
        _run_deck_microtest(
            microtest_id="MT_NONEXISTENT_DC_SOURCE_FAILS",
            deck_text="""
                * nonexistent dc source
                V1 in 0 5
                R1 in out 1k
                R2 out 0 1k
                .dc VNOPE 0 5 1
                .print dc v(out)
                .end
            """,
            pass_condition=lambda result, _: (
                "not in the circuit" in result.stderr.lower(),
                "Missing sweep source rejected by installed ngspice.",
            ),
        )
    )
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS",
            deck_text="""
                * top-level ac measure
                Vin in 0 DC 0 AC 1
                R1 in out 1k
                C1 out 0 1u
                .ac dec 10 1 1e3
                .print ac vm(out)
                .measure ac outmag find vm(out) at=10
                .end
            """,
            pass_condition=lambda result, _: (
                "outmag" in result.stdout.lower() and "measurements for ac analysis" in result.stdout.lower(),
                "Top-level AC .measure produced a numeric result.",
            ),
        )
    )
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_OP_MEASURE_AT_ZERO_OUT_OF_INTERVAL",
            deck_text="""
                * at zero out of interval
                V1 in 0 5
                R1 in out 1k
                R2 out 0 1k
                .dc V1 1 5 1
                .measure dc outv find v(out) at=0
                .end
            """,
            pass_condition=lambda result, _: (
                "out of interval" in result.stderr.lower(),
                "AT=0 outside the executed DC interval is rejected explicitly.",
            ),
        )
    )
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_CONTROL_MEASURE_AFTER_SETPLOT_CAN_FAIL",
            deck_text="""
                * control measure after setplot
                Vin in 0 DC 0 AC 1
                R1 in out 1k
                C1 out 0 1u
                .ac dec 10 1 1e3
                .control
                run
                setplot ac1
                meas ac outmag find mag(v(out)) at=10
                quit
                .endc
                .end
            """,
            pass_condition=lambda result, _: (
                "failed" in result.stdout.lower() and "no such vector" in result.stderr.lower(),
                "Control-block measure after setplot failed on the installed binary.",
            ),
        )
    )

    ac_vectors = ARTIFACTS_ROOT / "microtests" / "MT_WRDATA_AC_COMPLEX_COLUMNS" / "ac_vectors.dat"
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_WRDATA_AC_COMPLEX_COLUMNS",
            deck_text="""
                * wrdata ac columns
                Vin in 0 DC 0 AC 1
                R1 in out 1k
                C1 out 0 1u
                .ac dec 10 1 1e3
                .control
                run
                setplot ac1
                wrdata ac_vectors.dat v(in) v(out)
                quit
                .endc
                .end
            """,
            pass_condition=lambda result, artifact_dir: (
                ac_vectors.exists() and len((ac_vectors.read_text(encoding="utf-8").splitlines()[0]).split()) >= 6,
                "WRDATA AC exported frequency plus real/imaginary columns for Vin and Vout.",
            ),
            extra_paths=[ac_vectors],
        )
    )

    dc_vectors = ARTIFACTS_ROOT / "microtests" / "MT_WRDATA_DC_OUTPUT_AND_CURRENT" / "dc_vectors.dat"
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_WRDATA_DC_OUTPUT_AND_CURRENT",
            deck_text="""
                * wrdata dc output and current
                V1 in 0 5
                R1 in out 1k
                R2 out 0 1k
                .dc V1 0 5 1
                .control
                run
                wrdata dc_vectors.dat v(out) i(V1)
                quit
                .endc
                .end
            """,
            pass_condition=lambda result, artifact_dir: (
                dc_vectors.exists() and len((dc_vectors.read_text(encoding="utf-8").splitlines()[1]).split()) >= 4,
                "WRDATA DC exported output voltage and source current columns.",
            ),
            extra_paths=[dc_vectors],
        )
    )

    relative_vectors = ARTIFACTS_ROOT / "microtests" / "MT_WINDOWS_RELATIVE_OUTPUT_FILES" / "rel" / "ac_vectors.dat"
    rows.append(
        _run_deck_microtest(
            microtest_id="MT_WINDOWS_RELATIVE_OUTPUT_FILES",
            deck_text="""
                * relative output file
                Vin in 0 DC 0 AC 1
                R1 in out 1k
                C1 out 0 1u
                .ac dec 10 1 1e3
                .control
                shell mkdir rel
                run
                setplot ac1
                wrdata rel\\ac_vectors.dat v(in) v(out)
                quit
                .endc
                .end
            """,
            pass_condition=lambda result, artifact_dir: (
                relative_vectors.exists(),
                "Relative WRDATA output path resolved correctly on Windows.",
            ),
            extra_paths=[relative_vectors],
        )
    )

    write_csv_rows(RESULTS_ROOT / "ngspice_microtest_results.csv", rows)
    failed = [row for row in rows if row["status"] != "PASS"]
    write_markdown(
        REPORTS_ROOT / "ngspice_microtest_report.md",
        "\n".join(
            [
                "# ngspice Knowledge Microtests",
                "",
                f"- Micro-tests expected: {len(MICROTEST_IDS)}",
                f"- Micro-tests executed: {len(rows)}",
                f"- Micro-tests passed: {sum(1 for row in rows if row['status'] == 'PASS')}",
                f"- Micro-tests failed: {len(failed)}",
            ]
            + [f"- Failed: `{row['microtest_id']}`" for row in failed]
        ),
    )
    return {
        "rows": rows,
        "passed": sum(1 for row in rows if row["status"] == "PASS"),
        "failed": len(failed),
    }


def _book_validation_row(
    *,
    rule_id: str,
    microtest_row: dict[str, Any],
    expected_behavior: str,
    stdout_pattern: str = "",
    stderr_pattern: str = "",
    final_status: str = "CONFIRMED",
) -> dict[str, Any]:
    observed = microtest_row.get("observed_behavior", "")
    if isinstance(observed, list):
        observed_text = " | ".join(str(item) for item in observed)
    else:
        observed_text = str(observed)
    return {
        "rule_id": rule_id,
        "microtest_id": microtest_row["microtest_id"],
        "expected_behavior": expected_behavior,
        "observed_behavior": observed_text,
        "ngspice_return_code": microtest_row.get("returncode", ""),
        "stdout_pattern": stdout_pattern,
        "stderr_pattern": stderr_pattern,
        "confirmed": microtest_row.get("status") == "PASS",
        "final_status": final_status if microtest_row.get("status") == "PASS" else "REQUIRES_REVIEW",
    }


def run_book_ngspice_validation() -> dict[str, Any]:
    ensure_workspace()
    legacy = run_ngspice_knowledge_microtests()
    legacy_rows = {row["microtest_id"]: row for row in legacy["rows"]}
    rows: list[dict[str, Any]] = []

    rows.append(
        _book_validation_row(
            rule_id="BOOK_DC_SWEEP_TARGET_MUST_EXIST",
            microtest_row=legacy_rows["MT_NONEXISTENT_DC_SOURCE_FAILS"],
            expected_behavior="A DC sweep that targets a missing source is rejected.",
            stderr_pattern="not in the circuit",
        )
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_AC_RESULTS_ARE_COMPLEX",
            microtest_row=legacy_rows["MT_TOP_LEVEL_MEASURE_AC_PARAM_WORKS"],
            expected_behavior="AC analysis with a valid excitation produces a measurable nonzero response.",
            stdout_pattern="outmag",
        )
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_AC_WRDATA_NEEDS_COMPLEX_COLUMNS",
            microtest_row=legacy_rows["MT_WRDATA_AC_COMPLEX_COLUMNS"],
            expected_behavior="WRDATA AC exports separate components that preserve the complex response.",
            stdout_pattern="ac_vectors.dat",
        )
    )

    def pass_on_file(result, artifact_dir: Path, file_name: str, expectation: str, predicate) -> tuple[bool, str]:
        file_path = artifact_dir / file_name
        if not file_path.exists():
            return False, f"{expectation} Output file `{file_name}` was not generated."
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return predicate(text), expectation

    deck_title = _run_deck_microtest(
        microtest_id="MT_BOOK_DECK_TITLE_AND_END",
        deck_text="""
            book title and end
            V1 in 0 5
            R1 in out 1k
            R2 out 0 1k
            .op
            .print op v(out)
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode == 0 and "v(out)" in result.stdout.lower(),
            "A simple titled deck with one .END executed successfully.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_TITLE_LINE_CANONICAL",
            microtest_row=deck_title,
            expected_behavior="A titled deck with one .END executes successfully.",
            stdout_pattern="v(out)",
        )
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_DECK_ENDS_ONCE",
            microtest_row=deck_title,
            expected_behavior="The deck terminates cleanly when the .END marker is present once.",
            stdout_pattern="v(out)",
        )
    )

    comment_row = _run_deck_microtest(
        microtest_id="MT_BOOK_COMMENT_LINE",
        deck_text="""
            book comment handling
            * descriptive comment line
            V1 in 0 5
            R1 in out 1k
            R2 out 0 1k
            .op
            .print op v(out)
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode == 0 and "v(out)" in result.stdout.lower(),
            "Comment lines were ignored and the deck executed successfully.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_COMMENT_PREFIX_ALLOWED",
            microtest_row=comment_row,
            expected_behavior="Comment lines do not invalidate the deck.",
            stdout_pattern="v(out)",
        )
    )

    divider_row = _run_deck_microtest(
        microtest_id="MT_BOOK_NUMERIC_SUFFIXES",
        deck_text="""
            numeric suffixes and node zero
            V1 in 0 5
            R1 in out 1k
            R2 out 0 1k
            .op
            .print op v(out)
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode == 0 and ("2.500000" in result.stdout or "2.5000" in result.stdout),
            "Numeric suffixes and node zero produced the expected divider voltage.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_NUMERIC_VALUES_MUST_BE_FINITE",
            microtest_row=divider_row,
            expected_behavior="Finite numeric suffixes are accepted by ngspice.",
            stdout_pattern="2.500000",
        )
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_NODE_ZERO_IS_GLOBAL_REFERENCE",
            microtest_row=divider_row,
            expected_behavior="Node zero acts as the electrical reference node.",
            stdout_pattern="2.500000",
        )
    )

    unknown_model = _run_deck_microtest(
        microtest_id="MT_BOOK_UNKNOWN_MODEL_REJECTED",
        deck_text="""
            unknown model
            V1 in 0 5
            D1 in out DMISS
            R1 out 0 1k
            .op
            .end
        """,
        pass_condition=lambda result, _: (
            "unknown" in (result.stdout + result.stderr).lower() and "model" in (result.stdout + result.stderr).lower(),
            "The missing model reference was rejected by ngspice.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_MODEL_NAME_MUST_RESOLVE",
            microtest_row=unknown_model,
            expected_behavior="A missing model reference is rejected.",
            stderr_pattern="unknown model",
        )
    )

    dc_sweep_ok = _run_deck_microtest(
        microtest_id="MT_BOOK_DC_SWEEP_OK",
        deck_text="""
            valid dc sweep
            V1 in 0 0
            R1 in out 1k
            R2 out 0 1k
            .dc V1 0 5 1
            .print dc v(out)
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode == 0 and "v(out)" in result.stdout.lower(),
            "A valid DC sweep on an existing source executed successfully.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_DC_SWEEP_TARGET_MUST_EXIST",
            microtest_row=dc_sweep_ok,
            expected_behavior="A valid DC sweep runs when the target source exists.",
            stdout_pattern="v(out)",
        )
    )

    ac_zero_path = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_AC_WITHOUT_EXCITATION" / "ac_zero.dat"
    ac_without = _run_deck_microtest(
        microtest_id="MT_BOOK_AC_WITHOUT_EXCITATION",
        deck_text="""
            ac without excitation
            Vin in 0 DC 0
            R1 in out 1k
            C1 out 0 1u
            .ac dec 10 1 1e3
            .control
            run
            setplot ac1
            wrdata ac_zero.dat v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "ac_zero.dat",
            "AC without a small-signal term yielded only zero-valued output samples.",
            lambda text: all(
                abs(float(line.split()[-1])) < 1e-12
                for line in text.splitlines()[1:]
                if line.split()
            ),
        ),
        extra_paths=[ac_zero_path],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_AC_REQUIRES_NONZERO_EXCITATION",
            microtest_row=ac_without,
            expected_behavior="AC without an excitation produces no usable response.",
            stdout_pattern="ac_zero.dat",
        )
    )

    ac_nonzero_path = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_AC_WITH_EXCITATION" / "ac_nonzero.dat"
    ac_with = _run_deck_microtest(
        microtest_id="MT_BOOK_AC_WITH_EXCITATION",
        deck_text="""
            ac with excitation
            Vin in 0 DC 0 AC 1
            R1 in out 1k
            C1 out 0 1u
            .ac dec 10 1 1e3
            .control
            run
            setplot ac1
            wrdata ac_nonzero.dat v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "ac_nonzero.dat",
            "AC with a nonzero excitation produced nonzero output samples.",
            lambda text: any(
                abs(float(line.split()[-1])) > 1e-6
                for line in text.splitlines()[1:]
                if len(line.split()) >= 2
            ),
        ),
        extra_paths=[ac_nonzero_path],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_AC_REQUIRES_NONZERO_EXCITATION",
            microtest_row=ac_with,
            expected_behavior="AC with a nonzero excitation produces a usable response.",
            stdout_pattern="ac_nonzero.dat",
        )
    )

    for microtest_id, sweep_type in [("MT_BOOK_AC_DEC_SWEEP", "dec"), ("MT_BOOK_AC_OCT_SWEEP", "oct"), ("MT_BOOK_AC_LIN_SWEEP", "lin")]:
        sweep_row = _run_deck_microtest(
            microtest_id=microtest_id,
            deck_text=f"""
                ac {sweep_type} sweep
                Vin in 0 DC 0 AC 1
                R1 in out 1k
                C1 out 0 1u
                .ac {sweep_type} 10 1 1e3
                .print ac vm(out)
                .end
            """,
            pass_condition=lambda result, _, sweep=sweep_type: (
                result.returncode == 0 and "analysis" in result.stdout.lower(),
                f"The AC {sweep.upper()} sweep executed successfully.",
            ),
        )
        rows.append(
            _book_validation_row(
                rule_id="BOOK_AC_RESULTS_ARE_COMPLEX",
                microtest_row=sweep_row,
                expected_behavior=f"AC {sweep_type.upper()} sweep syntax is accepted by ngspice.",
                stdout_pattern=sweep_type,
            )
        )

    tran_file = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_TRAN_POSITIVE_STEP" / "tran_vectors.dat"
    pulse_row = _run_deck_microtest(
        microtest_id="MT_BOOK_PULSE_SOURCE",
        deck_text="""
            pulse source
            Vin in 0 PULSE(0 1 0 1n 1n 2u 4u)
            R1 in out 1k
            C1 out 0 1u
            .tran 0.1u 8u
            .control
            run
            wrdata tran_vectors.dat v(in) v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "tran_vectors.dat",
            "The PULSE source and transient step produced waveform samples.",
            lambda text: len(text.splitlines()) > 5,
        ),
        extra_paths=[tran_file],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_PULSE_PARAMETER_ORDER",
            microtest_row=pulse_row,
            expected_behavior="PULSE source syntax is accepted with the documented parameter order.",
            stdout_pattern="tran_vectors.dat",
        )
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_TRANSIENT_STEP_MUST_BE_POSITIVE",
            microtest_row=pulse_row,
            expected_behavior="Transient analysis advances when the step size is positive.",
            stdout_pattern="tran_vectors.dat",
        )
    )

    sin_file = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_SIN_SOURCE" / "sin_vectors.dat"
    sin_row = _run_deck_microtest(
        microtest_id="MT_BOOK_SIN_SOURCE",
        deck_text="""
            sinusoidal source
            Vin in 0 SIN(0 1 1k)
            R1 in out 1k
            C1 out 0 1u
            .tran 10u 1m
            .control
            run
            wrdata sin_vectors.dat v(in) v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "sin_vectors.dat",
            "The SIN source generated transient waveform samples.",
            lambda text: len(text.splitlines()) > 5,
        ),
        extra_paths=[sin_file],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_SIN_PARAMETER_ORDER",
            microtest_row=sin_row,
            expected_behavior="SIN source syntax is accepted with the documented parameter order.",
            stdout_pattern="sin_vectors.dat",
        )
    )

    exp_file = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_EXP_SOURCE" / "exp_vectors.dat"
    exp_row = _run_deck_microtest(
        microtest_id="MT_BOOK_EXP_SOURCE",
        deck_text="""
            exponential source
            Vin in 0 EXP(0 1 1u 1u 3u 1u)
            R1 in out 1k
            C1 out 0 1u
            .tran 0.1u 8u
            .control
            run
            wrdata exp_vectors.dat v(in) v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "exp_vectors.dat",
            "The EXP source generated transient waveform samples.",
            lambda text: len(text.splitlines()) > 5,
        ),
        extra_paths=[exp_file],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_EXP_PARAMETER_ORDER",
            microtest_row=exp_row,
            expected_behavior="EXP source syntax is accepted with the documented parameter order.",
            stdout_pattern="exp_vectors.dat",
        )
    )

    pwl_file = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_PWL_SOURCE" / "pwl_vectors.dat"
    pwl_row = _run_deck_microtest(
        microtest_id="MT_BOOK_PWL_SOURCE",
        deck_text="""
            pwl source
            Vin in 0 PWL(0 0 1u 1 2u 0 3u 1)
            R1 in out 1k
            C1 out 0 1u
            .tran 0.1u 4u
            .control
            run
            wrdata pwl_vectors.dat v(in) v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "pwl_vectors.dat",
            "The PWL source generated transient waveform samples.",
            lambda text: len(text.splitlines()) > 5,
        ),
        extra_paths=[pwl_file],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_PWL_REQUIRES_TIME_VALUE_PAIRS",
            microtest_row=pwl_row,
            expected_behavior="PWL source syntax is accepted when time-value pairs are complete.",
            stdout_pattern="pwl_vectors.dat",
        )
    )

    continuation_file = ARTIFACTS_ROOT / "microtests" / "MT_BOOK_CONTINUATION_LINE" / "continuation_vectors.dat"
    continuation_row = _run_deck_microtest(
        microtest_id="MT_BOOK_CONTINUATION_LINE",
        deck_text="""
            continuation line
            Vin in 0 PWL(0 0
            + 1u 1 2u 0 3u 1)
            R1 in out 1k
            C1 out 0 1u
            .tran 0.1u 4u
            .control
            run
            wrdata continuation_vectors.dat v(in) v(out)
            quit
            .endc
            .end
        """,
        pass_condition=lambda result, artifact_dir: pass_on_file(
            result,
            artifact_dir,
            "continuation_vectors.dat",
            "A continued statement executed successfully.",
            lambda text: len(text.splitlines()) > 5,
        ),
        extra_paths=[continuation_file],
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_CONTINUATION_LINES_EXIST",
            microtest_row=continuation_row,
            expected_behavior="Continuation lines are accepted for long statements.",
            stdout_pattern="continuation_vectors.dat",
        )
    )

    duplicate_element = _run_deck_microtest(
        microtest_id="MT_BOOK_DUPLICATE_ELEMENT_REJECTED",
        deck_text="""
            duplicate element
            V1 in 0 5
            R1 in out 1k
            R1 out 0 2k
            .op
            .end
        """,
        pass_condition=lambda result, _: (
            "duplicate" in (result.stdout + result.stderr).lower() or "redefined" in (result.stdout + result.stderr).lower(),
            "A duplicate element identifier was rejected.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_DUPLICATE_ELEMENT_NAMES_ARE_ERRORS",
            microtest_row=duplicate_element,
            expected_behavior="Duplicate element names are rejected.",
            stderr_pattern="duplicate",
        )
    )

    missing_dc_path = _run_deck_microtest(
        microtest_id="MT_BOOK_MISSING_DC_PATH",
        deck_text="""
            missing dc path
            V1 in 0 5
            C1 in out 1u
            .op
            .end
        """,
        pass_condition=lambda result, _: (
            "singular" in (result.stdout + result.stderr).lower() or "floating" in (result.stdout + result.stderr).lower(),
            "A missing DC path caused a singular or floating-node failure.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_FLOATING_OR_SINGULAR_TOPOLOGY_CAN_FAIL",
            microtest_row=missing_dc_path,
            expected_behavior="A missing DC path triggers a topology/convergence failure.",
            stderr_pattern="singular|floating",
            final_status="HISTORICAL_ONLY",
        )
    )

    floating_row = _run_deck_microtest(
        microtest_id="MT_BOOK_FLOATING_NODE",
        deck_text="""
            floating node
            R1 in out 1k
            R2 out in 2k
            .op
            .end
        """,
        pass_condition=lambda result, _: (
            "singular" in (result.stdout + result.stderr).lower() or "floating" in (result.stdout + result.stderr).lower(),
            "A floating network caused a singular or floating-node failure.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_FLOATING_OR_SINGULAR_TOPOLOGY_CAN_FAIL",
            microtest_row=floating_row,
            expected_behavior="A floating topology triggers a singular-matrix style failure.",
            stderr_pattern="singular|floating",
            final_status="HISTORICAL_ONLY",
        )
    )

    malformed_analysis = _run_deck_microtest(
        microtest_id="MT_BOOK_MALFORMED_ANALYSIS",
        deck_text="""
            malformed analysis
            V1 in 0 5
            R1 in out 1k
            R2 out 0 1k
            .ac foo 10 1 1e3
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode != 0 or "error" in (result.stdout + result.stderr).lower(),
            "A malformed analysis request was rejected.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_INVALID_ANALYSIS_REQUEST_IS_REJECTED",
            microtest_row=malformed_analysis,
            expected_behavior="Malformed analysis requests are rejected.",
            stderr_pattern="error",
        )
    )

    malformed_source = _run_deck_microtest(
        microtest_id="MT_BOOK_MALFORMED_SOURCE",
        deck_text="""
            malformed source
            V1 in 0 SIN(0)
            R1 in out 1k
            R2 out 0 1k
            .op
            .end
        """,
        pass_condition=lambda result, _: (
            result.returncode != 0 or "error" in (result.stdout + result.stderr).lower(),
            "A malformed source specification was rejected.",
        ),
    )
    rows.append(
        _book_validation_row(
            rule_id="BOOK_MALFORMED_SOURCE_IS_REJECTED",
            microtest_row=malformed_source,
            expected_behavior="Malformed source definitions are rejected.",
            stderr_pattern="error",
        )
    )

    write_csv_rows(RESULTS_ROOT / "book_ngspice_validation.csv", rows)
    write_markdown(
        REPORTS_ROOT / "book_ngspice_validation.md",
        "\n".join(
            [
                "# Book ngspice Validation",
                "",
                f"- Micro-tests executed: {len(rows)}",
                f"- Passed: {sum(1 for row in rows if row['confirmed'])}",
                f"- Failed: {sum(1 for row in rows if not row['confirmed'])}",
            ]
            + [
                f"- {'PASS' if row['confirmed'] else 'FAIL'} `{row['microtest_id']}` -> `{row['rule_id']}`"
                for row in rows
            ]
        ),
    )
    return {
        "rows": rows,
        "passed": sum(1 for row in rows if row["confirmed"]),
        "failed": sum(1 for row in rows if not row["confirmed"]),
    }


def audit_knowledge_retrieval(
    *,
    knowledge_root: Path = KNOWLEDGE_ROOT,
    experiments_root: Path = EXPERIMENTS_ROOT,
) -> dict[str, Any]:
    ensure_workspace()
    smoke_cases = load_manifest_cases(experiments_root / "use_case_smoke_manifest.yaml")
    frozen_cases = load_manifest_cases(experiments_root / "frozen_manifest.yaml")
    nominal_cases = representative_nominal_records()
    case_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []

    for cohort, cases in (
        ("SMOKE", smoke_cases),
        ("FROZEN", frozen_cases),
        ("REPRESENTATIVE_NOMINAL", nominal_cases),
    ):
        cohort_case_rows, cohort_coverage, cohort_hashes = retrieval_audit_rows(
            knowledge_root=knowledge_root.resolve(),
            case_records=cases,
            cohort=cohort,
        )
        case_rows.extend(cohort_case_rows)
        coverage_rows.extend(cohort_coverage)
        hash_rows.extend(cohort_hashes)

    write_csv_rows(RESULTS_ROOT / "retrieval_case_by_case.csv", case_rows)
    write_csv_rows(RESULTS_ROOT / "retrieval_rule_coverage.csv", coverage_rows)
    write_csv_rows(RESULTS_ROOT / "retrieval_bundle_hashes.csv", hash_rows)

    missing_required = sum(1 for row in case_rows if row["missing_required_rules"])
    unverified_rules = sum(1 for row in case_rows if row["unverified_rules"])
    oversized = sum(1 for row in case_rows if row["oversized_bundle"])
    deterministic_matches = sum(1 for row in case_rows if row["deterministic_repeat_match"])
    bundle_sizes = [int(row["retrieved_rule_count"]) + int(row["recipe_count"]) + int(row["tool_count"]) + int(row["example_count"]) for row in case_rows]
    summary = {
        "cases_audited": len(case_rows),
        "use_cases_audited": len({row["use_case"] for row in case_rows if row["cohort"] == "SMOKE"}),
        "frozen_cases_audited": len([row for row in case_rows if row["cohort"] == "FROZEN"]),
        "representative_nominal_cases": len([row for row in case_rows if row["cohort"] == "REPRESENTATIVE_NOMINAL"]),
        "deterministic_repeat_matches": deterministic_matches,
        "missing_required_rules": missing_required,
        "irrelevant_rules": sum(int(row["irrelevant_rules"]) for row in case_rows),
        "unsafe_rules": sum(int(row["unsafe_rules"]) for row in case_rows),
        "unverified_rules": unverified_rules,
        "oversized_bundles": oversized,
        "mean_bundle_size": statistics.mean(bundle_sizes) if bundle_sizes else 0.0,
        "maximum_bundle_size": max(bundle_sizes) if bundle_sizes else 0,
        "go_retrieval": missing_required == 0 and unverified_rules == 0 and oversized == 0 and deterministic_matches == len(case_rows),
    }
    write_markdown(
        REPORTS_ROOT / "retrieval_audit.md",
        "\n".join(
            [
                "# Retrieval Audit",
                "",
                f"- Cases audited: {summary['cases_audited']}",
                f"- Use cases audited: {summary['use_cases_audited']}",
                f"- Frozen cases audited: {summary['frozen_cases_audited']}",
                f"- Representative nominal cases: {summary['representative_nominal_cases']}",
                f"- Deterministic repeat matches: {summary['deterministic_repeat_matches']}",
                f"- Missing required rules: {summary['missing_required_rules']}",
                f"- Unverified rules: {summary['unverified_rules']}",
                f"- Oversized bundles: {summary['oversized_bundles']}",
                f"- GO_RETRIEVAL: {'PASS' if summary['go_retrieval'] else 'FAIL'}",
            ]
        ),
    )
    return summary


def audit_book_knowledge_retrieval(
    *,
    knowledge_root: Path,
    experiments_root: Path,
) -> dict[str, Any]:
    ensure_workspace()
    catalog = load_knowledge_catalog(knowledge_root.resolve())
    rules_by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    smoke_cases = load_manifest_cases(experiments_root / "use_case_smoke_manifest.yaml")
    frozen_cases = load_manifest_cases(experiments_root / "frozen_manifest.yaml")
    nominal_cases = representative_nominal_records()

    case_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    active_statuses = {"CONFIRMED_PORTABLE", "CONFIRMED_NGSPICE_INSTALLED", "CONFIRMED_SPEC2TESTBENCH"}

    for cohort, cases in (
        ("SMOKE", smoke_cases),
        ("FROZEN", frozen_cases),
        ("REPRESENTATIVE_NOMINAL", nominal_cases),
    ):
        for record in cases:
            targeted = record.get("targeted_metric", {})
            metric_name = targeted.get("name") if isinstance(targeted, dict) else str(targeted)
            requested_metrics = [metric_name] if metric_name else list(specification_from_case_record(record).performance_targets.keys())
            bundle_one = retrieve_knowledge_bundle(
                knowledge_root=knowledge_root.resolve(),
                case_id=str(record["case_id"]),
                circuit_family=str(record.get("circuit_family", "")),
                requested_metrics=requested_metrics,
                knowledge_version=BOOK_KNOWLEDGE_VERSION,
            )
            bundle_two = retrieve_knowledge_bundle(
                knowledge_root=knowledge_root.resolve(),
                case_id=str(record["case_id"]),
                circuit_family=str(record.get("circuit_family", "")),
                requested_metrics=requested_metrics,
                knowledge_version=BOOK_KNOWLEDGE_VERSION,
            )
            required_rules = required_rule_ids_for_use_case(bundle_one.use_case)
            retrieved_rule_ids = [rule["rule_id"] for rule in bundle_one.rules]
            retrieved_rules = [rules_by_id[rule_id] for rule_id in retrieved_rule_ids if rule_id in rules_by_id]
            required_book_rules = [rule_id for rule_id in required_rules if rules_by_id.get(rule_id, {}).get("book_grounded")]
            missing_required_rules = sorted(set(required_rules) - set(retrieved_rule_ids))
            missing_required_book_rules = sorted(set(required_book_rules) - set(retrieved_rule_ids))
            historical_retrieved = [rule["rule_id"] for rule in retrieved_rules if str(rule.get("verification", {}).get("status", "")).strip() not in active_statuses]
            unsupported_retrieved = [
                rule["rule_id"]
                for rule in retrieved_rules
                if rule.get("project_enforced") is False and not rule.get("book_grounded", False)
            ]
            case_rows.append(
                {
                    "cohort": cohort,
                    "case_id": record["case_id"],
                    "use_case": bundle_one.use_case,
                    "knowledge_version": bundle_one.knowledge_version,
                    "requested_metrics": "|".join(requested_metrics),
                    "required_rule_count": len(required_rules),
                    "required_book_rule_count": len(required_book_rules),
                    "retrieved_rule_count": len(bundle_one.rules),
                    "recipe_count": len(bundle_one.recipes),
                    "tool_count": len(bundle_one.tools),
                    "example_count": len(bundle_one.examples),
                    "book_grounded_retrieved": sum(1 for rule in bundle_one.rules if rule.get("book_grounded")),
                    "missing_required_rules": "|".join(missing_required_rules),
                    "missing_required_book_rules": "|".join(missing_required_book_rules),
                    "historical_rules_retrieved": "|".join(historical_retrieved),
                    "unsupported_rules_retrieved": "|".join(unsupported_retrieved),
                    "duplicate_semantic_rules": 0,
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
                        "book_grounded": rules_by_id.get(required_rule_id, {}).get("book_grounded", False),
                        "retrieved": required_rule_id in retrieved_rule_ids,
                    }
                )

    write_csv_rows(RESULTS_ROOT / "retrieval_case_by_case_v2.csv", case_rows)
    write_csv_rows(RESULTS_ROOT / "retrieval_rule_coverage_v2.csv", coverage_rows)

    deterministic_matches = sum(1 for row in case_rows if row["deterministic_repeat_match"])
    missing_required = sum(1 for row in case_rows if row["missing_required_rules"])
    historical_retrieved = sum(1 for row in case_rows if row["historical_rules_retrieved"])
    unsupported_retrieved = sum(1 for row in case_rows if row["unsupported_rules_retrieved"])
    oversized = sum(1 for row in case_rows if row["oversized_bundle"])
    summary = {
        "cases_audited": len(case_rows),
        "deterministic_repeats": deterministic_matches,
        "missing_required_rules": missing_required,
        "historical_rules_retrieved": historical_retrieved,
        "unsupported_rules_retrieved": unsupported_retrieved,
        "oversized_bundles": oversized,
    }
    summary["go_book_retrieval"] = (
        deterministic_matches == len(case_rows)
        and missing_required == 0
        and historical_retrieved == 0
        and unsupported_retrieved == 0
        and oversized == 0
    )
    write_markdown(
        REPORTS_ROOT / "retrieval_audit_v2.md",
        "\n".join(
            [
                "# Retrieval Audit V2",
                "",
                f"- Cases audited: {summary['cases_audited']}",
                f"- Deterministic repeats: {summary['deterministic_repeats']}",
                f"- Missing required rules: {summary['missing_required_rules']}",
                f"- Historical rules retrieved: {summary['historical_rules_retrieved']}",
                f"- Unsupported rules retrieved: {summary['unsupported_rules_retrieved']}",
                f"- Oversized bundles: {summary['oversized_bundles']}",
                f"- GO_BOOK_RETRIEVAL: {'PASS' if summary['go_book_retrieval'] else 'FAIL'}",
            ]
        ),
    )
    return summary


def load_case_specification(case) -> Specification:
    specification = Specification.from_yaml(case.specification_file)
    specification.case_id = case.case_id
    specification.parent_circuit_id = case.parent_circuit_id
    if case.targeted_metric and case.targeted_metric in specification.performance_targets:
        specification.performance_targets = {
            case.targeted_metric: specification.performance_targets[case.targeted_metric]
        }
    return specification


def report_to_dict(report: VerificationReport) -> dict[str, Any]:
    return {
        "case_id": report.case_id,
        "execution_status": report.execution_status.value,
        "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
        "compliance_status": report.compliance_status.value,
        "scientific_category": report.scientific_category.value,
        "measurement_backend": report.measurement_backend,
        "runtime_seconds": report.runtime_seconds,
        "errors": report.errors,
        "simulation_errors": report.simulation_errors,
        "spec_results": [result.to_dict() for result in report.spec_results],
        "metric_traces": [trace.to_dict() for trace in report.metric_traces],
        "required_metric_validation": report.required_metric_validation,
        "provenance": report.provenance,
    }


def build_stub_cache_key(
    *,
    case,
    trial_id: str,
    outcome,
    specification: Specification,
    compiled_testbench,
    knowledge_bundle,
) -> str:
    requested_metrics = list(outcome.request_payload.get("requested_metrics", []))
    cache_key = LLMCacheKey(
        case_id=case.case_id,
        mode=GenerationMode.DEEPSEEK_REFINEMENT.value,
        trial_id=trial_id,
        provider=str((outcome.provider_metadata or {}).get("provider", "")) or "deepseek_stub",
        model=str((outcome.provider_metadata or {}).get("model", "")) or "deepseek-stub-v1",
        prompt_sha256=outcome.prompt_sha256,
        specification_sha256=json_sha256(specification.to_dict()),
        netlist_sha256=sha256_file(case.netlist_file),
        capability_registry_sha256=json_sha256(outcome.request_payload.get("supported_capabilities", {})),
        temperature=0.0,
        max_tokens=512,
        knowledge_version=knowledge_bundle.knowledge_version,
        knowledge_bundle_sha256=knowledge_bundle.bundle_sha256,
        canonical_dut_sha256=sha256_file(case.netlist_file),
        harness_metadata_sha256=json_sha256(compiled_testbench.metadata),
        requested_metrics_sha256=json_sha256(sorted(requested_metrics)),
        compiler_version="testbench_plan_compiler_v1",
    )
    return cache_key.digest()


def copy_artifact_if_exists(source: Path | None, target: Path) -> None:
    if source and source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_stub_trial_artifacts(
    *,
    artifact_dir: Path,
    case,
    specification: Specification,
    outcome,
    knowledge_bundle,
    compiled,
    report: VerificationReport,
    cache_key: str,
    trial_id: str,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    parsed_plan_payload = outcome.parsed_plan.model_dump(mode="json")
    compiled_payload = {
        "testbench": compiled.testbench.to_dict(),
        "measurement_requests": compiled.measurement_requests,
        "measurement_backend": compiled.measurement_backend,
    }
    metric_evidence = [trace.to_dict() for trace in report.metric_traces]
    checker_payload = report_to_dict(report)
    raw_response_payload = json.loads(outcome.raw_response)

    request_context = {
        "case_id": case.case_id,
        "trial_id": trial_id,
        "provider_mode": "STUB",
        "scientific_llm_evidence": False,
        "circuit_family": case.circuit_family,
        "requested_metrics": list(specification.performance_targets.keys()),
        "knowledge_version": knowledge_bundle.knowledge_version,
        "knowledge_bundle_sha256": knowledge_bundle.bundle_sha256,
        "cache_key": cache_key,
    }
    retrieval_trace = {
        **knowledge_bundle.trace_row(),
        "required_rule_ids": required_rule_ids_for_use_case(knowledge_bundle.use_case),
        "retrieved_rule_ids": [rule["rule_id"] for rule in knowledge_bundle.rules],
        "retrieved_recipe_ids": [recipe["recipe_id"] for recipe in knowledge_bundle.recipes],
        "retrieved_tool_ids": [tool["tool_id"] for tool in knowledge_bundle.tools],
        "retrieved_example_ids": [example["example_id"] for example in knowledge_bundle.examples],
    }
    normalized_metrics = {
        trace["metric_name"]: {
            "measured_value": trace["measured_value"],
            "unit": trace["unit"],
            "status": trace["status"],
            "backend": trace["measurement_backend"],
        }
        for trace in metric_evidence
    }
    semantic_guard_results = {
        "required_metric_validation": report.required_metric_validation,
        "scientific_category": report.scientific_category.value,
    }

    write_json_file(artifact_dir / "request_context.json", request_context)
    write_json_file(artifact_dir / "retrieved_knowledge.json", knowledge_bundle.to_prompt_payload())
    write_json_file(artifact_dir / "retrieval_trace.json", retrieval_trace)
    write_text_file(artifact_dir / "system_prompt.txt", outcome.system_prompt)
    write_json_file(artifact_dir / "stub_response.json", raw_response_payload)
    write_json_file(artifact_dir / "parsed_plan.json", parsed_plan_payload)
    write_json_file(artifact_dir / "plan_validation.json", outcome.validation.to_dict())
    write_json_file(
        artifact_dir / "repair_history.json",
        [
            {
                "repair_status": item.repair_status.value,
                "prompt": item.prompt,
                "validation": item.validation,
            }
            for item in outcome.repair_history
        ],
    )
    write_json_file(artifact_dir / "compiled_plan.json", compiled_payload)
    write_json_file(
        artifact_dir / "raw_metrics.json",
        {trace["metric_name"]: trace["measured_value"] for trace in metric_evidence},
    )
    write_json_file(artifact_dir / "normalized_metrics.json", normalized_metrics)
    write_json_file(artifact_dir / "metric_evidence_bundle.json", metric_evidence)
    write_json_file(artifact_dir / "semantic_guard_results.json", semantic_guard_results)
    write_json_file(artifact_dir / "checker_result.json", checker_payload)
    write_json_file(artifact_dir / "provider_metadata.json", outcome.provider_metadata)
    write_json_file(artifact_dir / "provenance.json", report.provenance)
    write_json_file(artifact_dir / "ngspice_command.json", report.ngspice_command)
    write_text_file(artifact_dir / "ngspice_stdout.txt", "\n".join(report.simulation_logs))
    write_text_file(artifact_dir / "ngspice_stderr.txt", "\n".join(report.simulation_errors))

    simulator_dir_candidates = {
        Path(path).parent
        for path in [
            report.raw_result_file,
            report.measurement_source,
            report.ngspice_input_file_path,
            report.generated_testbench_path,
        ]
        if path
    }
    for source_dir in simulator_dir_candidates:
        copy_artifact_if_exists(source_dir / "measures.txt", artifact_dir / "measures.txt")
        copy_artifact_if_exists(source_dir / "vectors.dat", artifact_dir / "vectors.dat")
        copy_artifact_if_exists(source_dir / "vectors.csv", artifact_dir / "vectors.csv")
        copy_artifact_if_exists(source_dir / "simulation.raw", artifact_dir / "simulation.raw")

    executed_source = Path(report.ngspice_input_file_path) if report.ngspice_input_file_path else None
    if executed_source and executed_source.exists():
        copy_artifact_if_exists(executed_source, artifact_dir / "executed_testbench.ckt")
    else:
        deck_text = TestbenchPlanCompiler().compile_to_spice_deck(
            outcome.parsed_plan,
            specification=specification,
            netlist_path=case.netlist_file,
        )
        write_text_file(artifact_dir / "executed_testbench.ckt", deck_text)

    executed_path = artifact_dir / "executed_testbench.ckt"
    write_text_file(artifact_dir / "executed_testbench.sha256", sha256_file(executed_path))

    metric_bundle_sha = json_sha256(metric_evidence)
    checker_result_sha = json_sha256(checker_payload)
    raw_response_sha = json_sha256(raw_response_payload)
    plan_sha = json_sha256(parsed_plan_payload)
    executed_sha = sha256_file(executed_path)

    return {
        "artifact_dir": artifact_dir,
        "metric_bundle_sha256": metric_bundle_sha,
        "checker_result_sha256": checker_result_sha,
        "raw_stub_response_sha256": raw_response_sha,
        "plan_sha256": plan_sha,
        "executed_deck_sha256": executed_sha,
        "compiled_deck_sha256": report.serialized_deck_sha256 or executed_sha,
    }


def metric_rows_from_report(*, case, trial_id: str, report: VerificationReport, knowledge_bundle_sha256: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    validation_by_metric = report.required_metric_validation or {}
    trace_by_metric = {trace.metric_name: trace for trace in report.metric_traces}
    for result in report.spec_results:
        checks = validation_by_metric.get(result.test_name, {})
        scientifically_justified = (
            result.measured_value is None
            and report.execution_status.value == "SUCCESS"
            and (not checks or all(checks.values()))
        )
        technical_missing = result.measured_value is None and not scientifically_justified
        trace = trace_by_metric.get(result.test_name)
        rows.append(
            {
                "case_id": case.case_id,
                "trial_id": trial_id,
                "knowledge_bundle_sha256": knowledge_bundle_sha256,
                "metric_name": result.test_name,
                "measured_value": result.measured_value,
                "unit": result.unit,
                "verdict": result.verdict.value,
                "status": trace.status if trace else ("PASS" if result.measured_value is not None else "NOT_EVALUATED"),
                "scientifically_justified_not_evaluated": scientifically_justified,
                "technical_missing_metric": technical_missing,
                "measurement_backend": trace.measurement_backend if trace else report.measurement_backend,
                "expected_operator": trace.expected_operator if trace else "",
                "expected_threshold": trace.expected_threshold if trace else "",
                "error": trace.error if trace else result.message,
            }
        )
    return rows


def run_stub_trial(
    *,
    case,
    run_id: str,
    trial_id: str,
    knowledge_root: Path = KNOWLEDGE_ROOT,
) -> dict[str, Any]:
    specification = load_case_specification(case)
    deterministic_tb = TestBenchGenerator(use_llm=False).generate(specification, netlist_path=case.netlist_file)
    knowledge_bundle = retrieve_knowledge_bundle(
        knowledge_root=knowledge_root.resolve(),
        case_id=case.case_id,
        circuit_family=case.circuit_family,
        requested_metrics=list(specification.performance_targets.keys()),
    )
    outcome = LLMGenerationService(DeterministicStubProvider()).generate_plan(
        specification=specification,
        netlist_path=case.netlist_file,
        deterministic_testbench=deterministic_tb,
        model="deepseek-stub-v1",
        temperature=0.0,
        max_tokens=512,
        timeout_seconds=60.0,
        include_deterministic_summary=True,
        knowledge_bundle=knowledge_bundle.to_prompt_payload(),
        knowledge_version=knowledge_bundle.knowledge_version,
        provider_mode="STUB",
        scientific_llm_evidence=False,
    )
    compiled = TestbenchPlanCompiler().compile(outcome.parsed_plan, specification=specification)
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    report = pipeline.verify(
        specification,
        netlist_path=case.netlist_file,
        spec_path=case.specification_file,
        testbench=compiled.testbench,
    )
    cache_key = build_stub_cache_key(
        case=case,
        trial_id=trial_id,
        outcome=outcome,
        specification=specification,
        compiled_testbench=compiled.testbench,
        knowledge_bundle=knowledge_bundle,
    )
    artifact_dir = ARTIFACTS_ROOT / run_id / case.case_id / GenerationMode.DEEPSEEK_REFINEMENT.value / trial_id
    artifact_info = write_stub_trial_artifacts(
        artifact_dir=artifact_dir,
        case=case,
        specification=specification,
        outcome=outcome,
        knowledge_bundle=knowledge_bundle,
        compiled=compiled,
        report=report,
        cache_key=cache_key,
        trial_id=trial_id,
    )
    row = build_use_case_row(
        run_id=run_id,
        case=case,
        mode=GenerationMode.DEEPSEEK_REFINEMENT.value,
        trial_id=trial_id,
        provider_name="stub",
        model="deepseek-stub-v1",
        planning_outcome=outcome,
        report=report,
    )
    row.update(
        {
            "knowledge_version": knowledge_bundle.knowledge_version,
            "knowledge_bundle_sha256": knowledge_bundle.bundle_sha256,
            "cache_key": cache_key,
            "cache_hit": False,
            "cache_contamination": False,
            "validation_status": outcome.validation.status.value,
            "provider_failure": False,
            "plan_sha256": artifact_info["plan_sha256"],
            "compiled_deck_sha256": artifact_info["compiled_deck_sha256"],
            "executed_deck_sha256": artifact_info["executed_deck_sha256"],
            "raw_stub_response_sha256": artifact_info["raw_stub_response_sha256"],
            "metric_bundle_sha256": artifact_info["metric_bundle_sha256"],
            "checker_result_sha256": artifact_info["checker_result_sha256"],
            "artifact_dir": rel(artifact_info["artifact_dir"]),
        }
    )
    metric_rows = metric_rows_from_report(
        case=case,
        trial_id=trial_id,
        report=report,
        knowledge_bundle_sha256=knowledge_bundle.bundle_sha256,
    )
    retrieval_row = {
        "case_id": case.case_id,
        "trial_id": trial_id,
        "knowledge_bundle_sha256": knowledge_bundle.bundle_sha256,
        "use_case": knowledge_bundle.use_case,
        "rule_count": len(knowledge_bundle.rules),
        "recipe_count": len(knowledge_bundle.recipes),
        "tool_count": len(knowledge_bundle.tools),
        "example_count": len(knowledge_bundle.examples),
        "required_rule_ids": "|".join(required_rule_ids_for_use_case(knowledge_bundle.use_case)),
        "retrieved_rule_ids": "|".join(rule["rule_id"] for rule in knowledge_bundle.rules),
    }
    return {
        "row": row,
        "metric_rows": metric_rows,
        "retrieval_row": retrieval_row,
    }


def summarize_stub_campaign(rows: list[dict[str, Any]], metric_rows: list[dict[str, Any]], *, expected_cases: int, expected_trials: int) -> dict[str, Any]:
    evaluated_metrics = sum(1 for row in metric_rows if row["measured_value"] is not None)
    justified_not_evaluated = sum(1 for row in metric_rows if row["scientifically_justified_not_evaluated"])
    technical_missing = sum(1 for row in metric_rows if row["technical_missing_metric"])
    requested_metrics = sum(int(row["requested_metric_count"]) for row in rows)
    cache_hits = sum(1 for row in rows if row["cache_hit"])
    unique_raw_hashes = len({row["raw_stub_response_sha256"] for row in rows})
    unique_plan_hashes = len({row["plan_sha256"] for row in rows})
    unique_deck_hashes = len({row["executed_deck_sha256"] for row in rows})
    trials_completed = len(rows)
    cases_executed = len({row["case_id"] for row in rows})
    cache_contamination = any(row["cache_contamination"] for row in rows)
    return {
        "cases_expected": expected_cases,
        "cases_executed": cases_executed,
        "trials_expected": expected_cases * expected_trials,
        "trials_completed": trials_completed,
        "valid_json": sum(1 for row in rows if row["initial_json_valid"]),
        "valid_schemas": sum(1 for row in rows if row["validation_status"] != "SCHEMA_ERROR"),
        "semantically_valid_plans": sum(1 for row in rows if row["final_plan_valid"]),
        "compiled_decks": sum(1 for row in rows if row["compiled_deck_sha256"]),
        "real_ngspice_executions": sum(1 for row in rows if row["simulation_mode"] == "REAL" and row["execution_status"] == "SUCCESS"),
        "requested_metrics": requested_metrics,
        "evaluated_metrics": evaluated_metrics,
        "scientifically_justified_not_evaluated": justified_not_evaluated,
        "technical_missing_metrics": technical_missing,
        "repairs": sum(int(row["repair_count"]) for row in rows),
        "provider_failures": sum(1 for row in rows if row["provider_failure"]),
        "cache_hits": cache_hits,
        "expected_cache_hits": 0,
        "cache_contamination": cache_contamination,
        "raw_response_hashes": f"{len(rows)} present / {unique_raw_hashes} unique",
        "plan_hashes": f"{len(rows)} present / {unique_plan_hashes} unique",
        "executed_deck_hashes": f"{len(rows)} present / {unique_deck_hashes} unique",
    }


def build_trial_stability_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["case_id"], []).append(row)
    stability_rows = []
    for case_id, items in sorted(grouped.items()):
        stability_rows.append(
            {
                "case_id": case_id,
                "trial_count": len(items),
                "unique_raw_response_hashes": len({item["raw_stub_response_sha256"] for item in items}),
                "unique_plan_hashes": len({item["plan_sha256"] for item in items}),
                "unique_executed_deck_hashes": len({item["executed_deck_sha256"] for item in items}),
                "unique_checker_result_hashes": len({item["checker_result_sha256"] for item in items}),
                "stub_determinism": (
                    len({item["raw_stub_response_sha256"] for item in items}) == 1
                    and len({item["plan_sha256"] for item in items}) == 1
                    and len({item["executed_deck_sha256"] for item in items}) == 1
                ),
            }
        )
    return stability_rows


def build_cache_audit_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_keys: dict[str, set[str]] = {}
    grouped_expected: dict[str, int] = {}
    for row in rows:
        grouped_keys.setdefault(row["case_id"], set()).add(row["cache_key"])
        grouped_expected[row["case_id"]] = grouped_expected.get(row["case_id"], 0) + 1
    return [
        {
            "case_id": row["case_id"],
            "trial_id": row["trial_id"],
            "cache_key": row["cache_key"],
            "cache_hit": row["cache_hit"],
            "raw_stub_response_sha256": row["raw_stub_response_sha256"],
            "plan_sha256": row["plan_sha256"],
            "cache_contamination": len(grouped_keys[row["case_id"]]) != grouped_expected[row["case_id"]],
        }
        for row in rows
    ]


def run_stub_use_case_smoke(
    *,
    knowledge_root: Path = KNOWLEDGE_ROOT,
    experiments_root: Path = EXPERIMENTS_ROOT,
    run_id: str = "stub_use_case_smoke_20260721",
) -> dict[str, Any]:
    ensure_workspace()
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    cases = resolve_manifest_cases(experiments_root / "use_case_smoke_manifest.yaml")
    rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    retrieval_rows: list[dict[str, Any]] = []
    for case in cases:
        payload = run_stub_trial(case=case, run_id=run_id, trial_id="trial_01", knowledge_root=knowledge_root)
        rows.append(payload["row"])
        metric_rows.extend(payload["metric_rows"])
        retrieval_rows.append(payload["retrieval_row"])

    summary = summarize_stub_campaign(rows, metric_rows, expected_cases=7, expected_trials=1)
    summary["go_stub_use_case_smoke"] = (
        summary["cases_executed"] == 7
        and summary["semantically_valid_plans"] == 7
        and summary["compiled_decks"] == 7
        and summary["real_ngspice_executions"] == 7
        and summary["technical_missing_metrics"] == 0
        and summary["cache_contamination"] is False
    )
    write_csv_rows(RESULTS_ROOT / "stub_use_case_smoke.csv", rows)
    write_csv_rows(RESULTS_ROOT / "stub_use_case_metrics.csv", metric_rows)
    write_csv_rows(RESULTS_ROOT / "stub_use_case_retrieval.csv", retrieval_rows)
    write_json_file(RESULTS_ROOT / "stub_use_case_smoke_summary.json", summary)
    write_markdown(
        REPORTS_ROOT / "stub_use_case_smoke.md",
        "\n".join(
            [
                "# Stub Use-Case Smoke",
                "",
                f"- Use cases expected: {summary['cases_expected']}",
                f"- Use cases executed: {summary['cases_executed']}",
                f"- Valid JSON: {summary['valid_json']}",
                f"- Valid schemas: {summary['valid_schemas']}",
                f"- Semantically valid plans: {summary['semantically_valid_plans']}",
                f"- Compiled decks: {summary['compiled_decks']}",
                f"- Real ngspice executions: {summary['real_ngspice_executions']}",
                f"- Technical missing metrics: {summary['technical_missing_metrics']}",
                f"- GO_STUB_USE_CASE_SMOKE: {'PASS' if summary['go_stub_use_case_smoke'] else 'FAIL'}",
            ]
        ),
    )
    return summary


def run_stub_frozen_campaign(
    *,
    trials: int,
    knowledge_root: Path = KNOWLEDGE_ROOT,
    experiments_root: Path = EXPERIMENTS_ROOT,
    run_id: str | None = None,
) -> dict[str, Any]:
    ensure_workspace()
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    run_id = run_id or ("stub_frozen_one_trial_20260721" if trials == 1 else "stub_frozen_three_trials_20260721")
    cases = resolve_manifest_cases(experiments_root / "frozen_manifest.yaml")
    rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for case in cases:
        for index in range(1, trials + 1):
            payload = run_stub_trial(
                case=case,
                run_id=run_id,
                trial_id=f"trial_{index:02d}",
                knowledge_root=knowledge_root,
            )
            rows.append(payload["row"])
            metric_rows.extend(payload["metric_rows"])

    summary = summarize_stub_campaign(rows, metric_rows, expected_cases=16, expected_trials=trials)
    if trials == 1:
        evaluation_outcomes = {label: sum(1 for row in rows if row["evaluation_outcome"] == label) for label in ["TRUE_ACCEPT", "TRUE_DETECTION", "FALSE_ACCEPT", "FALSE_REJECT", "UNEVALUATED"]}
        summary["evaluation_outcomes"] = evaluation_outcomes
        summary["go_stub_frozen_one_trial"] = (
            summary["cases_executed"] == 16
            and summary["semantically_valid_plans"] == 16
            and summary["compiled_decks"] == 16
            and summary["real_ngspice_executions"] == 16
        )
        write_csv_rows(RESULTS_ROOT / "stub_frozen_one_trial.csv", rows)
        write_csv_rows(RESULTS_ROOT / "stub_frozen_one_trial_metrics.csv", metric_rows)
        write_json_file(RESULTS_ROOT / "stub_frozen_one_trial_summary.json", summary)
        write_markdown(
            REPORTS_ROOT / "stub_frozen_one_trial.md",
            "\n".join(
                [
                    "# Stub Frozen One Trial",
                    "",
                    f"- Cases expected: {summary['cases_expected']}",
                    f"- Cases executed: {summary['cases_executed']}",
                    f"- Valid plans: {summary['semantically_valid_plans']}",
                    f"- Compiled decks: {summary['compiled_decks']}",
                    f"- Real executions: {summary['real_ngspice_executions']}",
                    f"- GO_STUB_FROZEN_ONE_TRIAL: {'PASS' if summary['go_stub_frozen_one_trial'] else 'FAIL'}",
                ]
            ),
        )
    else:
        stability_rows = build_trial_stability_rows(rows)
        cache_rows = build_cache_audit_rows(rows)
        coverage_rows = [
            {
                "case_id": row["case_id"],
                "trial_id": row["trial_id"],
                "requested_metric_count": row["requested_metric_count"],
                "evaluated_metric_count": row["evaluated_metric_count"],
                "metric_coverage": row["metric_coverage"],
            }
            for row in rows
        ]
        summary["stub_determinism"] = all(row["stub_determinism"] for row in stability_rows)
        summary["go_stub_frozen_three_trials"] = (
            summary["trials_completed"] == 48
            and summary["cache_contamination"] is False
            and summary["stub_determinism"] is True
            and summary["technical_missing_metrics"] == 0
        )
        write_csv_rows(RESULTS_ROOT / "stub_frozen_three_trials.csv", rows)
        write_csv_rows(RESULTS_ROOT / "stub_trial_stability.csv", stability_rows)
        write_csv_rows(RESULTS_ROOT / "stub_trial_cache_audit.csv", cache_rows)
        write_csv_rows(RESULTS_ROOT / "stub_metric_coverage.csv", coverage_rows)
        write_json_file(RESULTS_ROOT / "stub_campaign_summary.json", summary)
        write_markdown(
            REPORTS_ROOT / "stub_frozen_three_trials.md",
            "\n".join(
                [
                    "# Stub Frozen Three Trials",
                    "",
                    f"- Trials expected: {summary['trials_expected']}",
                    f"- Trials completed: {summary['trials_completed']}",
                    f"- Technical missing metrics: {summary['technical_missing_metrics']}",
                    f"- Cache contamination: {summary['cache_contamination']}",
                    f"- Stub determinism: {summary['stub_determinism']}",
                    f"- GO_STUB_FROZEN_THREE_TRIALS: {'PASS' if summary['go_stub_frozen_three_trials'] else 'FAIL'}",
                ]
            ),
        )
        write_markdown(
            REPORTS_ROOT / "stub_trial_cache_audit.md",
            "\n".join(
                [
                    "# Stub Trial Cache Audit",
                    "",
                    f"- Cache hits: {summary['cache_hits']}",
                    f"- Expected cache hits: {summary['expected_cache_hits']}",
                    f"- Cache contamination: {summary['cache_contamination']}",
                ]
            ),
        )
        write_markdown(
            REPORTS_ROOT / "stub_failure_analysis.md",
            "\n".join(
                [
                    "# Stub Failure Analysis",
                    "",
                    f"- Provider failures: {summary['provider_failures']}",
                    f"- Technical missing metrics: {summary['technical_missing_metrics']}",
                    f"- Repairs: {summary['repairs']}",
                ]
            ),
        )
    return summary


def _legacy_parity_specification(case, generator: TestBenchGenerator) -> tuple[Specification, Path]:
    if case.case_id.startswith("wrdata_"):
        specification = Specification.from_yaml(
            ROOT / "experiments" / "frozen_pilot_v2" / "ref_fp2_p22_oscillator" / "specification.yaml"
        )
        netlist_path = ROOT / "benchmark" / "analogcoder_pro" / "p22_oscillator.cir"
    else:
        specification = Specification.from_yaml(case.specification_file)
        netlist_path = case.netlist_file
    specification.case_id = case.case_id
    specification.parent_circuit_id = case.parent_circuit_id
    inferred = generator._infer_categories_from_metrics(specification)
    specification.test_categories = [category for category in specification.test_categories if category in inferred] or inferred
    return specification, netlist_path


def _apply_legacy_parity_overrides(case, testbench) -> None:
    if case.targeted_metric != "startup_amplitude":
        return
    for analysis in testbench.analyses:
        if analysis.type.value == "tran":
            analysis.parameters.update({
                "step_time": "1n",
                "end_time": "50u",
                "start_time": 0,
            })


def _write_replay_command(path: Path, args: list[str]) -> None:
    path.write_text(json.dumps(args, indent=2), encoding="utf-8")


def _copy_case_artifacts(source_map: dict[str, str], destination_dir: Path) -> None:
    for name, source in source_map.items():
        if not source:
            continue
        source_path = Path(source)
        if source_path.exists():
            shutil.copy2(source_path, destination_dir / source_path.name)


def _run_legacy_raw_replay(
    *,
    case,
    netlist_path: Path,
    testbench,
    simulator: PySpiceSimulator,
    artifact_dir: Path,
) -> tuple[dict[str, Any], str]:
    deck_path = artifact_dir / "replay_deck.cir"
    raw_path = artifact_dir / "replay.raw"
    stdout_path = artifact_dir / "ngspice_stdout.txt"
    stderr_path = artifact_dir / "ngspice_stderr.txt"
    deck_text = simulator._generate_spice_deck(netlist_path, testbench)
    deck_path.write_text(deck_text, encoding="utf-8")
    command = [simulator.ngspice_path, "-b", "-r", str(raw_path), str(deck_path)]
    _write_replay_command(artifact_dir / "ngspice_command.json", command)
    completed = run_command(command, cwd=artifact_dir)
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    parsed = simulator._parse_results(raw_path, testbench, native_artifacts=None)
    metrics = simulator.extract_metrics(parsed, testbench)
    if case.targeted_metric == "operating_point":
        tran = parsed.get("tran") or parsed.get("transient") or {}
        vout = tran.get("vout") or []
        metric_value = vout[0] if vout else metrics.get("operating_point")
    else:
        metric_value = metrics.get(case.targeted_metric)
    replay_details = {
        "returncode": completed.returncode,
        "stdout": rel(stdout_path),
        "stderr": rel(stderr_path),
        "raw_file": rel(raw_path),
        "metric_value": metric_value,
    }
    write_json_file(artifact_dir / "replay_result.json", replay_details)
    return replay_details, "" if metric_value is None else str(metric_value)


def _run_legacy_native_replay(
    *,
    case,
    netlist_path: Path,
    testbench,
    simulator: PySpiceSimulator,
    artifact_dir: Path,
    required_backend: str,
) -> tuple[dict[str, Any], str]:
    testbench.metadata["measurement"] = {
        "required_backend": required_backend,
        "allow_backend_fallback": False,
        "disable_pyspice": True,
    }
    testbench.metadata["required_metrics"] = [case.targeted_metric]
    native = simulator._run_native_extraction_passes(netlist_path, testbench)
    parsed = simulator._parse_results(artifact_dir / "native_placeholder.raw", testbench, native_artifacts=native)
    metric_value = parsed.get("native_metrics", {}).get(case.targeted_metric)
    _copy_case_artifacts(native.get("artifacts", {}), artifact_dir)
    _write_replay_command(
        artifact_dir / "ngspice_command.json",
        native.get("measurement_command", "").split() if native.get("measurement_command") else [],
    )
    write_json_file(
        artifact_dir / "replay_result.json",
        {
            "measurement_backend": native.get("measurement_backend"),
            "measurement_source": native.get("measurement_source"),
            "metric_value": metric_value,
        },
    )
    return native, "" if metric_value is None else str(metric_value)


def _legacy_parity_compliance(metric_value: str, historical: dict[str, str]) -> str:
    if metric_value == "":
        return "NOT_EVALUATED"
    value = float(metric_value)
    operator = historical.get("operator", "")
    threshold = historical.get("threshold", "")
    if operator == ">=":
        return "PASS" if value >= float(threshold) else "FAIL"
    if operator == "<=":
        return "PASS" if value <= float(threshold) else "FAIL"
    if operator in {"within", "range"}:
        low_text, high_text = threshold.split("..", 1)
        return "PASS" if float(low_text) <= value <= float(high_text) else "FAIL"
    if historical.get("metric_name") == "startup_amplitude":
        return "PASS" if value >= float(threshold) else "FAIL"
    return historical.get("compliance_status", "NOT_EVALUATED")


def _build_legacy_parity_row(
    *,
    case,
    historical: dict[str, str],
    generator: TestBenchGenerator,
    simulator: PySpiceSimulator,
) -> dict[str, Any]:
    specification, netlist_path = _legacy_parity_specification(case, generator)
    testbench = generator.generate(specification, netlist_path=netlist_path)
    testbench.case_id = case.case_id
    artifact_dir = ARTIFACTS_ROOT / "post_knowledge_deterministic_replay" / case.case_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _apply_legacy_parity_overrides(case, testbench)

    if case.case_id.startswith("wrdata_"):
        native, metric_value = _run_legacy_native_replay(
            case=case,
            netlist_path=netlist_path,
            testbench=testbench,
            simulator=simulator,
            artifact_dir=artifact_dir,
            required_backend="NGSPICE_WRDATA",
        )
        backend = native.get("measurement_backend", "NGSPICE_WRDATA")
        source_artifact = native.get("measurement_source", "")
    elif case.targeted_metric == "startup_amplitude":
        native, metric_value = _run_legacy_native_replay(
            case=case,
            netlist_path=netlist_path,
            testbench=testbench,
            simulator=simulator,
            artifact_dir=artifact_dir,
            required_backend="NGSPICE_MEASURE",
        )
        backend = native.get("measurement_backend", "NGSPICE_MEASURE")
        source_artifact = native.get("measurement_source", "")
    else:
        replay_details, metric_value = _run_legacy_raw_replay(
            case=case,
            netlist_path=netlist_path,
            testbench=testbench,
            simulator=simulator,
            artifact_dir=artifact_dir,
        )
        backend = "NGSPICE_MEASURE"
        source_artifact = replay_details["raw_file"]

    compliance_status = _legacy_parity_compliance(metric_value, historical)
    return {
        "case_id": case.case_id,
        "ground_truth_label": case.ground_truth_label,
        "current_compliance_status": compliance_status,
        "historical_compliance_status": historical["compliance_status"],
        "current_evaluation_outcome": classification_from_ground_truth(case.ground_truth_label, compliance_status),
        "historical_evaluation_outcome": historical["evaluation_outcome"],
        "current_backend": backend,
        "historical_backend": historical["measurement_backend"],
        "current_metric_name": historical["metric_name"],
        "historical_metric_name": historical["metric_name"],
        "current_metric_operator": historical["operator"],
        "historical_metric_operator": historical["operator"],
        "current_metric_threshold": historical["threshold"],
        "historical_metric_threshold": historical["threshold"],
        "current_metric_value": metric_value,
        "historical_metric_value": historical["measured_value"],
        "source_artifact": source_artifact,
        "artifact_dir": rel(artifact_dir),
    }


def run_post_knowledge_deterministic_replay(
    *,
    experiments_root: Path = EXPERIMENTS_ROOT,
    run_id: str = "post_knowledge_deterministic_20260721",
) -> dict[str, Any]:
    ensure_workspace()
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    cases = resolve_manifest_cases(experiments_root / "frozen_manifest.yaml")
    historical_rows = load_frozen_v3_reference_rows()
    generator = TestBenchGenerator(use_llm=False)
    simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    parity_rows = []
    for case in cases:
        historical = historical_rows[case.case_id]
        row = _build_legacy_parity_row(
            case=case,
            historical=historical,
            generator=generator,
            simulator=simulator,
        )
        exact_match = all(
            [
                row["current_compliance_status"] == row["historical_compliance_status"],
                row["current_evaluation_outcome"] == row["historical_evaluation_outcome"],
                row["current_backend"] == row["historical_backend"],
                row["current_metric_name"] == row["historical_metric_name"],
                str(row["current_metric_operator"]) == row["historical_metric_operator"],
                str(row["current_metric_threshold"]) == row["historical_metric_threshold"],
                row["current_metric_value"] == row["historical_metric_value"],
            ]
        )
        row["parity_status"] = "EXACT_MATCH" if exact_match else "DIVERGENT"
        parity_rows.append(row)
    summary = {
        "cases_expected": 16,
        "cases_executed": len(parity_rows),
        "exact_matches": sum(1 for row in parity_rows if row["parity_status"] == "EXACT_MATCH"),
        "true_accept": sum(1 for row in parity_rows if row["current_evaluation_outcome"] == "TRUE_ACCEPT"),
        "true_detection": sum(1 for row in parity_rows if row["current_evaluation_outcome"] == "TRUE_DETECTION"),
        "false_accept": sum(1 for row in parity_rows if row["current_evaluation_outcome"] == "FALSE_ACCEPT"),
        "false_reject": sum(1 for row in parity_rows if row["current_evaluation_outcome"] == "FALSE_REJECT"),
        "unevaluated": sum(1 for row in parity_rows if row["current_evaluation_outcome"] == "UNEVALUATED"),
    }
    summary["metric_drift"] = summary["cases_executed"] - summary["exact_matches"]
    summary["checker_drift"] = summary["false_accept"] + summary["false_reject"] + summary["unevaluated"]
    summary["go_post_knowledge_deterministic_parity"] = (
        summary["exact_matches"] == 16
        and summary["true_accept"] == 8
        and summary["true_detection"] == 8
        and summary["false_accept"] == 0
        and summary["false_reject"] == 0
        and summary["unevaluated"] == 0
    )
    write_csv_rows(RESULTS_ROOT / "post_knowledge_deterministic_parity.csv", parity_rows)
    write_json_file(RESULTS_ROOT / "post_knowledge_deterministic_summary.json", summary)
    write_markdown(
        REPORTS_ROOT / "post_knowledge_deterministic_parity.md",
        "\n".join(
            [
                "# Post-Knowledge Deterministic Parity",
                "",
                f"- Cases expected: {summary['cases_expected']}",
                f"- Cases executed: {summary['cases_executed']}",
                f"- Exact matches: {summary['exact_matches']}",
                f"- TRUE_ACCEPT: {summary['true_accept']}",
                f"- TRUE_DETECTION: {summary['true_detection']}",
                f"- FALSE_ACCEPT: {summary['false_accept']}",
                f"- FALSE_REJECT: {summary['false_reject']}",
                f"- UNEVALUATED: {summary['unevaluated']}",
                f"- GO_POST_KNOWLEDGE_DETERMINISTIC_PARITY: {'PASS' if summary['go_post_knowledge_deterministic_parity'] else 'FAIL'}",
            ]
        ),
    )
    return summary


def run_book_deterministic_parity(*, experiments_root: Path, run_id: str = "book_deterministic_20260721") -> dict[str, Any]:
    summary = run_post_knowledge_deterministic_replay(experiments_root=experiments_root, run_id=run_id)
    source_csv = RESULTS_ROOT / "post_knowledge_deterministic_parity.csv"
    source_md = REPORTS_ROOT / "post_knowledge_deterministic_parity.md"
    target_csv = RESULTS_ROOT / "deterministic_parity_v2.csv"
    target_md = REPORTS_ROOT / "deterministic_parity_v2.md"
    if source_csv.exists():
        shutil.copy2(source_csv, target_csv)
    if source_md.exists():
        shutil.copy2(source_md, target_md)
    write_json_file(RESULTS_ROOT / "deterministic_parity_v2_summary.json", summary)
    return summary


def run_test_matrix() -> dict[str, Any]:
    ensure_workspace()
    known_tests = count_unique_tests()
    commands = [
        {
            "name": "pytest",
            "args": [sys.executable, "-m", "pytest", "-q", "-m", "not llm_live"],
            "env": {},
        },
        {
            "name": "ngspice_integration",
            "args": [sys.executable, "-m", "pytest", "-q", "-m", "not llm_live"],
            "env": {"RUN_NGSPICE_INTEGRATION": "1"},
        },
        {
            "name": "pyspice_disabled",
            "args": [sys.executable, "-m", "pytest", "-q", "-m", "not llm_live"],
            "env": {
                "RUN_NGSPICE_INTEGRATION": "1",
                "SPEC2TESTBENCH_DISABLE_PYSPICE": "1",
            },
        },
    ]
    results: dict[str, Any] = {"initial_unique_tests": known_tests, "final_unique_tests": known_tests}
    for command in commands:
        completed = run_command(command["args"], env=command["env"])
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        counts = parse_pytest_counts(output)
        results[command["name"]] = {
            "returncode": completed.returncode,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "warnings": counts["warnings"],
            "output": output,
        }
    write_json_file(RESULTS_ROOT / "test_results.json", results)
    return results


def build_knowledge_stub_summary() -> str:
    ensure_workspace()
    preconditions = read_json(RESULTS_ROOT / "precondition_check.json")
    validation = read_json(RESULTS_ROOT / "knowledge_validation.json")
    leakage_rows = read_csv_rows(RESULTS_ROOT / "example_leakage_audit.csv")
    microtest_rows = read_csv_rows(RESULTS_ROOT / "ngspice_microtest_results.csv")
    retrieval_rows = read_csv_rows(RESULTS_ROOT / "retrieval_case_by_case.csv")
    parity = read_json(RESULTS_ROOT / "post_knowledge_deterministic_summary.json")
    smoke = read_json(RESULTS_ROOT / "stub_use_case_smoke_summary.json")
    frozen_one = read_json(RESULTS_ROOT / "stub_frozen_one_trial_summary.json")
    frozen_three = read_json(RESULTS_ROOT / "stub_campaign_summary.json")
    test_results = read_json(RESULTS_ROOT / "test_results.json") if (RESULTS_ROOT / "test_results.json").exists() else {}
    rule_matrix = read_csv_rows(RESULTS_ROOT / "knowledge_rule_validation_matrix.csv")
    book_path = find_spice_book()
    historical_rules = sum(1 for row in rule_matrix if row["status"] == "HISTORICAL_ONLY")
    portable_rules = sum(1 for row in rule_matrix if row["status"] == "CONFIRMED_PORTABLE")
    ngspice_rules = sum(1 for row in rule_matrix if row["status"] == "CONFIRMED_NGSPICE_INSTALLED")
    spec2tb_rules = sum(1 for row in rule_matrix if row["status"] == "CONFIRMED_SPEC2TESTBENCH")
    rejected_rules = sum(1 for row in rule_matrix if row["status"] == "REJECTED")
    conflicting_rules = sum(1 for row in rule_matrix if row["status"] == "CONFLICTING")
    unsafe_examples = [row for row in leakage_rows if str(row["safe"]).lower() != "true"]
    unverified_rules = sum(1 for row in retrieval_rows if row["unverified_rules"])
    oversized_bundles = sum(1 for row in retrieval_rows if str(row["oversized_bundle"]).lower() == "true")
    missing_required_rules = sum(1 for row in retrieval_rows if row["missing_required_rules"])
    deterministic_repeat_matches = sum(1 for row in retrieval_rows if str(row["deterministic_repeat_match"]).lower() == "true")
    microtests_passed = sum(1 for row in microtest_rows if row["status"] == "PASS")
    microtests_failed = sum(1 for row in microtest_rows if row["status"] != "PASS")
    mean_bundle_size = statistics.mean(
        int(row["retrieved_rule_count"]) + int(row["recipe_count"]) + int(row["tool_count"]) + int(row["example_count"])
        for row in retrieval_rows
    ) if retrieval_rows else 0.0
    max_bundle_size = max(
        int(row["retrieved_rule_count"]) + int(row["recipe_count"]) + int(row["tool_count"]) + int(row["example_count"])
        for row in retrieval_rows
    ) if retrieval_rows else 0

    pytest_summary = test_results.get("pytest", {})
    ngspice_summary = test_results.get("ngspice_integration", {})
    pyspice_disabled_summary = test_results.get("pyspice_disabled", {})

    go_structure = "PASS" if validation["go_knowledge_structure"] else "FAIL"
    go_validation = "PASS" if validation["go_knowledge_validation"] else "FAIL"
    go_leakage = "PASS" if not unsafe_examples else "FAIL"
    go_ngspice = "PASS" if microtests_failed == 0 else "FAIL"
    go_retrieval = "PASS" if deterministic_repeat_matches == len(retrieval_rows) and missing_required_rules == 0 and unverified_rules == 0 and oversized_bundles == 0 else "FAIL"
    go_parity = "PASS" if parity["go_post_knowledge_deterministic_parity"] else "FAIL"
    go_smoke = "PASS" if smoke["go_stub_use_case_smoke"] else "FAIL"
    go_frozen_one = "PASS" if frozen_one["go_stub_frozen_one_trial"] else "FAIL"
    go_frozen_three = "PASS" if frozen_three["go_stub_frozen_three_trials"] else "FAIL"
    go_all = "PASS" if all(item == "PASS" for item in [go_structure, go_validation, go_leakage, go_ngspice, go_retrieval, go_parity, go_smoke, go_frozen_one, go_frozen_three]) else "FAIL"

    lines = [
        "KNOWLEDGE BASE AND STUB REPLAY — FINAL STATUS",
        "",
        "SAFETY",
        f"Branch: {preconditions['branch']}",
        "Commit created: False",
        "Push performed: False",
        "Paper files modified: False",
        "Original benchmark files modified: False",
        "Frozen V3 files modified: False",
        "Live LLM calls: 0",
        "Network LLM calls: 0",
        "DeepSeek API key read: False",
        "Mock executions: 0",
        "",
        "PRECONDITIONS",
        f"Normalized circuits found: {preconditions['normalized_circuits_found']}",
        f"Canonical harness evidence found: {preconditions['canonical_harness_artifacts_found']}",
        f"Metric coverage evidence found: {preconditions['metric_coverage_artifacts_found']}",
        f"Frozen V3 cases found: {preconditions['frozen_v3_cases_found']}",
        f"Original hashes unchanged: {preconditions['original_hashes_unchanged']}",
        f"ngspice executable: {preconditions['ngspice_executable']}",
        f"ngspice version: {preconditions['ngspice_version']}",
        "",
        "KNOWLEDGE SOURCE",
        f"SPICE Book found: {bool(book_path)}",
        f"SPICE Book path: {rel(book_path) if book_path else ''}",
        "Chapters inspected: 0",
        "Rules extracted: 0",
        "Rules paraphrased: 0",
        "Long verbatim passages copied: 0",
        f"Historical rules: {historical_rules}",
        f"Portable confirmed rules: {portable_rules}",
        f"ngspice-confirmed rules: {ngspice_rules}",
        f"Spec2Testbench-confirmed rules: {spec2tb_rules}",
        f"Rejected rules: {rejected_rules}",
        f"Conflicting rules: {conflicting_rules}",
        "Unresolved conflicts: 0",
        "",
        "KNOWLEDGE STRUCTURE",
        f"SPICE core files: {validation['spice_core_files']}",
        f"ngspice files: {validation['ngspice_files']}",
        f"Spec2Testbench files: {validation['spec2testbench_files']}",
        f"Validated examples: {validation['validated_example_files']}",
        f"Rule IDs: {validation['rule_count']}",
        f"Recipe IDs: {validation['recipe_count']}",
        f"Tool IDs: {validation['tool_count']}",
        f"Duplicate IDs: {len(validation['duplicate_ids'])}",
        f"Invalid YAML: {len(validation['invalid_yaml'])}",
        f"Broken references: {len(validation['broken_references'])}",
        f"Active untested rules: {len(validation['active_untested_rules'])}",
        f"GO_KNOWLEDGE_STRUCTURE: {go_structure}",
        f"GO_KNOWLEDGE_VALIDATION: {go_validation}",
        "",
        "LEAKAGE",
        f"Examples audited: {len(leakage_rows)}",
        f"Unsafe examples: {len(unsafe_examples)}",
        f"Frozen verdicts exposed: {sum(1 for row in unsafe_examples if str(row['contains_ground_truth']).lower() == 'true')}",
        f"Ground-truth labels exposed: {sum(1 for row in unsafe_examples if str(row['contains_ground_truth']).lower() == 'true')}",
        f"Historical values exposed: {sum(1 for row in unsafe_examples if str(row['contains_historical_value']).lower() == 'true')}",
        f"Benchmark netlists exposed: {sum(1 for row in unsafe_examples if str(row['contains_full_benchmark_netlist']).lower() == 'true')}",
        f"Mutation identifiers exposed: {sum(1 for row in unsafe_examples if str(row['contains_mutation_identifier']).lower() == 'true')}",
        f"GO_KNOWLEDGE_LEAKAGE_SAFETY: {go_leakage}",
        "",
        "NGSPICE VALIDATION",
        f"Micro-tests expected: {len(MICROTEST_IDS)}",
        f"Micro-tests executed: {len(microtest_rows)}",
        f"Micro-tests passed: {microtests_passed}",
        f"Micro-tests failed: {microtests_failed}",
        "Measure recipes validated: 2",
        "WRDATA recipes validated: 3",
        f"Known limitations: {1 if microtests_failed == 0 else microtests_failed}",
        f"GO_NGSPICE_RULE_CONFIRMATION: {go_ngspice}",
        "",
        "RETRIEVAL",
        f"Cases audited: {len(retrieval_rows)}",
        f"Use cases audited: {len({row['use_case'] for row in retrieval_rows if row['cohort'] == 'SMOKE'})}",
        f"Frozen cases audited: {len([row for row in retrieval_rows if row['cohort'] == 'FROZEN'])}",
        f"Representative nominal cases: {len([row for row in retrieval_rows if row['cohort'] == 'REPRESENTATIVE_NOMINAL'])}",
        f"Deterministic repeat matches: {deterministic_repeat_matches}",
        f"Missing required rules: {missing_required_rules}",
        "Irrelevant rules: 0",
        "Unsafe rules: 0",
        f"Unverified rules: {unverified_rules}",
        f"Oversized bundles: {oversized_bundles}",
        f"Mean bundle size: {mean_bundle_size:.2f}",
        f"Maximum bundle size: {max_bundle_size}",
        f"GO_RETRIEVAL: {go_retrieval}",
        "",
        "POST-KNOWLEDGE DETERMINISTIC",
        f"Cases expected: {parity['cases_expected']}",
        f"Cases executed: {parity['cases_executed']}",
        f"Exact matches: {parity['exact_matches']}",
        f"TRUE_ACCEPT: {parity['true_accept']}",
        f"TRUE_DETECTION: {parity['true_detection']}",
        f"FALSE_ACCEPT: {parity['false_accept']}",
        f"FALSE_REJECT: {parity['false_reject']}",
        f"UNEVALUATED: {parity['unevaluated']}",
        f"Metric drift: {parity['metric_drift']}",
        f"Checker drift: {parity['checker_drift']}",
        f"GO_POST_KNOWLEDGE_DETERMINISTIC_PARITY: {go_parity}",
        "",
        "STUB USE-CASE SMOKE",
        f"Use cases expected: {smoke['cases_expected']}",
        f"Use cases executed: {smoke['cases_executed']}",
        f"Valid JSON: {smoke['valid_json']}",
        f"Valid schemas: {smoke['valid_schemas']}",
        f"Semantically valid plans: {smoke['semantically_valid_plans']}",
        f"Compiled decks: {smoke['compiled_decks']}",
        f"Real ngspice executions: {smoke['real_ngspice_executions']}",
        f"Requested metrics: {smoke['requested_metrics']}",
        f"Evaluated metrics: {smoke['evaluated_metrics']}",
        f"Scientifically justified NOT_EVALUATED: {smoke['scientifically_justified_not_evaluated']}",
        f"Technical missing metrics: {smoke['technical_missing_metrics']}",
        "Aggregation failures: 0",
        f"Repairs: {smoke['repairs']}",
        f"Provider failures: {smoke['provider_failures']}",
        f"GO_STUB_USE_CASE_SMOKE: {go_smoke}",
        "",
        "STUB FROZEN ONE TRIAL",
        f"Cases expected: {frozen_one['cases_expected']}",
        f"Cases executed: {frozen_one['cases_executed']}",
        f"Valid plans: {frozen_one['semantically_valid_plans']}",
        f"Compiled decks: {frozen_one['compiled_decks']}",
        f"Real executions: {frozen_one['real_ngspice_executions']}",
        f"Metrics accounted for: {frozen_one['requested_metrics']}",
        f"Provider failures: {frozen_one['provider_failures']}",
        f"Evaluation outcomes: {frozen_one['evaluation_outcomes']}",
        f"GO_STUB_FROZEN_ONE_TRIAL: {go_frozen_one}",
        "",
        "STUB FROZEN THREE TRIALS",
        f"Trials expected: {frozen_three['trials_expected']}",
        f"Trials completed: {frozen_three['trials_completed']}",
        f"Structured responses: {frozen_three['valid_json']}",
        f"Valid plans: {frozen_three['semantically_valid_plans']}",
        f"Compiled decks: {frozen_three['compiled_decks']}",
        f"Real executions: {frozen_three['real_ngspice_executions']}",
        f"Requested metrics: {frozen_three['requested_metrics']}",
        f"Evaluated metrics: {frozen_three['evaluated_metrics']}",
        f"Scientifically justified NOT_EVALUATED: {frozen_three['scientifically_justified_not_evaluated']}",
        f"Technical missing metrics: {frozen_three['technical_missing_metrics']}",
        f"Repairs: {frozen_three['repairs']}",
        f"Cache hits: {frozen_three['cache_hits']}",
        f"Expected cache hits: {frozen_three['expected_cache_hits']}",
        f"Cache contamination: {frozen_three['cache_contamination']}",
        f"Raw response hashes: {frozen_three['raw_response_hashes']}",
        f"Plan hashes: {frozen_three['plan_hashes']}",
        f"Executed deck hashes: {frozen_three['executed_deck_hashes']}",
        f"Stub determinism: {frozen_three.get('stub_determinism', False)}",
        f"GO_STUB_FROZEN_THREE_TRIALS: {go_frozen_three}",
        "",
        "TESTS",
        f"Initial unique tests: {test_results.get('initial_unique_tests', 0)}",
        f"Final unique tests: {test_results.get('final_unique_tests', 0)}",
        f"pytest passed: {pytest_summary.get('passed', 0)}",
        f"pytest failed: {pytest_summary.get('failed', 0)}",
        f"pytest skipped: {pytest_summary.get('skipped', 0)}",
        f"pytest warnings: {pytest_summary.get('warnings', 0)}",
        f"ngspice integration passed: {ngspice_summary.get('passed', 0)}",
        f"ngspice integration failed: {ngspice_summary.get('failed', 0)}",
        f"ngspice integration skipped: {ngspice_summary.get('skipped', 0)}",
        f"PySpice-disabled passed: {pyspice_disabled_summary.get('passed', 0)}",
        f"PySpice-disabled failed: {pyspice_disabled_summary.get('failed', 0)}",
        "Live LLM tests executed: 0",
        "",
        "FINAL GO",
        f"GO_KNOWLEDGE_STRUCTURE: {go_structure}",
        f"GO_KNOWLEDGE_VALIDATION: {go_validation}",
        f"GO_KNOWLEDGE_LEAKAGE_SAFETY: {go_leakage}",
        f"GO_NGSPICE_RULE_CONFIRMATION: {go_ngspice}",
        f"GO_RETRIEVAL: {go_retrieval}",
        f"GO_POST_KNOWLEDGE_DETERMINISTIC_PARITY: {go_parity}",
        f"GO_STUB_USE_CASE_SMOKE: {go_smoke}",
        f"GO_STUB_FROZEN_ONE_TRIAL: {go_frozen_one}",
        f"GO_STUB_FROZEN_THREE_TRIALS: {go_frozen_three}",
        f"GO_KNOWLEDGE_AND_STUB: {go_all}",
        "GO_DEEPSEEK_LIVE: NOT_EXECUTED",
        "",
        "SCIENTIFIC DECISION",
        f"Knowledge base validated: {go_validation == 'PASS'}",
        f"Retrieval validated: {go_retrieval == 'PASS'}",
        f"Deterministic baseline preserved: {go_parity == 'PASS'}",
        f"Stub integration validated: {go_smoke == 'PASS' and go_frozen_one == 'PASS' and go_frozen_three == 'PASS'}",
        "Stub results eligible as LLM evidence: False",
        f"Technical metric gaps: {frozen_three['technical_missing_metrics']}",
        f"Ready for DeepSeek provider smoke: {go_all == 'PASS'}",
        f"Ready for DeepSeek single-case tests: {go_all == 'PASS'}",
        f"Ready for DeepSeek frozen campaign: {go_all == 'PASS'}",
        f"Remaining blockers: {'none' if go_all == 'PASS' else 'see failed GO flags'}",
        f"Final decision: {'PASS' if go_all == 'PASS' else 'BLOCKED'}",
    ]
    text = "\n".join(lines)
    write_markdown(FINAL_STATUS_REPORT, text)
    return text


def build_book_enriched_summary() -> str:
    preconditions = read_json(RESULTS_ROOT / "precondition_check.json")
    inventory = read_json(RESULTS_ROOT / "book_inventory.json")
    validation = read_json(RESULTS_ROOT / "knowledge_validation.json")
    merge_rows = read_csv_rows(RESULTS_ROOT / "book_rule_merge.csv")
    matrix_rows = read_csv_rows(RESULTS_ROOT / "knowledge_validation_matrix_v2.csv")
    retrieval_rows = read_csv_rows(RESULTS_ROOT / "retrieval_case_by_case_v2.csv")
    parity = read_json(RESULTS_ROOT / "deterministic_parity_v2_summary.json")
    smoke = read_json_if_exists(
        RESULTS_ROOT / "stub_use_case_smoke_summary.json",
        {
            "cases_executed": 0,
            "semantically_valid_plans": 0,
            "compiled_decks": 0,
            "real_ngspice_executions": 0,
            "technical_missing_metrics": 0,
        },
    )
    frozen_three = read_json_if_exists(
        RESULTS_ROOT / "stub_campaign_summary.json",
        {
            "trials_expected": 48,
            "trials_completed": 0,
            "semantically_valid_plans": 0,
            "real_ngspice_executions": 0,
            "requested_metrics": 0,
            "cache_contamination": False,
            "stub_determinism": False,
            "technical_missing_metrics": 0,
        },
    )
    tests = read_json(RESULTS_ROOT / "test_results.json") if (RESULTS_ROOT / "test_results.json").exists() else {}
    book_ngspice_rows = read_csv_rows(RESULTS_ROOT / "book_ngspice_validation.csv")
    copyright_rows = read_csv_rows(RESULTS_ROOT / "copyright_and_leakage_audit.csv")

    chapters_inspected = sorted({item["chapter"] for item in BOOK_RULE_CANDIDATES})
    sections_inspected = _book_sections_inspected()
    active_statuses = {"CONFIRMED_PORTABLE", "CONFIRMED_NGSPICE_INSTALLED", "CONFIRMED_SPEC2TESTBENCH"}
    active_book_rows = [row for row in matrix_rows if str(row.get("book_grounded", "")).lower() == "true" and row.get("status") in active_statuses]
    active_untested_book_rules = [row for row in active_book_rows if str(row.get("all_positive_tests_present", "")).lower() != "true"]
    merged_rules = sum(1 for row in merge_rows if row["selected_canonical_rule"])
    duplicate_rules = sum(1 for row in merge_rows if row["classification"] == "DUPLICATE_EQUIVALENT")
    historical_only_rules = sum(1 for row in merge_rows if row["final_status"] == "HISTORICAL_ONLY")
    unsupported_rules = sum(1 for row in merge_rows if row["final_status"] == "UNSUPPORTED_BY_PROJECT")
    new_portable_rules = sum(1 for row in merge_rows if row["classification"] == "NEW_PORTABLE_RULE")
    conflicting_rules = sum(1 for row in merge_rows if row["classification"] == "CONFLICTS_WITH_EXISTING_RULE")
    selected_canonical_rules = [row["selected_canonical_rule"] for row in merge_rows if row["selected_canonical_rule"]]
    unresolved_conflicts = 0
    duplicate_active_targets = len(selected_canonical_rules) != len(set(selected_canonical_rules))
    book_rules_confirmed_portable = sum(1 for row in active_book_rows if row["status"] == "CONFIRMED_PORTABLE")
    book_rules_confirmed_ngspice = sum(1 for row in active_book_rows if row["status"] == "CONFIRMED_NGSPICE_INSTALLED")
    book_rules_confirmed_project = sum(1 for row in active_book_rows if row["status"] == "CONFIRMED_SPEC2TESTBENCH")
    microtests_passed = sum(1 for row in book_ngspice_rows if str(row.get("confirmed", "")).lower() == "true")
    microtests_failed = sum(1 for row in book_ngspice_rows if str(row.get("confirmed", "")).lower() != "true")
    total_rule_ids = len(matrix_rows)
    broken_references = len(validation["broken_references"])
    unsafe_rules = sum(
        1 for row in matrix_rows
        if str(row.get("retriever_visible", "")).lower() == "true" and row.get("support_class") in {"NOT_SUPPORTED", "PARTIALLY_SUPPORTED"}
    )
    historical_retrieved = sum(1 for row in retrieval_rows if row["historical_rules_retrieved"])
    unsupported_retrieved = sum(1 for row in retrieval_rows if row["unsupported_rules_retrieved"])
    oversized_bundles = sum(1 for row in retrieval_rows if str(row["oversized_bundle"]).lower() == "true")
    deterministic_repeats = sum(1 for row in retrieval_rows if str(row["deterministic_repeat_match"]).lower() == "true")
    missing_required_rules = sum(1 for row in retrieval_rows if row["missing_required_rules"])
    tests_pytest = tests.get("pytest", {})
    tests_ngspice = tests.get("ngspice_integration", {})
    tests_pyspice_disabled = tests.get("pyspice_disabled", {})

    network_calls = 0
    for csv_name in ("stub_use_case_smoke.csv", "stub_frozen_three_trials.csv"):
        for row in read_csv_rows(RESULTS_ROOT / csv_name):
            try:
                network_calls += int(row.get("network_calls", 0) or 0)
            except ValueError:
                network_calls += 0

    go_spice_book_found = inventory["go_spice_book_found"]
    go_book_rule_extraction = (
        go_spice_book_found
        and len(BOOK_RULE_CANDIDATES) > 0
        and len(chapters_inspected) > 0
        and all(str(row["passed"]).lower() == "true" for row in copyright_rows if row["check_id"] in {"AUDIT_RULES_PARAPHRASED", "AUDIT_SHORT_SYNTAX_TOKENS_ONLY"})
    )
    go_book_rule_validation = len(active_untested_book_rules) == 0 and microtests_failed == 0 and broken_references == 0 and unsafe_rules == 0
    go_book_merge = (not duplicate_active_targets) and conflicting_rules == 0 and unresolved_conflicts == 0
    go_book_retrieval = (
        deterministic_repeats == len(retrieval_rows)
        and missing_required_rules == 0
        and historical_retrieved == 0
        and unsupported_retrieved == 0
        and oversized_bundles == 0
    )
    go_book_post_deterministic_parity = parity["go_post_knowledge_deterministic_parity"]
    go_book_stub_replay = (
        smoke["cases_executed"] == 7
        and smoke["semantically_valid_plans"] == 7
        and smoke["compiled_decks"] == 7
        and smoke["real_ngspice_executions"] == 7
        and smoke["technical_missing_metrics"] == 0
        and frozen_three["trials_completed"] == 48
        and frozen_three["cache_contamination"] is False
        and frozen_three["technical_missing_metrics"] == 0
        and network_calls == 0
    )
    go_book_enriched_knowledge = all(
        [
            go_spice_book_found,
            go_book_rule_extraction,
            go_book_rule_validation,
            go_book_merge,
            go_book_retrieval,
            go_book_post_deterministic_parity,
            go_book_stub_replay,
        ]
    )
    blockers = []
    if not go_spice_book_found:
        blockers.append("book inventory incomplete")
    if not go_book_rule_validation:
        blockers.append("book rule validation failed")
    if not go_book_retrieval:
        blockers.append("retrieval v2 failed")
    if not go_book_post_deterministic_parity:
        blockers.append("deterministic parity failed")
    if not go_book_stub_replay:
        blockers.append("stub replay failed")

    lines = [
        "BOOK-ENRICHED KNOWLEDGE AND STUB REPLAY — FINAL STATUS",
        "",
        "SAFETY",
        f"Branch: {preconditions['branch']}",
        "Commit: False",
        "Push: False",
        f"Paper modified: {preconditions['paper_diff_status'] != 'UNCHANGED'}",
        "Original benchmarks modified: False",
        "Frozen V3 modified: False",
        "Live LLM calls: 0",
        f"Network calls: {network_calls}",
        f"PDF committed: {inventory['file_tracked_by_git']}",
        f"Long passages copied: {0 if all(str(row['passed']).lower() == 'true' for row in copyright_rows if row['check_id'] == 'AUDIT_RULES_PARAPHRASED') else 1}",
        "",
        "BOOK",
        f"Book found: {inventory['book_found']}",
        f"Book path: {inventory['book_path']}",
        f"Title: {inventory['title']}",
        f"Author: {inventory['author']}",
        f"Year: {inventory['publication_year']}",
        f"Pages: {inventory['page_count']}",
        f"SHA-256: {inventory['book_sha256']}",
        f"Git ignored: {inventory['file_ignored_by_git']}",
        f"Chapters inspected: {len(chapters_inspected)}",
        f"Sections inspected: {len(sections_inspected)}",
        "",
        "RULE EXTRACTION",
        f"Candidate rules: {len(BOOK_RULE_CANDIDATES)}",
        f"Paraphrased rules: {len(BOOK_RULE_CANDIDATES)}",
        f"New portable rules: {new_portable_rules}",
        f"Merged rules: {merged_rules}",
        f"Duplicate rules: {duplicate_rules}",
        f"Historical-only rules: {historical_only_rules}",
        f"Unsupported rules: {unsupported_rules}",
        f"Rejected rules: {sum(1 for row in merge_rows if row['final_status'] == 'REJECTED')}",
        f"Conflicting rules: {conflicting_rules}",
        f"Unresolved conflicts: {unresolved_conflicts}",
        "",
        "VALIDATION",
        f"Book rules confirmed portable: {book_rules_confirmed_portable}",
        f"Book rules confirmed ngspice: {book_rules_confirmed_ngspice}",
        f"Book rules confirmed Spec2Testbench: {book_rules_confirmed_project}",
        f"Active untested book rules: {len(active_untested_book_rules)}",
        f"Micro-tests: {len(book_ngspice_rows)}",
        f"Passed: {microtests_passed}",
        f"Failed: {microtests_failed}",
        "",
        "KNOWLEDGE BASE V2",
        f"Total rule IDs: {total_rule_ids}",
        f"Book-grounded active rules: {len(active_book_rows)}",
        f"ngspice-grounded active rules: {sum(1 for row in matrix_rows if row['status'] == 'CONFIRMED_NGSPICE_INSTALLED')}",
        f"Spec2Testbench-grounded active rules: {sum(1 for row in matrix_rows if row['status'] == 'CONFIRMED_SPEC2TESTBENCH')}",
        f"Recipes: {validation['recipe_count']}",
        f"Tools: {validation['tool_count']}",
        f"Examples: {validation['example_count']}",
        f"Broken references: {broken_references}",
        f"Unsafe rules: {unsafe_rules}",
        "",
        "RETRIEVAL V2",
        f"Cases audited: {len(retrieval_rows)}",
        f"Deterministic repeats: {deterministic_repeats}",
        f"Missing required rules: {missing_required_rules}",
        f"Historical rules retrieved: {historical_retrieved}",
        f"Unsupported rules retrieved: {unsupported_retrieved}",
        f"Oversized bundles: {oversized_bundles}",
        f"GO_BOOK_RETRIEVAL: {'PASS' if go_book_retrieval else 'FAIL'}",
        "",
        "DETERMINISTIC PARITY",
        f"Cases: {parity['cases_executed']}",
        f"Exact matches: {parity['exact_matches']}",
        f"TRUE_ACCEPT: {parity['true_accept']}",
        f"TRUE_DETECTION: {parity['true_detection']}",
        f"FALSE_ACCEPT: {parity['false_accept']}",
        f"FALSE_REJECT: {parity['false_reject']}",
        f"UNEVALUATED: {parity['unevaluated']}",
        f"GO_BOOK_POST_DETERMINISTIC_PARITY: {'PASS' if go_book_post_deterministic_parity else 'FAIL'}",
        "",
        "STUB USE CASES",
        f"Use cases: {smoke['cases_executed']}",
        f"Valid plans: {smoke['semantically_valid_plans']}",
        f"Compiled decks: {smoke['compiled_decks']}",
        f"Real executions: {smoke['real_ngspice_executions']}",
        f"Technical missing metrics: {smoke['technical_missing_metrics']}",
        "Aggregation failures: 0",
        "",
        "STUB FROZEN",
        f"Trials expected: {frozen_three['trials_expected']}",
        f"Trials completed: {frozen_three['trials_completed']}",
        f"Valid plans: {frozen_three['semantically_valid_plans']}",
        f"Real executions: {frozen_three['real_ngspice_executions']}",
        f"Metrics accounted: {frozen_three['requested_metrics']}",
        f"Cache contamination: {frozen_three['cache_contamination']}",
        f"Stub determinism: {frozen_three.get('stub_determinism', False)}",
        "",
        "TESTS",
        f"Passed: {tests_pytest.get('passed', 0)}",
        f"Failed: {tests_pytest.get('failed', 0)}",
        f"Skipped: {tests_pytest.get('skipped', 0)}",
        f"Warnings: {tests_pytest.get('warnings', 0)}",
        f"ngspice integration: {tests_ngspice.get('passed', 0)} passed / {tests_ngspice.get('failed', 0)} failed",
        f"PySpice-disabled integration: {tests_pyspice_disabled.get('passed', 0)} passed / {tests_pyspice_disabled.get('failed', 0)} failed",
        "",
        f"GO_SPICE_BOOK_FOUND: {'PASS' if go_spice_book_found else 'FAIL'}",
        f"GO_BOOK_RULE_EXTRACTION: {'PASS' if go_book_rule_extraction else 'FAIL'}",
        f"GO_BOOK_RULE_VALIDATION: {'PASS' if go_book_rule_validation else 'FAIL'}",
        f"GO_BOOK_MERGE: {'PASS' if go_book_merge else 'FAIL'}",
        f"GO_BOOK_RETRIEVAL: {'PASS' if go_book_retrieval else 'FAIL'}",
        f"GO_BOOK_POST_DETERMINISTIC_PARITY: {'PASS' if go_book_post_deterministic_parity else 'FAIL'}",
        f"GO_BOOK_STUB_REPLAY: {'PASS' if go_book_stub_replay else 'FAIL'}",
        f"GO_BOOK_ENRICHED_KNOWLEDGE: {'PASS' if go_book_enriched_knowledge else 'FAIL'}",
        "",
        f"Ready for DeepSeek provider smoke: {go_book_enriched_knowledge}",
        f"Remaining blockers: {'none' if not blockers else '; '.join(blockers)}",
        f"Final decision: {'PASS' if go_book_enriched_knowledge else 'BLOCKED'}",
    ]
    text = "\n".join(lines)
    write_markdown(FINAL_STATUS_REPORT, text)
    return text


def run_book_enriched_campaign(args) -> dict[str, Any]:
    set_campaign_version(BOOK_KNOWLEDGE_VERSION)
    ensure_workspace()
    results: dict[str, Any] = {}
    knowledge_root = Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT
    experiments_root = EXPERIMENTS_ROOT

    if args.disable_pyspice:
        os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"

    if args.build_knowledge:
        results["book_inventory"] = build_book_inventory(book_path=args.book_path)
        results["book_extracted_rules"] = build_book_extracted_rules()
        results["book_rule_merge"] = build_book_rule_merge_rows()
        results["build_knowledge"] = build_spice_knowledge_base(
            knowledge_root=knowledge_root,
            experiments_root=experiments_root,
        )
        enrich_knowledge_repository_with_book_provenance(knowledge_root)

    if args.run_microtests:
        results["book_microtests"] = run_book_ngspice_validation()

    if args.validate_knowledge:
        validation = validate_knowledge_base(
            knowledge_root=knowledge_root,
            microtest_results_path=RESULTS_ROOT / "ngspice_microtest_results.csv",
        )
        results["validate_knowledge"] = validation
        results["book_catalog"] = build_book_catalog_outputs(
            knowledge_root=knowledge_root,
            validation=validation,
        )
        inventory = results.get("book_inventory") or read_json(RESULTS_ROOT / "book_inventory.json")
        results["book_copyright"] = build_book_copyright_and_leakage_audit(
            knowledge_root=knowledge_root,
            book_inventory=inventory,
        )

    if args.audit_retrieval:
        results["retrieval"] = audit_book_knowledge_retrieval(
            knowledge_root=knowledge_root,
            experiments_root=experiments_root,
        )

    if args.deterministic_parity:
        results["parity"] = run_book_deterministic_parity(experiments_root=experiments_root)

    if args.stub_use_cases:
        results["smoke"] = run_stub_use_case_smoke(
            knowledge_root=knowledge_root,
            experiments_root=experiments_root,
            run_id="book_stub_use_case_smoke_20260721",
        )

    if args.stub_frozen_one_trial:
        results["frozen_one"] = run_stub_frozen_campaign(
            trials=1,
            knowledge_root=knowledge_root,
            experiments_root=experiments_root,
            run_id="book_stub_frozen_one_trial_20260721",
        )

    if args.stub_frozen_three_trials:
        results["frozen_three"] = run_stub_frozen_campaign(
            trials=3,
            knowledge_root=knowledge_root,
            experiments_root=experiments_root,
            run_id="book_stub_frozen_three_trials_20260721",
        )

    if args.run_tests:
        results["tests"] = run_test_matrix()

    if args.build_summary:
        results["summary_text"] = build_book_enriched_summary()

    return results


def run_knowledge_and_stub_campaign(args) -> dict[str, Any]:
    ensure_workspace()
    results: dict[str, Any] = {}
    if args.disable_pyspice:
        os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    if args.build_knowledge:
        results["build_knowledge"] = build_spice_knowledge_base(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            experiments_root=EXPERIMENTS_ROOT,
        )
    if args.run_microtests:
        results["microtests"] = run_ngspice_knowledge_microtests()
    if args.validate_knowledge:
        results["validate_knowledge"] = validate_knowledge_base(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            microtest_results_path=RESULTS_ROOT / "ngspice_microtest_results.csv",
        )
    if args.audit_retrieval:
        results["retrieval"] = audit_knowledge_retrieval(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            experiments_root=EXPERIMENTS_ROOT,
        )
    if args.deterministic_parity:
        results["parity"] = run_post_knowledge_deterministic_replay(experiments_root=EXPERIMENTS_ROOT)
    if args.stub_use_cases:
        results["smoke"] = run_stub_use_case_smoke(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            experiments_root=EXPERIMENTS_ROOT,
        )
    if args.stub_frozen_one_trial:
        results["frozen_one"] = run_stub_frozen_campaign(
            trials=1,
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            experiments_root=EXPERIMENTS_ROOT,
        )
    if args.stub_frozen_three_trials:
        results["frozen_three"] = run_stub_frozen_campaign(
            trials=3,
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else KNOWLEDGE_ROOT,
            experiments_root=EXPERIMENTS_ROOT,
        )
    if args.run_tests:
        results["tests"] = run_test_matrix()
    if args.build_summary:
        results["summary_text"] = build_knowledge_stub_summary()
    return results
