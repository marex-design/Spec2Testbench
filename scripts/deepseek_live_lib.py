from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from pydantic.version import VERSION as PYDANTIC_VERSION

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spec2testbench.application.ports.llm_provider import LLMProviderError, LLMRequest
from spec2testbench.application.services.llm_generation_service import LLMGenerationService
from spec2testbench.application.services.spice_knowledge import retrieve_knowledge_bundle
from spec2testbench.application.services.testbench_plan_compiler import TestbenchPlanCompiler
from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan
from spec2testbench.infrastructure.llm.deepseek_provider import (
    LEGACY_DEEPSEEK_ALIASES,
    DeepSeekProvider,
    DeepSeekProviderConfig,
)


CAMPAIGN_NAME = "deepseek_live_v1"
CAMPAIGN_SALT = os.getenv("DEEPSEEK_CAMPAIGN_SALT", CAMPAIGN_NAME)
CAMPAIGN_PROTOCOL_DATE = "2026-07-22"
KNOWLEDGE_VERSION = "knowledge_book_v1"
PROMPT_VERSION = "deepseek_testbench_planner_book_v1"
PROMPT_PATH = ROOT / "spec2testbench/infrastructure/llm/prompts/deepseek_testbench_planner_book_v1.txt"
RESPONSE_SCHEMA_VERSION = "testbench_plan_v1_compat"
PROVIDER_SMOKE_PROMPT_VERSION = "deepseek_provider_smoke_v1"
PROVIDER_SMOKE_RESPONSE_SCHEMA_VERSION = "provider_smoke_response_v1"
COMPILER_VERSION = "testbench_plan_compiler_v1"
CHECKER_VERSION = "verification_pipeline_v1"
RETRIEVER_VERSION = "deterministic_book_retriever_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
RUN_RESULTS_DIR = RESULTS_DIR / "runs"
RUN_REPORTS_DIR = REPORTS_DIR / "runs"
KNOWLEDGE_ROOT = ROOT / "knowledge"
LEGACY_USE_CASE_MANIFEST = ROOT / "experiments/llm_deepseek/use_case_smoke_manifest.yaml"
LEGACY_FROZEN_MANIFEST = ROOT / "experiments/llm_deepseek/frozen_manifest.yaml"
DETERMINISTIC_REFERENCE_CSV = ROOT / "results/knowledge_book_v1/deterministic_parity_v2.csv"
STUB_REFERENCE_CSV = ROOT / "results/knowledge_book_v1/stub_frozen_three_trials.csv"
PROMPT_AUDIT_CSV = RESULTS_DIR / "prompt_leakage_audit.csv"
LIVE_BUDGET_CSV = RESULTS_DIR / "live_budget_tracking.csv"
LIVE_CALL_AUDIT_CSV = RESULTS_DIR / "live_call_audit.csv"
FINAL_SUMMARY_JSON = RESULTS_DIR / "deepseek_live_campaign_summary.json"
FINAL_STATUS_MD = REPORTS_DIR / "final_status.md"
PRE_LIVE_WORKTREE_BLOCKER = REPORTS_DIR / "pre_live_worktree_blocker.md"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
ENV_EXAMPLE_AUDIT_JSON = RESULTS_DIR / "env_example_audit.json"
ENV_EXAMPLE_AUDIT_MD = REPORTS_DIR / "env_example_audit.md"
PRE_COMMIT_INVENTORY_CSV = RESULTS_DIR / "pre_commit_inventory.csv"
PRE_COMMIT_INVENTORY_MD = REPORTS_DIR / "pre_commit_inventory.md"
CLEAN_COMMIT_MANIFEST_CSV = RESULTS_DIR / "clean_commit_manifest.csv"
CLEAN_COMMIT_PLAN_MD = REPORTS_DIR / "clean_commit_plan.md"
OFFLINE_TEST_MATRIX_JSON = RESULTS_DIR / "offline_test_matrix.json"
PROVIDER_SMOKE_PROMPT_PATH = ROOT / "spec2testbench/infrastructure/llm/prompts/deepseek_provider_smoke_v1.txt"

STAGE_ORDER = [
    "model_discovery",
    "provider_smoke",
    "single_ac",
    "single_transient",
    "single_oscillator",
    "single_schmitt",
    "use_case_smoke",
    "frozen_protocol_freeze",
    "frozen_trial_1",
    "frozen_trials_2_3",
    "post_live_deterministic",
    "final_summary",
]

GROUND_TRUTH_TOKENS = {
    "GROUND_TRUTH_COMPLIANT",
    "GROUND_TRUTH_NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
    "UNEVALUATED",
}
ALLOWED_PRELIVE_ARTIFACT_ROOTS = (
    "artifacts/deepseek_live_v1/",
    "results/deepseek_live_v1/",
    "reports/deepseek_live_v1/",
)
FREEZE_SENSITIVE_ROOTS = (
    "spec2testbench/",
    "scripts/",
    "tests/",
    "knowledge/",
    "benchmark/",
    "experiments/frozen_pilot_v3/",
)
PLACEHOLDER_SECRET_WORDS = {
    "your",
    "deepseek",
    "openai",
    "google",
    "gemini",
    "anthropic",
    "api",
    "key",
    "token",
    "placeholder",
    "example",
    "here",
    "set",
    "me",
    "value",
}
ENV_ASSIGNMENT_RE = re.compile(
    r"^[ \t]*DEEPSEEK_API_KEY[ \t]*=[ \t]*(?P<value>[^\r\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)
AUTHORIZATION_HEADER_RE = re.compile(
    r"Authorization['\"]?\s*[:=]\s*['\"]?\s*Bearer\s+(?P<value>[^\s'\",}]+)",
    re.IGNORECASE,
)
BEARER_TOKEN_RE = re.compile(r"\bBearer\s+(?P<value>[^\s'\",}]+)", re.IGNORECASE)
API_KEY_LITERAL_RE = re.compile(r"\bapi_key\b\s*[:=]\s*['\"](?P<value>[^'\"]+)['\"]", re.IGNORECASE)
SK_TOKEN_RE = re.compile(r"\b(?P<value>sk-[A-Za-z0-9._-]{8,})\b")
SCANNABLE_SUFFIXES = {".py", ".ps1", ".json", ".md", ".txt", ".yaml", ".yml", ".csv", ".env", ".example"}
REVIEWABLE_PRELIVE_ARTIFACT_NAMES = {
    "clean_commit_manifest.csv",
    "clean_commit_plan.md",
    "env_example_audit.json",
    "env_example_audit.md",
    "final_status.md",
    "pre_commit_inventory.csv",
    "pre_commit_inventory.md",
    "pre_live_manifest.json",
    "pre_live_manifest.md",
    "pre_live_worktree_blocker.md",
    "secret_audit.json",
    "secret_audit.md",
}
PROMPT_AUDIT_SENSITIVE_KEYS = {
    "benchmark_case_id",
    "deterministic_result",
    "expected_outcome",
    "expected_verdict",
    "ground_truth",
    "ground_truth_label",
    "historical_metric",
    "historical_outcome",
    "historical_verdict",
    "internal_case_id",
    "local_path",
    "mutation_id",
    "mutation_label",
    "original_case_id",
    "reference_metric",
    "reference_outcome",
    "reference_testbench",
    "reference_verdict",
    "scientific_category_expected",
    "source_file_path",
    "stub_result",
}
PROMPT_AUDIT_GROUND_TRUTH_KEYS = {"ground_truth", "ground_truth_label"}
PROMPT_AUDIT_HISTORICAL_VERDICT_KEYS = {
    "deterministic_result",
    "expected_outcome",
    "expected_verdict",
    "historical_outcome",
    "historical_verdict",
    "reference_outcome",
    "reference_verdict",
    "scientific_category_expected",
    "stub_result",
}
PROMPT_AUDIT_HISTORICAL_METRIC_KEYS = {"historical_metric", "reference_metric"}
PROMPT_AUDIT_MUTATION_KEYS = {"mutation_id", "mutation_label"}
PROMPT_AUDIT_BENCHMARK_KEYS = {"benchmark_case_id", "internal_case_id", "original_case_id", "reference_testbench"}
PROMPT_AUDIT_LOCAL_PATH_KEYS = {"local_path", "source_file_path"}
PROMPT_AUDIT_SENSITIVE_VALUE_TOKENS = {
    "COMPLIANT_REFERENCE",
    "CONTROLLED_VIOLATION",
    "FALSE_ACCEPT",
    "FALSE_REJECT",
    "SIMULABLE_COMPLIANT",
    "SIMULABLE_NONCOMPLIANT",
    "TRUE_ACCEPT",
    "TRUE_DETECTION",
}
PROMPT_AUDIT_HISTORY_METRIC_TOKENS = {"HISTORICAL_METRIC", "MEASURED_VALUE"}
PROMPT_AUDIT_GENERIC_POLICY_TERMS = {
    "benchmark",
    "compliance",
    "expected outcome",
    "ground truth",
    "historical",
    "mutation",
    "outcome",
    "verdict",
}
PROMPT_AUDIT_NEGATIVE_PREFIX_RE = re.compile(r"\b(do not|don't|must never|must not|never|without)\b", re.IGNORECASE)
PROMPT_AUDIT_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>"
    + "|".join(sorted(re.escape(key) for key in PROMPT_AUDIT_SENSITIVE_KEYS))
    + r")\b\s*[:=]\s*[^\s\]}]+",
    re.IGNORECASE,
)
PROMPT_AUDIT_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:\b[A-Z]:[\\/]|file://|/home/|/users/|/mnt/)"
)
PROMPT_AUDIT_MUTATION_VALUE_RE = re.compile(r"\b(?:FP\d+_CV_\d+|CV[_-]?\d+|WRDATA_[A-Z0-9_]+)\b", re.IGNORECASE)
PROMPT_AUDIT_BENCHMARK_VALUE_RE = re.compile(
    r"\b(?:analogcoder[-_ ]?pro|frozen(?:[_ -]?pilot)?(?:[_ -]?v?3)?|p(?:0[1-9]|1\d|2[0-8])(?:_[a-z0-9_]+)?|smoke_p\d{2}_[a-z0-9_]+)\b",
    re.IGNORECASE,
)
PROMPT_AUDIT_DRIVE_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/]")
PROMPT_AUDIT_SAFE_RELATIVE_PATH_PREFIXES = ("analysis/", "knowledge/", "rule/")
PROVIDER_SMOKE_BLOCKER_ANALYSIS_JSON = RESULTS_DIR / "provider_smoke_blocker_analysis.json"
PROVIDER_SMOKE_BLOCKER_ANALYSIS_MD = REPORTS_DIR / "provider_smoke_blocker_analysis.md"
PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON = RESULTS_DIR / "provider_smoke_sanitized_payload.json"
PROVIDER_SMOKE_EXPECTED_SHAPE_JSON = RESULTS_DIR / "provider_smoke_expected_shape.json"
PROVIDER_SMOKE_JSON_SCHEMA_JSON = RESULTS_DIR / "provider_smoke_json_schema.json"
PROVIDER_SMOKE_VALIDATION_INVENTORY_CSV = RESULTS_DIR / "provider_smoke_validation_inventory.csv"
PROVIDER_SMOKE_VALIDATION_INVENTORY_MD = REPORTS_DIR / "provider_smoke_validation_inventory.md"
PROVIDER_SMOKE_SCHEMA_ERRORS_JSON = RESULTS_DIR / "provider_smoke_schema_errors.json"
PROVIDER_SMOKE_SCHEMA_ERRORS_CSV = RESULTS_DIR / "provider_smoke_schema_errors.csv"
PROVIDER_SMOKE_SCHEMA_ERRORS_MD = REPORTS_DIR / "provider_smoke_schema_errors.md"
PROVIDER_SMOKE_ROOT_CAUSE_JSON = RESULTS_DIR / "provider_smoke_root_cause.json"
PROVIDER_SMOKE_ROOT_CAUSE_MD = REPORTS_DIR / "provider_smoke_root_cause.md"
PROVIDER_SMOKE_FIX_COMMIT_MANIFEST_CSV = RESULTS_DIR / "provider_smoke_fix_commit_manifest.csv"
PROVIDER_SMOKE_FIX_COMMIT_PLAN_MD = REPORTS_DIR / "provider_smoke_fix_commit_plan.md"


@dataclass(frozen=True)
class PromptAuditInput:
    system_policy: str
    retrieved_knowledge: Any
    sanitized_dynamic_payload: dict[str, Any]
    output_schema_instruction: str
    stage: str
    opaque_case_id: str
    trial_id: str

    def prompt_sha256(self) -> str:
        return json_sha256(
            {
                "system_policy": self.system_policy,
                "retrieved_knowledge": _normalize_prompt_audit_value(self.retrieved_knowledge),
                "sanitized_dynamic_payload": _normalize_prompt_audit_value(self.sanitized_dynamic_payload),
                "output_schema_instruction": self.output_schema_instruction,
            }
        )


@dataclass
class ZoneAudit:
    section: str
    safe: bool = True
    ground_truth_found: bool = False
    historical_verdict_found: bool = False
    historical_metric_found: bool = False
    mutation_id_found: bool = False
    benchmark_name_found: bool = False
    local_path_found: bool = False
    actual_sensitive_value_present: bool = False
    negative_policy_instruction_only: bool = False
    matched_rules: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    def observe(self, code: str) -> None:
        if code not in self.matched_rules:
            self.matched_rules.append(code)

    def reject(
        self,
        code: str,
        *,
        ground_truth: bool = False,
        historical_verdict: bool = False,
        historical_metric: bool = False,
        mutation_id: bool = False,
        benchmark_name: bool = False,
        local_path: bool = False,
        actual_sensitive_value: bool = True,
    ) -> None:
        self.safe = False
        self.observe(code)
        if code not in self.rejection_reasons:
            self.rejection_reasons.append(code)
        self.ground_truth_found = self.ground_truth_found or ground_truth
        self.historical_verdict_found = self.historical_verdict_found or historical_verdict
        self.historical_metric_found = self.historical_metric_found or historical_metric
        self.mutation_id_found = self.mutation_id_found or mutation_id
        self.benchmark_name_found = self.benchmark_name_found or benchmark_name
        self.local_path_found = self.local_path_found or local_path
        self.actual_sensitive_value_present = self.actual_sensitive_value_present or actual_sensitive_value


@dataclass
class PromptLeakageAuditResult:
    stage: str
    opaque_case_id: str
    trial_id: str
    system_policy_safe: bool
    retrieved_knowledge_safe: bool
    dynamic_payload_safe: bool
    schema_instruction_safe: bool
    ground_truth_found: bool
    historical_verdict_found: bool
    historical_metric_found: bool
    mutation_id_found: bool
    benchmark_name_found: bool
    local_path_found: bool
    actual_sensitive_value_present: bool
    negative_policy_instruction_only: bool
    matched_sections: list[str]
    matched_rules: list[str]
    finding_count: int
    rejection_reasons: list[str]
    prompt_safe: bool
    prompt_sha256: str
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "opaque_case_id": self.opaque_case_id,
            "trial_id": self.trial_id,
            "run_id": self.run_id,
            "system_policy_safe": self.system_policy_safe,
            "retrieved_knowledge_safe": self.retrieved_knowledge_safe,
            "dynamic_payload_safe": self.dynamic_payload_safe,
            "schema_instruction_safe": self.schema_instruction_safe,
            "ground_truth_found": self.ground_truth_found,
            "historical_verdict_found": self.historical_verdict_found,
            "historical_metric_found": self.historical_metric_found,
            "mutation_id_found": self.mutation_id_found,
            "benchmark_name_found": self.benchmark_name_found,
            "local_path_found": self.local_path_found,
            "actual_sensitive_value_present": self.actual_sensitive_value_present,
            "negative_policy_instruction_only": self.negative_policy_instruction_only,
            "matched_sections": json.dumps(self.matched_sections, ensure_ascii=True),
            "matched_rules": json.dumps(self.matched_rules, ensure_ascii=True),
            "finding_count": self.finding_count,
            "rejection_reasons": json.dumps(self.rejection_reasons, ensure_ascii=True),
            "prompt_safe": self.prompt_safe,
            "prompt_sha256": self.prompt_sha256,
        }


class ProviderSmokeCapability(str, Enum):
    JSON_ONLY = "JSON_ONLY"
    PROVIDER_REACHABLE = "PROVIDER_REACHABLE"
    SCHEMA_COMPLIANCE = "SCHEMA_COMPLIANCE"


class ProviderSmokeConstraint(str, Enum):
    NO_MARKDOWN = "NO_MARKDOWN"
    NO_EXPLANATION = "NO_EXPLANATION"
    NO_VERDICT = "NO_VERDICT"
    NO_RAW_SPICE = "NO_RAW_SPICE"
    NO_LOCAL_PATHS = "NO_LOCAL_PATHS"
    NO_HISTORICAL_RESULTS = "NO_HISTORICAL_RESULTS"


class ProviderSmokeResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    smoke_id: Literal["provider_smoke"]
    status: Literal["READY"]
    capabilities: list[ProviderSmokeCapability]
    acknowledged_constraints: list[ProviderSmokeConstraint]

    @field_validator("capabilities", "acknowledged_constraints")
    @classmethod
    def _validate_non_empty_unique_enum_list(cls, value: list[Any]) -> list[Any]:
        if not value:
            raise ValueError("must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("must be unique")
        return value


@dataclass(frozen=True)
class CampaignCase:
    case_id: str
    parent_circuit_id: str
    ground_truth_label: str
    circuit_family: str
    specification_file: Path
    netlist_file: Path
    targeted_metric: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_tree(root: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        entries.append({"path": relative, "sha256": sha256_file(path)})
    return json_sha256(entries)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def current_run_id() -> str:
    return os.getenv("DEEPSEEK_LIVE_RUN_ID", "").strip()


def current_execution_mode() -> str:
    return os.getenv("DEEPSEEK_LIVE_EXECUTION_MODE", "LIVE").strip().upper() or "LIVE"


def provider_smoke_run_results_dir(run_id: str) -> Path:
    return RUN_RESULTS_DIR / run_id


def provider_smoke_run_reports_dir(run_id: str) -> Path:
    return RUN_REPORTS_DIR / run_id


def provider_smoke_artifact_dir(run_id: str) -> Path:
    return ARTIFACTS_DIR / "provider_smoke" / run_id


def build_provider_smoke_expected_response() -> ProviderSmokeResponseV1:
    return ProviderSmokeResponseV1.model_validate(
        {
            "schema_version": "1.0",
            "smoke_id": "provider_smoke",
            "status": "READY",
            "capabilities": [
                ProviderSmokeCapability.JSON_ONLY,
                ProviderSmokeCapability.PROVIDER_REACHABLE,
                ProviderSmokeCapability.SCHEMA_COMPLIANCE,
            ],
            "acknowledged_constraints": [
                ProviderSmokeConstraint.NO_MARKDOWN,
                ProviderSmokeConstraint.NO_EXPLANATION,
                ProviderSmokeConstraint.NO_VERDICT,
                ProviderSmokeConstraint.NO_RAW_SPICE,
                ProviderSmokeConstraint.NO_LOCAL_PATHS,
                ProviderSmokeConstraint.NO_HISTORICAL_RESULTS,
            ],
        }
    )


def provider_smoke_expected_shape_payload() -> dict[str, Any]:
    return build_provider_smoke_expected_response().model_dump(mode="json")


def provider_smoke_json_schema_payload() -> dict[str, Any]:
    return ProviderSmokeResponseV1.model_json_schema()


def _write_provider_smoke_contract_artifacts() -> None:
    write_json(PROVIDER_SMOKE_EXPECTED_SHAPE_JSON, provider_smoke_expected_shape_payload())
    write_json(PROVIDER_SMOKE_JSON_SCHEMA_JSON, provider_smoke_json_schema_payload())


def _redact_sensitive_text(text: str) -> str:
    if not text:
        return ""
    redacted = BEARER_TOKEN_RE.sub("Bearer ***", text)
    redacted = API_KEY_LITERAL_RE.sub('api_key="***"', redacted)
    redacted = SK_TOKEN_RE.sub("***", redacted)
    return redacted


def _provider_smoke_run_id(run_id: str | None = None) -> str:
    candidate = (run_id or current_run_id()).strip()
    return candidate or "run_id_not_set"


def _provider_smoke_user_payload(audit_input: PromptAuditInput) -> dict[str, Any]:
    return {
        "retrieved_knowledge": audit_input.retrieved_knowledge,
        "sanitized_dynamic_payload": audit_input.sanitized_dynamic_payload,
        "output_schema_instruction": audit_input.output_schema_instruction,
    }


def _provider_smoke_user_prompt_text(audit_input: PromptAuditInput) -> str:
    return json.dumps(_provider_smoke_user_payload(audit_input), ensure_ascii=True)


def _write_provider_smoke_request_artifacts(
    *,
    audit_input: PromptAuditInput,
    run_id: str,
    execution_mode: str,
    model: str,
) -> Path:
    artifact_dir = provider_smoke_artifact_dir(run_id)
    user_payload = _provider_smoke_user_payload(audit_input)
    user_prompt_text = _provider_smoke_user_prompt_text(audit_input)
    prompt_sha = audit_input.prompt_sha256()
    write_json(
        artifact_dir / "request_metadata.json",
        {
            "run_id": run_id,
            "stage": audit_input.stage,
            "opaque_case_id": audit_input.opaque_case_id,
            "trial_id": audit_input.trial_id,
            "execution_mode": execution_mode,
            "model": model,
            "prompt_version": PROVIDER_SMOKE_PROMPT_VERSION,
            "response_schema_version": PROVIDER_SMOKE_RESPONSE_SCHEMA_VERSION,
            "prompt_sha256": prompt_sha,
            "user_prompt_sha256": sha256_text(user_prompt_text),
        },
    )
    write_json(artifact_dir / "sanitized_payload.json", user_payload)
    write_text(artifact_dir / "system_prompt.txt", audit_input.system_policy)
    write_text(artifact_dir / "user_prompt.txt", user_prompt_text)
    write_text(artifact_dir / "prompt.sha256", f"{prompt_sha}\n")
    return artifact_dir


def _serialize_validation_errors(
    exc: ValidationError,
    *,
    run_id: str,
    validation_model: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, error in enumerate(exc.errors(include_url=False), start=1):
        location = ".".join(str(item) for item in error.get("loc", ())) or "<root>"
        error_type = str(error.get("type", "") or "")
        input_value = error.get("input")
        if input_value is None:
            input_redacted = ""
        elif isinstance(input_value, (str, int, float, bool)):
            input_redacted = _redact_sensitive_text(str(input_value))[:120]
        else:
            input_redacted = type(input_value).__name__
        expected_type = ""
        message = str(error.get("msg", "") or "")
        lowered_message = message.lower()
        if "literal" in lowered_message or "enum" in lowered_message:
            expected_type = "enum"
        elif "list" in lowered_message:
            expected_type = "list"
        elif "dict" in lowered_message:
            expected_type = "dict"
        rows.append(
            {
                "run_id": run_id,
                "validation_model": validation_model,
                "error_index": index,
                "location": location,
                "error_type": error_type,
                "message": _redact_sensitive_text(message),
                "expected_type": expected_type,
                "received_type": type(input_value).__name__ if input_value is not None else "",
                "input_redacted": input_redacted,
                "root_cause_category": _classify_schema_error_category(error_type=error_type, message=message, location=location),
                "repairable_offline": True,
            }
        )
    return rows


def _classify_schema_error_category(*, error_type: str, message: str, location: str) -> str:
    lowered_type = error_type.lower()
    lowered_message = message.lower()
    if "missing" in lowered_type:
        return "MISSING_REQUIRED_FIELD"
    if "extra_forbidden" in lowered_type or "extra inputs are not permitted" in lowered_message:
        return "EXTRA_FORBIDDEN_FIELD"
    if "literal" in lowered_type or "enum" in lowered_type or "expected" in lowered_message and "allowed" in lowered_message:
        return "ENUM_VALUE_MISMATCH"
    if "list" in lowered_type and "too_short" in lowered_type:
        return "EMPTY_REQUIRED_COLLECTION"
    if any(token in lowered_type for token in ("int", "string_type", "dict_type", "list_type", "model_type", "float")):
        return "TYPE_MISMATCH"
    if location == "<root>":
        return "WRONG_TOP_LEVEL_SHAPE"
    return "UNKNOWN_SCHEMA_FAILURE"


def _write_provider_smoke_response_artifacts(
    *,
    artifact_dir: Path,
    response_content: str | None,
    parsed_response: dict[str, Any] | None,
    json_valid: bool | None,
    json_error: Exception | None,
    schema_valid: bool | None,
    validation_model: str,
    schema_error_rows: list[dict[str, Any]],
    provider_response_metadata: dict[str, Any],
    live_call_record: dict[str, Any],
    provider_smoke_result: dict[str, Any],
    run_id: str,
) -> None:
    if response_content is not None:
        write_text(artifact_dir / "raw_response.txt", response_content)
        write_text(artifact_dir / "raw_response.sha256", f"{sha256_text(response_content)}\n")
    parse_result = {
        "run_id": run_id,
        "json_valid": json_valid,
        "parser": "json.loads",
        "error": _redact_sensitive_text(str(json_error)) if json_error is not None else "",
    }
    write_json(artifact_dir / "JSON_parse_result.json", parse_result)
    if parsed_response is not None:
        write_json(artifact_dir / "parsed_json.json", parsed_response)
    write_json(
        artifact_dir / "schema_validation.json",
        {
            "run_id": run_id,
            "validation_model": validation_model,
            "validation_method": f"{validation_model}.model_validate",
            "schema_valid": schema_valid,
            "pydantic_version": PYDANTIC_VERSION,
            "error_count": len(schema_error_rows),
        },
    )
    write_json(artifact_dir / "schema_validation_errors.json", schema_error_rows)
    write_json(artifact_dir / "provider_response_metadata.json", provider_response_metadata)
    write_json(artifact_dir / "live_call_record.json", live_call_record)
    write_json(artifact_dir / "provider_smoke.json", provider_smoke_result)


def _provider_smoke_error_summary_rows(error_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    summary = {
        "missing_fields": [],
        "extra_fields": [],
        "type_mismatches": [],
        "enum_mismatches": [],
        "empty_required_collections": [],
    }
    for row in error_rows:
        category = row.get("root_cause_category")
        location = str(row.get("location", "") or "")
        if category == "MISSING_REQUIRED_FIELD":
            summary["missing_fields"].append(location)
        elif category == "EXTRA_FORBIDDEN_FIELD":
            summary["extra_fields"].append(location)
        elif category == "TYPE_MISMATCH":
            summary["type_mismatches"].append(location)
        elif category == "ENUM_VALUE_MISMATCH":
            summary["enum_mismatches"].append(location)
        elif category == "EMPTY_REQUIRED_COLLECTION":
            summary["empty_required_collections"].append(location)
    return {key: sorted(dict.fromkeys(value)) for key, value in summary.items()}


def _write_provider_smoke_schema_error_reports(
    *,
    error_rows: list[dict[str, Any]],
    run_id: str,
    validation_model: str,
    error_details_available: bool,
    detail_source: str,
) -> None:
    write_json(
        PROVIDER_SMOKE_SCHEMA_ERRORS_JSON,
        {
            "run_id": run_id,
            "validation_model": validation_model,
            "pydantic_version": PYDANTIC_VERSION,
            "validation_method": f"{validation_model}.model_validate",
            "error_details_available": error_details_available,
            "detail_source": detail_source,
            "error_count": len(error_rows),
            "errors": error_rows,
        },
    )
    csv_rows = error_rows or [
        {
            "run_id": run_id,
            "validation_model": validation_model,
            "error_index": 0,
            "location": "NOT_AVAILABLE",
            "error_type": "ERROR_DETAILS_UNAVAILABLE",
            "message": "Raw response was not persisted; exact ValidationError.errors() output is unavailable for this historical run.",
            "expected_type": "",
            "received_type": "",
            "input_redacted": "",
            "root_cause_category": "SMOKE_CONTRACT_INCONSISTENT",
            "repairable_offline": True,
        }
    ]
    write_csv(PROVIDER_SMOKE_SCHEMA_ERRORS_CSV, csv_rows)
    summary_rows = _provider_smoke_error_summary_rows(error_rows)
    write_markdown(
        PROVIDER_SMOKE_SCHEMA_ERRORS_MD,
        [
            "# Provider Smoke Schema Errors",
            "",
            f"- Run ID: {run_id}",
            f"- Validation model: {validation_model}",
            f"- Pydantic version: {PYDANTIC_VERSION}",
            f"- Validation method: {validation_model}.model_validate",
            f"- Error details available: {str(error_details_available).lower()}",
            f"- Detail source: {detail_source}",
            f"- Error count: {len(error_rows)}",
            f"- Missing fields: {', '.join(summary_rows['missing_fields']) if summary_rows['missing_fields'] else 'none'}",
            f"- Extra fields: {', '.join(summary_rows['extra_fields']) if summary_rows['extra_fields'] else 'none'}",
            f"- Type mismatches: {', '.join(summary_rows['type_mismatches']) if summary_rows['type_mismatches'] else 'none'}",
            f"- Enum mismatches: {', '.join(summary_rows['enum_mismatches']) if summary_rows['enum_mismatches'] else 'none'}",
            f"- Empty required collections: {', '.join(summary_rows['empty_required_collections']) if summary_rows['empty_required_collections'] else 'none'}",
        ],
    )


def _collect_provider_smoke_inventory_rows(run_id: str) -> list[dict[str, Any]]:
    candidates = [
        {
            "path": provider_smoke_artifact_dir(run_id) / "raw_response.txt",
            "stage": "provider_smoke",
            "artifact_type": "RAW_RESPONSE",
            "contains_provider_response": True,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "provider_response_metadata.json",
            "stage": "provider_smoke",
            "artifact_type": "PROVIDER_RESPONSE_METADATA",
            "contains_provider_response": False,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "parsed_json.json",
            "stage": "provider_smoke",
            "artifact_type": "PARSED_JSON",
            "contains_provider_response": True,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "schema_validation_errors.json",
            "stage": "provider_smoke",
            "artifact_type": "SCHEMA_VALIDATION_ERRORS",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "request_metadata.json",
            "stage": "provider_smoke",
            "artifact_type": "REQUEST_METADATA",
            "contains_provider_response": False,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "system_prompt.txt",
            "stage": "provider_smoke",
            "artifact_type": "SYSTEM_PROMPT",
            "contains_provider_response": False,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": provider_smoke_artifact_dir(run_id) / "user_prompt.txt",
            "stage": "provider_smoke",
            "artifact_type": "USER_PROMPT",
            "contains_provider_response": False,
            "contains_validation_details": False,
            "selected_for_analysis": True,
        },
        {
            "path": RESULTS_DIR / "provider_smoke.json",
            "stage": "provider_smoke",
            "artifact_type": "PROVIDER_SMOKE_RESULT",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": RESULTS_DIR / "provider_smoke_calls.csv",
            "stage": "provider_smoke",
            "artifact_type": "PROVIDER_SMOKE_CALL_LEDGER",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": LIVE_CALL_AUDIT_CSV,
            "stage": "campaign",
            "artifact_type": "LIVE_CALL_LEDGER",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": REPORTS_DIR / "provider_smoke.md",
            "stage": "provider_smoke",
            "artifact_type": "REPORT",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": FINAL_SUMMARY_JSON,
            "stage": "provider_smoke",
            "artifact_type": "CURRENT_SUMMARY",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
        {
            "path": FINAL_STATUS_MD,
            "stage": "provider_smoke",
            "artifact_type": "CURRENT_REPORT",
            "contains_provider_response": False,
            "contains_validation_details": True,
            "selected_for_analysis": True,
        },
    ]
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        path = candidate["path"]
        exists = path.exists()
        text = path.read_text(encoding="utf-8", errors="replace") if exists else ""
        belongs_to_current_run = run_id in text or run_id in str(path).replace("\\", "/")
        contains_secret = bool(scan_text_for_secret_matches(text)) if exists else False
        rows.append(
            {
                "path": str(path).replace("\\", "/"),
                "run_id": run_id,
                "stage": candidate["stage"],
                "artifact_type": candidate["artifact_type"],
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else 0,
                "sha256": sha256_file(path) if exists else "",
                "belongs_to_current_run": belongs_to_current_run,
                "contains_provider_response": candidate["contains_provider_response"],
                "contains_validation_details": candidate["contains_validation_details"],
                "contains_secret": contains_secret,
                "selected_for_analysis": candidate["selected_for_analysis"],
            }
        )
    return rows


def _write_provider_smoke_validation_inventory(run_id: str) -> list[dict[str, Any]]:
    rows = _collect_provider_smoke_inventory_rows(run_id)
    write_csv(PROVIDER_SMOKE_VALIDATION_INVENTORY_CSV, rows)
    write_markdown(
        PROVIDER_SMOKE_VALIDATION_INVENTORY_MD,
        [
            "# Provider Smoke Validation Inventory",
            "",
            f"- Run ID: {run_id}",
            f"- Files scanned: {len(rows)}",
            f"- Files present: {sum(1 for row in rows if row['exists'])}",
            f"- Raw response present: {str(any(row['artifact_type'] == 'RAW_RESPONSE' and row['exists'] for row in rows)).lower()}",
            f"- Validation details present: {str(any(row['contains_validation_details'] and row['exists'] for row in rows)).lower()}",
            "",
            "## Selected Artifacts",
            *(f"- {row['artifact_type']}: {row['path']} ({'present' if row['exists'] else 'missing'})" for row in rows if row["selected_for_analysis"]),
        ],
    )
    return rows


def _write_current_run_ledgers(run_id: str) -> None:
    run_results_dir = provider_smoke_run_results_dir(run_id)
    write_csv(run_results_dir / "live_call_audit_current_run.csv", [row for row in read_csv(LIVE_CALL_AUDIT_CSV) if row.get("run_id", "") == run_id])
    write_csv(run_results_dir / "live_budget_current_run.csv", [row for row in read_csv(LIVE_BUDGET_CSV) if row.get("run_id", "") == run_id])
    write_csv(run_results_dir / "prompt_leakage_audit_current_run.csv", [row for row in read_csv(PROMPT_AUDIT_CSV) if row.get("run_id", "") == run_id])


def _provider_smoke_root_cause_payload(
    *,
    run_id: str,
    provider_smoke: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
    error_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_response_found = any(row["artifact_type"] == "RAW_RESPONSE" and row["exists"] for row in inventory_rows)
    schema_error_summary = _provider_smoke_error_summary_rows(error_rows)
    categories = sorted(
        dict.fromkeys(
            [row["root_cause_category"] for row in error_rows]
            or [
                "WRONG_VALIDATION_MODEL",
                "MODEL_OUTPUT_SCHEMA_MISMATCH",
                "SMOKE_CONTRACT_INCONSISTENT",
            ]
        )
    )
    expected_shape = provider_smoke_expected_shape_payload()
    return {
        "run_id": run_id,
        "json_valid": provider_smoke.get("json_valid"),
        "schema_valid": provider_smoke.get("schema_valid"),
        "provider_failure_code": provider_smoke.get("provider_failure_code", ""),
        "provider_failure_stage": provider_smoke.get("provider_failure_stage", ""),
        "raw_response_found": raw_response_found,
        "exact_validation_errors_available": bool(error_rows),
        "original_expected_schema": "TestbenchPlan",
        "prompt_claimed_schema": "TestbenchPlanV2",
        "final_smoke_schema": "ProviderSmokeResponseV1",
        "production_schema_used_for_real_circuits": "TestbenchPlan",
        "original_contract_internally_consistent": False,
        "root_cause_categories": categories,
        "root_cause": (
            "The historical provider smoke contract was internally inconsistent: the smoke prompt asked for a generic "
            "TestbenchPlanV2-style payload while the executor validated the response against the strict production "
            "TestbenchPlan model. A generic smoke probe without DUT, metrics, recipes, or analysis jobs cannot satisfy "
            "that production schema without inventing scientific content."
        ),
        "what_deepseek_returned": (
            "A JSON object was returned and counted for tokens, but the exact raw body was not persisted for the historical run."
            if not raw_response_found
            else "A JSON object was returned and persisted in raw_response.txt."
        ),
        "what_schema_required": {
            "historical_validator": "TestbenchPlan.model_validate",
            "historical_required_fields": ["case_id", "analysis_type", "measurements", "simulation_parameters", "concise_rationale"],
            "current_smoke_expected_shape": expected_shape,
        },
        "gap_introduced_in": [
            "build_provider_smoke_prompt_audit_input",
            "execute_provider_smoke_probe",
        ],
        "json_valid_but_schema_invalid_reason": (
            "The provider returned syntactically valid JSON, but schema validation failed because the smoke response "
            "shape did not match the strict production TestbenchPlan model."
        ),
        "missing_fields": schema_error_summary["missing_fields"],
        "extra_fields": schema_error_summary["extra_fields"],
        "type_mismatches": schema_error_summary["type_mismatches"],
        "enum_mismatches": schema_error_summary["enum_mismatches"],
        "empty_required_collections": schema_error_summary["empty_required_collections"],
        "repairable_offline": True,
        "production_schema_weakened": False,
        "dedicated_smoke_schema_introduced": True,
    }


def _write_provider_smoke_root_cause_reports(payload: dict[str, Any]) -> None:
    write_json(PROVIDER_SMOKE_ROOT_CAUSE_JSON, payload)
    write_markdown(
        PROVIDER_SMOKE_ROOT_CAUSE_MD,
        [
            "# Provider Smoke Root Cause",
            "",
            f"- Run ID: {payload['run_id']}",
            f"- Raw response found: {str(payload['raw_response_found']).lower()}",
            f"- Exact validation errors available: {str(payload['exact_validation_errors_available']).lower()}",
            f"- Original expected schema: {payload['original_expected_schema']}",
            f"- Prompt claimed schema: {payload['prompt_claimed_schema']}",
            f"- Final smoke schema: {payload['final_smoke_schema']}",
            f"- Original contract internally consistent: {str(payload['original_contract_internally_consistent']).lower()}",
            f"- Root cause categories: {', '.join(payload['root_cause_categories'])}",
            f"- Root cause: {payload['root_cause']}",
            f"- JSON valid but schema invalid reason: {payload['json_valid_but_schema_invalid_reason']}",
            f"- Missing fields: {', '.join(payload['missing_fields']) if payload['missing_fields'] else 'none'}",
            f"- Extra fields: {', '.join(payload['extra_fields']) if payload['extra_fields'] else 'none'}",
            f"- Type mismatches: {', '.join(payload['type_mismatches']) if payload['type_mismatches'] else 'none'}",
            f"- Enum mismatches: {', '.join(payload['enum_mismatches']) if payload['enum_mismatches'] else 'none'}",
            f"- Empty required collections: {', '.join(payload['empty_required_collections']) if payload['empty_required_collections'] else 'none'}",
            f"- Dedicated smoke schema introduced: {str(payload['dedicated_smoke_schema_introduced']).lower()}",
            f"- Production schema weakened: {str(payload['production_schema_weakened']).lower()}",
        ],
    )


def reconcile_provider_smoke_run_artifacts(run_id: str) -> dict[str, Any]:
    normalized_run_id = _provider_smoke_run_id(run_id)
    _write_provider_smoke_contract_artifacts()
    _write_current_run_ledgers(normalized_run_id)
    provider_smoke = read_json(RESULTS_DIR / "provider_smoke.json", {})
    if provider_smoke.get("run_id") == normalized_run_id and provider_smoke.get("provider_failure") == "ValidationError":
        provider_smoke["provider_failure"] = "SCHEMA_ERROR"
        provider_smoke["provider_failure_code"] = "SCHEMA_ERROR"
        provider_smoke["provider_failure_stage"] = "SCHEMA_VALIDATION"
        provider_smoke["provider_exception_class"] = "ValidationError"
        provider_smoke["provider_exception_message_sanitized"] = "Raw response was not persisted; exact ValidationError details unavailable."
        provider_smoke["semantic_valid"] = "NOT_EXECUTED"
        provider_smoke["transport_response_received"] = True
        provider_smoke["content_received"] = True
        provider_smoke["json_parsed"] = True
        provider_smoke["schema_valid"] = False
        provider_smoke["GO_PROVIDER_TRANSPORT"] = "PASS"
        provider_smoke["GO_PROVIDER_JSON"] = "PASS"
        provider_smoke["GO_PROVIDER_SMOKE_SCHEMA"] = "NO_GO"
        provider_smoke["GO_PROVIDER_SMOKE"] = "NO_GO"
        write_json(RESULTS_DIR / "provider_smoke.json", provider_smoke)
        write_json(provider_smoke_run_results_dir(normalized_run_id) / "provider_smoke.json", provider_smoke)
    inventory_rows = _write_provider_smoke_validation_inventory(normalized_run_id)
    raw_response_path = provider_smoke_artifact_dir(normalized_run_id) / "raw_response.txt"
    error_details_available = (provider_smoke_artifact_dir(normalized_run_id) / "schema_validation_errors.json").exists()
    error_rows = read_json(provider_smoke_artifact_dir(normalized_run_id) / "schema_validation_errors.json", [])
    _write_provider_smoke_schema_error_reports(
        error_rows=error_rows,
        run_id=normalized_run_id,
        validation_model="TestbenchPlan",
        error_details_available=error_details_available,
        detail_source=str(raw_response_path).replace("\\", "/") if error_details_available else "RAW_RESPONSE_MISSING",
    )
    root_cause_payload = _provider_smoke_root_cause_payload(
        run_id=normalized_run_id,
        provider_smoke=provider_smoke,
        inventory_rows=inventory_rows,
        error_rows=error_rows,
    )
    _write_provider_smoke_root_cause_reports(root_cause_payload)
    return {
        "provider_smoke": provider_smoke,
        "inventory_rows": inventory_rows,
        "schema_error_rows": error_rows,
        "root_cause": root_cause_payload,
    }


def append_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    existing = read_csv(path)
    combined = existing + [{key: value for key, value in row.items()} for row in rows]
    write_csv(path, combined)


def _normalize_prompt_audit_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _normalize_prompt_audit_value(value.model_dump(mode="json"))
    if hasattr(value, "dict") and callable(value.dict):
        return _normalize_prompt_audit_value(value.dict())
    if isinstance(value, dict):
        return {str(key): _normalize_prompt_audit_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_prompt_audit_value(item) for item in value]
    return value


def _iter_prompt_audit_nodes(value: Any, *, path: str) -> list[tuple[str, Any]]:
    normalized = _normalize_prompt_audit_value(value)
    if isinstance(normalized, dict):
        nodes: list[tuple[str, Any]] = []
        for key, item in normalized.items():
            child_path = f"{path}.{key}" if path else str(key)
            nodes.extend(_iter_prompt_audit_nodes(item, path=child_path))
        return nodes
    if isinstance(normalized, list):
        nodes = []
        for index, item in enumerate(normalized):
            child_path = f"{path}[{index}]"
            nodes.extend(_iter_prompt_audit_nodes(item, path=child_path))
        return nodes
    return [(path, normalized)]


def _safe_prompt_audit_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_safe_relative_prompt_path(text: str) -> bool:
    lowered = text.strip().replace("\\", "/").lower()
    return any(lowered.startswith(prefix) for prefix in PROMPT_AUDIT_SAFE_RELATIVE_PATH_PREFIXES)


def _string_contains_prompt_audit_value(text: str, tokens: set[str]) -> bool:
    upper = text.upper()
    return any(token in upper for token in tokens)


def _key_flag_kwargs(normalized_key: str) -> dict[str, bool]:
    return {
        "ground_truth": normalized_key in PROMPT_AUDIT_GROUND_TRUTH_KEYS,
        "historical_verdict": normalized_key in PROMPT_AUDIT_HISTORICAL_VERDICT_KEYS,
        "historical_metric": normalized_key in PROMPT_AUDIT_HISTORICAL_METRIC_KEYS,
        "mutation_id": normalized_key in PROMPT_AUDIT_MUTATION_KEYS,
        "benchmark_name": normalized_key in PROMPT_AUDIT_BENCHMARK_KEYS,
        "local_path": normalized_key in PROMPT_AUDIT_LOCAL_PATH_KEYS,
    }


def _value_flag_kwargs(text: str) -> dict[str, bool]:
    upper = text.upper()
    return {
        "ground_truth": any(token in upper for token in GROUND_TRUTH_TOKENS if token.startswith("GROUND_TRUTH")),
        "historical_verdict": _string_contains_prompt_audit_value(text, PROMPT_AUDIT_SENSITIVE_VALUE_TOKENS),
        "historical_metric": _string_contains_prompt_audit_value(text, PROMPT_AUDIT_HISTORY_METRIC_TOKENS),
        "mutation_id": bool(PROMPT_AUDIT_MUTATION_VALUE_RE.search(text)),
        "benchmark_name": bool(PROMPT_AUDIT_BENCHMARK_VALUE_RE.search(text)),
        "local_path": bool(PROMPT_AUDIT_ABSOLUTE_PATH_RE.search(text)) and not _is_safe_relative_prompt_path(text),
    }


def _line_is_negative_instruction(line: str, *, in_negative_block: bool) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    if PROMPT_AUDIT_NEGATIVE_PREFIX_RE.search(lowered):
        return True
    if in_negative_block and lowered.startswith("-"):
        return True
    return False


def _audit_text_zone(section: str, text: str) -> ZoneAudit:
    audit = ZoneAudit(section=section)
    negative_lines: list[str] = []
    generic_term_lines: list[str] = []
    in_negative_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not line:
            in_negative_block = False
            continue
        if "must never" in lowered or "must not" in lowered or lowered.endswith("never:"):
            in_negative_block = True
        if any(term in lowered for term in PROMPT_AUDIT_GENERIC_POLICY_TERMS):
            generic_term_lines.append(line)
            if _line_is_negative_instruction(line, in_negative_block=in_negative_block):
                negative_lines.append(line)
                audit.observe(f"{section.upper()}_NEGATIVE_POLICY_INSTRUCTION")
        assignment_match = PROMPT_AUDIT_SENSITIVE_ASSIGNMENT_RE.search(line)
        if assignment_match:
            normalized_key = assignment_match.group("key").lower()
            audit.reject(
                f"{section.upper()}_SENSITIVE_ASSIGNMENT@{normalized_key}",
                **_key_flag_kwargs(normalized_key),
            )
        if PROMPT_AUDIT_ABSOLUTE_PATH_RE.search(line) and not _is_safe_relative_prompt_path(line):
            audit.reject(f"{section.upper()}_ABSOLUTE_LOCAL_PATH", local_path=True)
        if _string_contains_prompt_audit_value(line, PROMPT_AUDIT_SENSITIVE_VALUE_TOKENS):
            audit.reject(f"{section.upper()}_SENSITIVE_HISTORY_VALUE", historical_verdict=True)
        if _string_contains_prompt_audit_value(line, PROMPT_AUDIT_HISTORY_METRIC_TOKENS):
            audit.reject(f"{section.upper()}_SENSITIVE_HISTORY_METRIC", historical_metric=True)
        if any(token in line.upper() for token in GROUND_TRUTH_TOKENS if token.startswith("GROUND_TRUTH")):
            audit.reject(f"{section.upper()}_GROUND_TRUTH_LABEL", ground_truth=True)
        if PROMPT_AUDIT_MUTATION_VALUE_RE.search(line):
            audit.reject(f"{section.upper()}_MUTATION_IDENTIFIER", mutation_id=True)
        if PROMPT_AUDIT_BENCHMARK_VALUE_RE.search(line):
            audit.reject(f"{section.upper()}_BENCHMARK_IDENTIFIER", benchmark_name=True)
    audit.negative_policy_instruction_only = bool(generic_term_lines) and len(generic_term_lines) == len(negative_lines) and audit.safe
    return audit


def _audit_dynamic_zone(section: str, payload: Any) -> ZoneAudit:
    audit = ZoneAudit(section=section)
    normalized = _normalize_prompt_audit_value(payload)
    if isinstance(normalized, dict):
        for key, value in normalized.items():
            normalized_key = str(key).lower()
            safe_path = _safe_prompt_audit_path(f"{section}.{key}")
            if normalized_key in PROMPT_AUDIT_SENSITIVE_KEYS:
                audit.reject(
                    f"{section.upper()}_FORBIDDEN_KEY@{safe_path}",
                    **_key_flag_kwargs(normalized_key),
                )
            child_audit = _audit_dynamic_zone(safe_path, value)
            audit.safe = audit.safe and child_audit.safe
            audit.ground_truth_found = audit.ground_truth_found or child_audit.ground_truth_found
            audit.historical_verdict_found = audit.historical_verdict_found or child_audit.historical_verdict_found
            audit.historical_metric_found = audit.historical_metric_found or child_audit.historical_metric_found
            audit.mutation_id_found = audit.mutation_id_found or child_audit.mutation_id_found
            audit.benchmark_name_found = audit.benchmark_name_found or child_audit.benchmark_name_found
            audit.local_path_found = audit.local_path_found or child_audit.local_path_found
            audit.actual_sensitive_value_present = (
                audit.actual_sensitive_value_present or child_audit.actual_sensitive_value_present
            )
            for code in child_audit.matched_rules:
                audit.observe(code)
            for code in child_audit.rejection_reasons:
                if code not in audit.rejection_reasons:
                    audit.rejection_reasons.append(code)
        return audit
    if isinstance(normalized, list):
        for index, item in enumerate(normalized):
            child_audit = _audit_dynamic_zone(f"{section}[{index}]", item)
            audit.safe = audit.safe and child_audit.safe
            audit.ground_truth_found = audit.ground_truth_found or child_audit.ground_truth_found
            audit.historical_verdict_found = audit.historical_verdict_found or child_audit.historical_verdict_found
            audit.historical_metric_found = audit.historical_metric_found or child_audit.historical_metric_found
            audit.mutation_id_found = audit.mutation_id_found or child_audit.mutation_id_found
            audit.benchmark_name_found = audit.benchmark_name_found or child_audit.benchmark_name_found
            audit.local_path_found = audit.local_path_found or child_audit.local_path_found
            audit.actual_sensitive_value_present = (
                audit.actual_sensitive_value_present or child_audit.actual_sensitive_value_present
            )
            for code in child_audit.matched_rules:
                audit.observe(code)
            for code in child_audit.rejection_reasons:
                if code not in audit.rejection_reasons:
                    audit.rejection_reasons.append(code)
        return audit
    if isinstance(normalized, str):
        if PROMPT_AUDIT_ABSOLUTE_PATH_RE.search(normalized) and not _is_safe_relative_prompt_path(normalized):
            audit.reject(f"{section.upper()}_ABSOLUTE_LOCAL_PATH@{_safe_prompt_audit_path(section)}", local_path=True)
        value_flags = _value_flag_kwargs(normalized)
        if value_flags["historical_verdict"]:
            audit.reject(f"{section.upper()}_SENSITIVE_HISTORY_VALUE@{_safe_prompt_audit_path(section)}", historical_verdict=True)
        if value_flags["historical_metric"]:
            audit.reject(f"{section.upper()}_SENSITIVE_HISTORY_METRIC@{_safe_prompt_audit_path(section)}", historical_metric=True)
        if value_flags["ground_truth"]:
            audit.reject(f"{section.upper()}_GROUND_TRUTH_LABEL@{_safe_prompt_audit_path(section)}", ground_truth=True)
        if value_flags["mutation_id"]:
            audit.reject(f"{section.upper()}_MUTATION_IDENTIFIER@{_safe_prompt_audit_path(section)}", mutation_id=True)
        if value_flags["benchmark_name"]:
            audit.reject(f"{section.upper()}_BENCHMARK_IDENTIFIER@{_safe_prompt_audit_path(section)}", benchmark_name=True)
    return audit


def build_prompt_audit_input(
    *,
    stage: str,
    opaque_case_id: str,
    trial_id: str,
    system_prompt: str,
    request_payload: dict[str, Any],
) -> PromptAuditInput:
    normalized_payload = _normalize_prompt_audit_value(request_payload)
    retrieved_knowledge = normalized_payload.get("knowledge_bundle", {})
    output_schema_instruction = json.dumps(
        normalized_payload.get("response_schema", {}),
        sort_keys=True,
        ensure_ascii=True,
    )
    sanitized_dynamic_payload = {
        key: value
        for key, value in normalized_payload.items()
        if key not in {"knowledge_bundle", "response_schema"}
    }
    return PromptAuditInput(
        system_policy=system_prompt,
        retrieved_knowledge=retrieved_knowledge,
        sanitized_dynamic_payload=sanitized_dynamic_payload,
        output_schema_instruction=output_schema_instruction,
        stage=stage,
        opaque_case_id=opaque_case_id,
        trial_id=trial_id,
    )


def _is_text_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return False
    return b"\x00" not in chunk


def _git_output(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def is_git_tracked(path: Path) -> bool:
    relative = _safe_relative(path)
    code, stdout, _ = _git_output("ls-files", "--", relative)
    return code == 0 and bool(stdout.strip())


def is_git_ignored(path_like: str | Path) -> bool:
    relative = _safe_relative(Path(path_like))
    return _git_output("check-ignore", relative)[0] == 0


def _normalize_secret_value(value: str) -> str:
    cleaned = value.strip()
    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0].strip()
    cleaned = cleaned.strip(" \t\r\n,;")
    if cleaned.startswith(("'", '"', "`", "(", "[", "{")):
        cleaned = cleaned[1:].strip()
    if cleaned.endswith(("'", '"', "`", ")", "]", "}")):
        cleaned = cleaned[:-1].strip()
    if cleaned.startswith(("'", '"')) and cleaned.endswith(("'", '"')) and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _placeholder_words(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^A-Za-z0-9]+", value.lower())
        if token
    }


def is_placeholder_secret_value(value: str) -> bool:
    normalized = _normalize_secret_value(value)
    if not normalized:
        return False
    words = _placeholder_words(normalized)
    return bool(words) and words <= PLACEHOLDER_SECRET_WORDS


def looks_like_real_secret_value(value: str) -> bool:
    normalized = _normalize_secret_value(value)
    if not normalized:
        return False
    if is_placeholder_secret_value(normalized):
        return False
    if normalized.startswith("sk-") and len(normalized) >= 12:
        return True
    if len(normalized) < 20:
        return False
    has_lower = any(char.islower() for char in normalized)
    has_upper = any(char.isupper() for char in normalized)
    has_digit = any(char.isdigit() for char in normalized)
    has_symbol = any(not char.isalnum() for char in normalized)
    diversity = sum((has_lower, has_upper, has_digit, has_symbol))
    unique_ratio = len(set(normalized)) / max(len(normalized), 1)
    return diversity >= 2 and unique_ratio >= 0.45


def scan_text_for_secret_matches(text: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        env_match = ENV_ASSIGNMENT_RE.match(line)
        if env_match:
            value = _normalize_secret_value(env_match.group("value"))
            if looks_like_real_secret_value(value):
                key = ("deepseek_env_assignment", value)
                if key not in seen:
                    seen.add(key)
                    matches.append({"match_type": "deepseek_env_assignment"})
            continue

        auth_match = AUTHORIZATION_HEADER_RE.search(line)
        if auth_match:
            value = _normalize_secret_value(auth_match.group("value"))
            if looks_like_real_secret_value(value):
                key = ("authorization_header", value)
                if key not in seen:
                    seen.add(key)
                    matches.append({"match_type": "authorization_header"})
            continue

        api_key_match = API_KEY_LITERAL_RE.search(line)
        if api_key_match:
            value = _normalize_secret_value(api_key_match.group("value"))
            if looks_like_real_secret_value(value):
                key = ("hardcoded_api_key_literal", value)
                if key not in seen:
                    seen.add(key)
                    matches.append({"match_type": "hardcoded_api_key_literal"})
            continue

        bearer_match = BEARER_TOKEN_RE.search(line)
        if bearer_match:
            value = _normalize_secret_value(bearer_match.group("value"))
            if looks_like_real_secret_value(value):
                key = ("bearer_token", value)
                if key not in seen:
                    seen.add(key)
                    matches.append({"match_type": "bearer_token"})
            continue

        for sk_match in SK_TOKEN_RE.finditer(line):
            value = _normalize_secret_value(sk_match.group("value"))
            if looks_like_real_secret_value(value):
                key = ("sk_prefix", value)
                if key not in seen:
                    seen.add(key)
                    matches.append({"match_type": "sk_prefix"})
    return matches


def audit_env_example(path: Path = ENV_EXAMPLE_PATH) -> dict[str, Any]:
    file_exists = path.exists()
    tracked_by_git = file_exists and is_git_tracked(path)
    content = path.read_text(encoding="utf-8", errors="ignore") if file_exists else ""
    env_match = ENV_ASSIGNMENT_RE.search(content)
    api_key_variable_present = env_match is not None
    api_key_value = _normalize_secret_value(env_match.group("value")) if env_match else ""
    api_key_value_empty = api_key_variable_present and api_key_value == ""
    realistic_key_placeholder_present = looks_like_real_secret_value(api_key_value)
    authorization_header_present = bool(AUTHORIZATION_HEADER_RE.search(content))
    safe = (
        file_exists
        and tracked_by_git
        and api_key_variable_present
        and api_key_value_empty
        and not realistic_key_placeholder_present
        and not authorization_header_present
    )
    return {
        "file_exists": file_exists,
        "tracked_by_git": tracked_by_git,
        "api_key_variable_present": api_key_variable_present,
        "api_key_value_empty": api_key_value_empty,
        "realistic_key_placeholder_present": realistic_key_placeholder_present,
        "authorization_header_present": authorization_header_present,
        "safe": safe,
    }


def classify_worktree_category(relative_path: str) -> str:
    path = relative_path.replace("\\", "/")
    lowered = path.lower()
    if path.startswith(ALLOWED_PRELIVE_ARTIFACT_ROOTS):
        return "GENERATED_PRELIVE_ARTIFACT"
    if path in {".env", ".env.local"} or lowered.endswith(".env"):
        return "SECRET"
    if path == ".env.example" or path.startswith("spec2testbench/config/") or path.startswith("experiments/deepseek_live_v1/"):
        return "CONFIGURATION"
    if path.startswith("tests/"):
        return "TEST"
    if "/prompts/" in path or path.endswith("_prompt.txt") or path.endswith("_prompt.md"):
        return "PROMPT"
    if path.startswith("scripts/") or path.startswith("spec2testbench/"):
        return "SOURCE_CODE"
    if path.startswith("knowledge/"):
        return "CONFIGURATION"
    if path.startswith("benchmark/"):
        return "SOURCE_CODE"
    if path.startswith("reports/") or path.startswith("results/") or path.startswith("artifacts/"):
        return "CACHE"
    if path.endswith(".md"):
        return "DOCUMENTATION"
    if any(token in lowered for token in ("tmp", "temp", ".cache", "__pycache__")):
        return "TEMPORARY"
    return "UNKNOWN"


def freeze_invalidation_reason(relative_path: str) -> str | None:
    path = relative_path.replace("\\", "/")
    if path.startswith(ALLOWED_PRELIVE_ARTIFACT_ROOTS):
        return None
    if path.startswith(("reports/", "results/", "artifacts/")):
        return "ARTIFACT_OUTSIDE_ALLOWED_ROOT"
    if "/prompts/" in path or path.endswith("_prompt.txt") or path.endswith("_prompt.md"):
        return "PROMPT"
    if path.startswith("knowledge/"):
        return "KNOWLEDGE"
    if path.startswith("benchmark/"):
        return "BENCHMARK"
    if path.endswith("canonical_harness_policies.yaml"):
        return "HARNESS_POLICY"
    if path.endswith("testbench_plan_compiler.py"):
        return "COMPILER"
    if path.endswith("testbench_plan.py"):
        return "SCHEMA"
    if path.startswith("spec2testbench/application/usecases/") or path.endswith("run_verification.py"):
        return "CHECKER"
    if path.startswith("experiments/deepseek_live_v1/") or path == ".env.example":
        return "CONFIGURATION"
    if path.startswith(FREEZE_SENSITIVE_ROOTS):
        return "SOURCE"
    if path.endswith(".md"):
        return None
    return "UNKNOWN"


def invalidates_source_freeze(relative_path: str) -> bool:
    return freeze_invalidation_reason(relative_path) is not None


def parse_status_line(line: str) -> tuple[str, str]:
    normalized = line.rstrip()
    if not normalized:
        return "", ""
    if len(normalized) >= 3 and normalized[0] in {"M", "A", "D", "R", "C", "U"} and normalized[1] == " " and normalized[2] != " ":
        status = f"{normalized[0]} "
        path = normalized[2:].replace("\\", "/")
    else:
        status = normalized[:2]
        path = normalized[3:].replace("\\", "/") if len(normalized) > 3 else ""
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return status, path


def ensure_campaign_directories() -> None:
    for path in (
        EXPERIMENTS_DIR,
        ARTIFACTS_DIR,
        RESULTS_DIR,
        REPORTS_DIR,
        ARTIFACTS_DIR / "provider_smoke",
        ARTIFACTS_DIR / "single_cases" / "ac_gain",
        ARTIFACTS_DIR / "single_cases" / "transient_delay",
        ARTIFACTS_DIR / "single_cases" / "oscillator",
        ARTIFACTS_DIR / "single_cases" / "schmitt",
        ARTIFACTS_DIR / "use_case_smoke",
        ARTIFACTS_DIR / "frozen_v3" / "trial_1",
        ARTIFACTS_DIR / "frozen_v3" / "trial_2",
        ARTIFACTS_DIR / "frozen_v3" / "trial_3",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _record_to_case(record: dict[str, Any]) -> CampaignCase:
    targeted = record.get("targeted_metric", {})
    metric_name = targeted.get("name") if isinstance(targeted, dict) else str(targeted or "")
    return CampaignCase(
        case_id=str(record["case_id"]),
        parent_circuit_id=str(record.get("parent_circuit_id", record["case_id"])),
        ground_truth_label=str(record.get("ground_truth_label", "")),
        circuit_family=str(record.get("circuit_family", "")),
        specification_file=ROOT / str(record["specification_file"]),
        netlist_file=ROOT / str(record["netlist_file"]),
        targeted_metric=metric_name,
    )


def _load_manifest_cases(path: Path) -> list[CampaignCase]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [_record_to_case(record) for record in payload.get("cases", [])]


def default_use_case_cases() -> list[CampaignCase]:
    if LEGACY_USE_CASE_MANIFEST.exists():
        return _load_manifest_cases(LEGACY_USE_CASE_MANIFEST)
    return [
        CampaignCase(
            case_id="smoke_p10_cutoff",
            parent_circuit_id="p10_lowpass",
            ground_truth_label="SMOKE_REFERENCE",
            circuit_family="low_pass_filter",
            specification_file=ROOT / "examples/benchmark_specs/p10_lowpass.yaml",
            netlist_file=ROOT / "benchmark/analogcoder_pro/p10_lowpass.cir",
            targeted_metric="cutoff_frequency_hz",
        )
    ]


def default_frozen_cases() -> list[CampaignCase]:
    if LEGACY_FROZEN_MANIFEST.exists():
        return _load_manifest_cases(LEGACY_FROZEN_MANIFEST)
    return []


def default_single_cases() -> dict[str, CampaignCase]:
    use_case_cases = {case.case_id: case for case in default_use_case_cases()}
    return {
        "single_ac": use_case_cases.get("smoke_p01_gain")
        or CampaignCase(
            case_id="smoke_p01_gain",
            parent_circuit_id="p01_amplifier",
            ground_truth_label="SMOKE_REFERENCE",
            circuit_family="amplifier",
            specification_file=ROOT / "examples/benchmark_specs/p01_amplifier.yaml",
            netlist_file=ROOT / "benchmark/analogcoder_pro/p01_amplifier.cir",
            targeted_metric="dc_gain_db",
        ),
        "single_transient": use_case_cases.get("smoke_p09_delay")
        or CampaignCase(
            case_id="smoke_p09_delay",
            parent_circuit_id="p09_comparator",
            ground_truth_label="SMOKE_REFERENCE",
            circuit_family="comparator",
            specification_file=ROOT / "examples/benchmark_specs/p09_comparator.yaml",
            netlist_file=ROOT / "benchmark/analogcoder_pro/p09_comparator.cir",
            targeted_metric="propagation_delay",
        ),
        "single_oscillator": use_case_cases.get("smoke_p22_frequency")
        or CampaignCase(
            case_id="smoke_p22_frequency",
            parent_circuit_id="p22_oscillator",
            ground_truth_label="SMOKE_REFERENCE",
            circuit_family="oscillator",
            specification_file=ROOT / "examples/benchmark_specs/p22_oscillator.yaml",
            netlist_file=ROOT / "benchmark/analogcoder_pro/p22_oscillator.cir",
            targeted_metric="oscillator_frequency",
        ),
        "single_schmitt": use_case_cases.get("smoke_p28_hysteresis")
        or CampaignCase(
            case_id="smoke_p28_hysteresis",
            parent_circuit_id="p28_schmitt",
            ground_truth_label="SMOKE_REFERENCE",
            circuit_family="schmitt_trigger",
            specification_file=ROOT / "experiments/llm_deepseek/specifications/smoke_p28_schmitt_hysteresis.yaml",
            netlist_file=ROOT / "benchmark/analogcoder_pro/p28_schmitt.cir",
            targeted_metric="hysteresis_width",
        ),
    }


def write_default_manifests() -> None:
    ensure_campaign_directories()
    single_cases = default_single_cases()
    use_case_cases = default_use_case_cases()
    frozen_cases = default_frozen_cases()

    provider_smoke_payload = {
        "campaign": CAMPAIGN_NAME,
        "manifest_name": "provider_smoke_manifest",
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "cases": [
            {
                "case_id": "smoke_p10_cutoff",
                "parent_circuit_id": "p10_lowpass",
                "ground_truth_label": "SMOKE_REFERENCE",
                "circuit_family": "low_pass_filter",
                "specification_file": "examples/benchmark_specs/p10_lowpass.yaml",
                "netlist_file": "benchmark/analogcoder_pro/p10_lowpass.cir",
                "targeted_metric": {"name": "cutoff_frequency_hz"},
            }
        ],
    }
    single_payload = {
        "campaign": CAMPAIGN_NAME,
        "manifest_name": "single_case_manifest",
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "cases": [
            {
                "case_id": case.case_id,
                "parent_circuit_id": case.parent_circuit_id,
                "ground_truth_label": case.ground_truth_label,
                "circuit_family": case.circuit_family,
                "specification_file": _safe_relative(case.specification_file),
                "netlist_file": _safe_relative(case.netlist_file),
                "targeted_metric": {"name": case.targeted_metric},
            }
            for case in single_cases.values()
        ],
    }
    use_case_payload = {
        "campaign": CAMPAIGN_NAME,
        "manifest_name": "use_case_smoke_manifest",
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "cases": [
            {
                "case_id": case.case_id,
                "parent_circuit_id": case.parent_circuit_id,
                "ground_truth_label": case.ground_truth_label,
                "circuit_family": case.circuit_family,
                "specification_file": _safe_relative(case.specification_file),
                "netlist_file": _safe_relative(case.netlist_file),
                "targeted_metric": {"name": case.targeted_metric},
            }
            for case in use_case_cases
        ],
    }
    frozen_case_payload = {
        "campaign": CAMPAIGN_NAME,
        "manifest_name": "frozen_case_manifest",
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "cases": [
            {
                "case_id": case.case_id,
                "parent_circuit_id": case.parent_circuit_id,
                "ground_truth_label": case.ground_truth_label,
                "circuit_family": case.circuit_family,
                "specification_file": _safe_relative(case.specification_file),
                "netlist_file": _safe_relative(case.netlist_file),
                "targeted_metric": {"name": case.targeted_metric},
            }
            for case in frozen_cases
        ],
    }
    frozen_protocol_payload = {
        "campaign": CAMPAIGN_NAME,
        "manifest_name": "frozen_protocol_manifest",
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "knowledge_version": KNOWLEDGE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "checker_version": CHECKER_VERSION,
        "provider_mode": "LIVE",
        "scientific_llm_evidence": False,
        "cases_manifest": "experiments/deepseek_live_v1/frozen_case_manifest.yaml",
    }

    write_yaml(EXPERIMENTS_DIR / "provider_smoke_manifest.yaml", provider_smoke_payload)
    write_yaml(EXPERIMENTS_DIR / "single_case_manifest.yaml", single_payload)
    write_yaml(EXPERIMENTS_DIR / "use_case_smoke_manifest.yaml", use_case_payload)
    write_yaml(EXPERIMENTS_DIR / "frozen_case_manifest.yaml", frozen_case_payload)
    write_yaml(EXPERIMENTS_DIR / "frozen_protocol_manifest.yaml", frozen_protocol_payload)


def collect_git_state() -> dict[str, Any]:
    _, status_short, _ = _git_output("status", "--short")
    _, diff_stat, _ = _git_output("diff", "--stat")
    _, source_freeze_diff, _ = _git_output(
        "diff",
        "--",
        "spec2testbench/",
        "scripts/",
        "tests/",
        "knowledge/",
        "configs/",
        "examples/",
    )
    _, head, _ = _git_output("rev-parse", "HEAD")
    _, branch, _ = _git_output("branch", "--show-current")
    modified_lines = [line for line in status_short.splitlines() if line.strip()]
    modified_paths = [path for _, path in (parse_status_line(line) for line in modified_lines) if path]
    benchmark_modified = any(path.startswith("benchmark/analogcoder_pro/") for path in modified_paths)
    knowledge_modified = any(path.startswith("knowledge/") for path in modified_paths)
    frozen_v3_modified = any(
        path.startswith("experiments/frozen_pilot_v3/")
        or path == "experiments/frozen_pilot_v3/reference_results.csv"
        for path in modified_paths
    )
    scientific_dirty_paths = sorted(path for path in modified_paths if invalidates_source_freeze(path))
    scientific_worktree_clean = not scientific_dirty_paths
    source_freeze_modified = not scientific_worktree_clean
    spice_book_pdf_matches = [
        path for path in ROOT.rglob("*")
        if path.is_file() and "spice" in path.name.lower() and "book" in path.name.lower() and path.suffix.lower() == ".pdf"
    ]
    spice_book_pdf_ignored = True
    for path in spice_book_pdf_matches:
        code, _, _ = _git_output("check-ignore", _safe_relative(path))
        spice_book_pdf_ignored = spice_book_pdf_ignored and code == 0
    commit_present = bool(head.strip())
    worktree_clean = not modified_lines
    go_code_freeze = (
        commit_present
        and worktree_clean
        and scientific_worktree_clean
        and not benchmark_modified
        and not knowledge_modified
        and not frozen_v3_modified
        and spice_book_pdf_ignored
    )
    return {
        "branch": branch.strip(),
        "git_commit": head.strip(),
        "worktree_clean": worktree_clean,
        "status_short_lines": modified_lines,
        "modified_paths": modified_paths,
        "diff_stat": diff_stat.strip(),
        "source_freeze_diff": source_freeze_diff.strip(),
        "source_freeze_modified": source_freeze_modified,
        "original_benchmark_files_modified": benchmark_modified,
        "knowledge_files_modified": knowledge_modified,
        "frozen_v3_files_modified": frozen_v3_modified,
        "scientific_worktree_clean": scientific_worktree_clean,
        "scientific_dirty_paths": scientific_dirty_paths,
        "spice_book_pdf_matches": [_safe_relative(path) for path in spice_book_pdf_matches],
        "spice_book_pdf_ignored": spice_book_pdf_ignored,
        "commit_present": commit_present,
        "go_code_freeze": go_code_freeze,
    }


def _scan_secrets_in_file(path: Path) -> list[dict[str, str]]:
    if not _is_text_file(path):
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [
        {"path": _safe_relative(path), "match_type": item["match_type"]}
        for item in scan_text_for_secret_matches(content)
    ]


def run_env_example_audit() -> dict[str, Any]:
    ensure_campaign_directories()
    payload = {
        "timestamp": utc_now_iso(),
        **audit_env_example(),
    }
    write_json(ENV_EXAMPLE_AUDIT_JSON, payload)
    write_markdown(
        ENV_EXAMPLE_AUDIT_MD,
        [
            "# DeepSeek Live .env.example Audit",
            "",
            f"- Timestamp: {payload['timestamp']}",
            f"- File found: {str(payload['file_exists']).lower()}",
            f"- Tracked: {str(payload['tracked_by_git']).lower()}",
            f"- API key variable: {str(payload['api_key_variable_present']).lower()}",
            f"- API key value empty: {str(payload['api_key_value_empty']).lower()}",
            f"- Realistic secret placeholder: {str(payload['realistic_key_placeholder_present']).lower()}",
            f"- Authorization header present: {str(payload['authorization_header_present']).lower()}",
            f"- Safe: {str(payload['safe']).lower()}",
        ],
    )
    return payload


def _iter_campaign_artifact_paths() -> list[str]:
    discovered: list[str] = []
    for root_name in ALLOWED_PRELIVE_ARTIFACT_ROOTS:
        base = ROOT / root_name.rstrip("/")
        if not base.exists():
            continue
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            discovered.append(_safe_relative(path))
    return discovered


def collect_worktree_inventory() -> list[dict[str, Any]]:
    code, status_stdout, _ = _git_output("status", "--short", "--untracked-files=all")
    rows_by_path: dict[str, dict[str, Any]] = {}

    def add_path(path: str, status: str, discovered_via: str) -> None:
        normalized = path.replace("\\", "/")
        if not normalized:
            return
        full_path = ROOT / normalized
        category = classify_worktree_category(normalized)
        freeze_reason = freeze_invalidation_reason(normalized)
        rows_by_path[normalized] = {
            "path": normalized,
            "status": status,
            "category": category,
            "discovered_via": discovered_via,
            "tracked_by_git": is_git_tracked(full_path),
            "ignored_by_git": is_git_ignored(normalized),
            "exists_on_disk": full_path.exists(),
            "invalidates_source_freeze": bool(freeze_reason),
            "freeze_invalidation_reason": freeze_reason or "",
        }

    if code == 0 and status_stdout:
        for line in status_stdout.splitlines():
            status, path = parse_status_line(line)
            if path:
                add_path(path, status, "git_status")

    for path in _iter_campaign_artifact_paths():
        if path not in rows_by_path:
            add_path(path, "!!", "allowed_campaign_artifact")

    for path in sorted(ROOT.glob(".env*")):
        relative = _safe_relative(path)
        if relative == ".env.example":
            continue
        if relative not in rows_by_path:
            add_path(relative, "!!", "local_env_file")

    return [rows_by_path[path] for path in sorted(rows_by_path)]


def _inventory_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row["category"])
        counts[category] = counts.get(category, 0) + 1
    return counts


def _commit_plan_bucket(row: dict[str, Any]) -> str:
    path = str(row["path"])
    category = str(row["category"])
    if category == "SECRET":
        return "FILES_TO_EXCLUDE"
    if category == "TEMPORARY":
        return "FILES_TO_DELETE_AS_TEMPORARY"
    if category == "CACHE":
        return "FILES_TO_EXCLUDE"
    if category == "GENERATED_PRELIVE_ARTIFACT":
        return "FILES_REQUIRING_REVIEW" if Path(path).name in REVIEWABLE_PRELIVE_ARTIFACT_NAMES else "FILES_TO_EXCLUDE"
    if category == "DOCUMENTATION":
        return "FILES_REQUIRING_REVIEW" if path == "README.md" else "FILES_TO_COMMIT"
    if category in {"SOURCE_CODE", "TEST", "PROMPT", "CONFIGURATION"}:
        return "FILES_TO_COMMIT"
    return "FILES_REQUIRING_REVIEW"


def build_pre_commit_inventory() -> dict[str, Any]:
    ensure_campaign_directories()
    rows = collect_worktree_inventory()
    counts = _inventory_counts(rows)
    write_csv(
        PRE_COMMIT_INVENTORY_CSV,
        rows,
        fieldnames=[
            "path",
            "status",
            "category",
            "discovered_via",
            "tracked_by_git",
            "ignored_by_git",
            "exists_on_disk",
            "invalidates_source_freeze",
            "freeze_invalidation_reason",
        ],
    )
    inventory_lines = [
        f"- `{row['path']}` | status `{row['status']}` | category `{row['category']}` | freeze `{str(row['invalidates_source_freeze']).lower()}`"
        for row in rows
    ]
    write_markdown(
        PRE_COMMIT_INVENTORY_MD,
        [
            "# DeepSeek Live Pre-Commit Inventory",
            "",
            f"- Generated at: {utc_now_iso()}",
            f"- Modified files: {len(rows)}",
            f"- Source files: {counts.get('SOURCE_CODE', 0)}",
            f"- Test files: {counts.get('TEST', 0)}",
            f"- Prompt files: {counts.get('PROMPT', 0)}",
            f"- Configuration files: {counts.get('CONFIGURATION', 0)}",
            f"- Documentation files: {counts.get('DOCUMENTATION', 0)}",
            f"- Generated artifacts: {counts.get('GENERATED_PRELIVE_ARTIFACT', 0)}",
            f"- Temporary files: {counts.get('TEMPORARY', 0)}",
            f"- Secret files: {counts.get('SECRET', 0)}",
            f"- Scientific worktree clean: {str(not any(row['invalidates_source_freeze'] for row in rows)).lower()}",
            "",
            "## Entries",
            *(inventory_lines or ["- None"]),
        ],
    )
    return {
        "rows": rows,
        "counts": counts,
        "scientific_worktree_clean": not any(row["invalidates_source_freeze"] for row in rows),
    }


def build_clean_commit_plan() -> dict[str, Any]:
    ensure_campaign_directories()
    rows = collect_worktree_inventory()
    manifest_rows: list[dict[str, Any]] = []
    buckets: dict[str, list[str]] = {
        "FILES_TO_COMMIT": [],
        "FILES_TO_EXCLUDE": [],
        "FILES_TO_DELETE_AS_TEMPORARY": [],
        "FILES_REQUIRING_REVIEW": [],
    }
    for row in rows:
        bucket = _commit_plan_bucket(row)
        buckets[bucket].append(str(row["path"]))
        manifest_rows.append(
            {
                "bucket": bucket,
                "path": row["path"],
                "status": row["status"],
                "category": row["category"],
                "invalidates_source_freeze": row["invalidates_source_freeze"],
                "freeze_invalidation_reason": row["freeze_invalidation_reason"],
            }
        )
    commit_lines = [f"- `{path}`" for path in buckets["FILES_TO_COMMIT"]] or ["- None"]
    exclude_lines = [f"- `{path}`" for path in buckets["FILES_TO_EXCLUDE"]] or ["- None"]
    delete_lines = [f"- `{path}`" for path in buckets["FILES_TO_DELETE_AS_TEMPORARY"]] or ["- None"]
    review_lines = [f"- `{path}`" for path in buckets["FILES_REQUIRING_REVIEW"]] or ["- None"]
    write_csv(
        CLEAN_COMMIT_MANIFEST_CSV,
        manifest_rows,
        fieldnames=[
            "bucket",
            "path",
            "status",
            "category",
            "invalidates_source_freeze",
            "freeze_invalidation_reason",
        ],
    )
    lines = [
        "# DeepSeek Live Clean Commit Plan",
        "",
        f"- Generated at: {utc_now_iso()}",
        f"- Files to commit: {len(buckets['FILES_TO_COMMIT'])}",
        f"- Files to exclude: {len(buckets['FILES_TO_EXCLUDE'])}",
        f"- Files to delete as temporary: {len(buckets['FILES_TO_DELETE_AS_TEMPORARY'])}",
        f"- Files requiring review: {len(buckets['FILES_REQUIRING_REVIEW'])}",
        "",
        "FILES_TO_COMMIT",
        *commit_lines,
        "",
        "FILES_TO_EXCLUDE",
        *exclude_lines,
        "",
        "FILES_TO_DELETE_AS_TEMPORARY",
        *delete_lines,
        "",
        "FILES_REQUIRING_REVIEW",
        *review_lines,
    ]
    write_markdown(CLEAN_COMMIT_PLAN_MD, lines)
    return buckets


def run_secret_audit() -> dict[str, Any]:
    ensure_campaign_directories()
    env_example_audit = run_env_example_audit()
    code, tracked_stdout, _ = _git_output("ls-files", "-z")
    tracked_paths = set()
    if code == 0 and tracked_stdout:
        tracked_paths = {
            item.replace("\\", "/")
            for item in tracked_stdout.split("\x00")
            if item
        }
    tracked_matches: list[dict[str, str]] = []
    untracked_matches: list[dict[str, str]] = []
    grep_code, grep_stdout, _ = _git_output(
        "grep",
        "-I",
        "-n",
        "-e",
        "DEEPSEEK_API_KEY=",
        "-e",
        "Authorization:",
        "-e",
        "Bearer ",
        "-e",
        "sk-",
        "-e",
        "api_key",
        "--",
        ".",
    )
    tracked_candidate_paths: set[str] = set()
    if grep_code in {0, 1} and grep_stdout:
        for line in grep_stdout.splitlines():
            path_part = line.split(":", 1)[0].replace("\\", "/")
            if path_part in tracked_paths:
                tracked_candidate_paths.add(path_part)
    tracked_candidates = sorted(ROOT / relative for relative in tracked_candidate_paths if (ROOT / relative).is_file())
    seen_untracked: set[str] = set()
    untracked_roots = [
        ROOT / "scripts",
        ROOT / "results",
        ROOT / "reports",
        ROOT / "artifacts",
    ]

    def should_scan(path: Path) -> bool:
        if not path.is_file():
            return False
        if ".git" in path.parts or "__pycache__" in path.parts:
            return False
        if path.name.startswith(".env"):
            return True
        return path.suffix.lower() in SCANNABLE_SUFFIXES

    for path in tracked_candidates:
        if not should_scan(path):
            continue
        tracked_matches.extend(_scan_secrets_in_file(path))

    untracked_candidates: list[Path] = []
    rg_executable = shutil.which("rg")
    if rg_executable:
        search_roots = [str(base.relative_to(ROOT)) for base in untracked_roots if base.exists()]
        if search_roots:
            completed = subprocess.run(
                [
                    rg_executable,
                    "-l",
                    "-I",
                    "-e",
                    "DEEPSEEK_API_KEY=",
                    "-e",
                    "Authorization:",
                    "-e",
                    "Bearer ",
                    "-e",
                    "sk-",
                    "-e",
                    "api_key",
                    *search_roots,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode in {0, 1} and completed.stdout:
                for line in completed.stdout.splitlines():
                    candidate = ROOT / line.strip()
                    if should_scan(candidate):
                        untracked_candidates.append(candidate)
    else:
        for base in untracked_roots:
            if not base.exists():
                continue
            untracked_candidates.extend(path for path in base.rglob("*") if should_scan(path))
    untracked_candidates.extend(path for path in ROOT.glob(".env*") if should_scan(path))

    for path in sorted(untracked_candidates):
        relative = _safe_relative(path)
        if relative in tracked_paths or relative in seen_untracked:
            continue
        seen_untracked.add(relative)
        untracked_matches.extend(_scan_secrets_in_file(path))
    environment_key_configured = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
    key_value_detected = any(
        item["match_type"] in {"deepseek_env_assignment", "sk_prefix", "hardcoded_api_key_literal"}
        for item in tracked_matches + untracked_matches
    )
    authorization_header_matches = sum(
        1
        for item in tracked_matches + untracked_matches
        if item["match_type"] in {"authorization_header", "bearer_token"}
    )
    env_ignored = _git_output("check-ignore", ".env")[0] == 0
    go_secret_safety = (
        not tracked_matches
        and not untracked_matches
        and env_ignored
        and env_example_audit["safe"]
    )
    result = {
        "timestamp": utc_now_iso(),
        "env_example_audit": env_example_audit,
        "tracked_secret_matches": tracked_matches,
        "untracked_secret_matches": untracked_matches,
        "tracked_secret_count": len(tracked_matches),
        "untracked_secret_count": len(untracked_matches),
        "environment_key_configured": environment_key_configured,
        "key_value_detected": key_value_detected,
        "key_value_logged": False,
        "authorization_header_matches": authorization_header_matches,
        "authorization_header_logged": False,
        "values_redacted": True,
        "false_positive_rules_corrected": True,
        "go_secret_safety": "PASS" if go_secret_safety else "NO_GO",
        "env_ignored": env_ignored,
    }
    match_lines = [f"- `{item['path']}` [{item['match_type']}]" for item in tracked_matches + untracked_matches]
    write_json(RESULTS_DIR / "secret_audit.json", result)
    write_markdown(
        REPORTS_DIR / "secret_audit.md",
        [
            "# DeepSeek Live Secret Audit",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- API key configured: {str(environment_key_configured).lower()}",
            f"- Tracked secret matches: {len(tracked_matches)}",
            f"- Untracked secret matches: {len(untracked_matches)}",
            f"- Authorization headers: {authorization_header_matches}",
            f"- Values redacted: {str(result['values_redacted']).lower()}",
            f"- False-positive rules corrected: {str(result['false_positive_rules_corrected']).lower()}",
            f"- .env ignored by Git: {str(env_ignored).lower()}",
            f"- GO_SECRET_SAFETY: {result['go_secret_safety']}",
            "",
            "## Matches",
            *(match_lines or ["- None"]),
        ],
    )
    return result


def _request_template_sha256() -> str:
    template = {
        "task": "",
        "case_id": "",
        "circuit_family": "",
        "available_nodes": [],
        "canonical_circuit_representation": {},
        "supply_information": {},
        "requested_metrics": [],
        "supported_capabilities": {},
        "normalized_specification": {},
        "deterministic_plan_summary": {},
        "response_schema": {},
        "provider_mode": "",
        "scientific_llm_evidence": False,
        "knowledge_version": "",
        "knowledge_bundle": {},
        "knowledge_bundle_sha256": "",
        "opaque_case_id": "",
        "prompt_version": PROMPT_VERSION,
        "schema_version": RESPONSE_SCHEMA_VERSION,
    }
    return json_sha256(template)


def _resolve_ngspice_info() -> tuple[str, str]:
    environment_path = ROOT / "results/knowledge_book_v1/ngspice_environment.json"
    if environment_path.exists():
        payload = json.loads(environment_path.read_text(encoding="utf-8"))
        environment = payload.get("environment", {})
        executable = str(environment.get("ngspice_executable", "") or "")
        version = str(environment.get("ngspice_version", "") or "")
        if executable or version:
            return executable, version
    ngspice_path = shutil.which("ngspice") or ""
    if not ngspice_path:
        return "", ""
    try:
        completed = subprocess.run(
            [ngspice_path, "-v"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ngspice_path, ""
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    first_line = output.splitlines()[0].strip() if output else ""
    return ngspice_path, first_line


def _frozen_case_hashes() -> tuple[dict[str, str], dict[str, str]]:
    specification_hashes: dict[str, str] = {}
    dut_hashes: dict[str, str] = {}
    for case in default_frozen_cases():
        if case.specification_file.exists():
            specification_hashes[case.case_id] = sha256_file(case.specification_file)
        if case.netlist_file.exists():
            dut_hashes[case.case_id] = sha256_file(case.netlist_file)
    return specification_hashes, dut_hashes


def build_pre_live_manifest() -> dict[str, Any]:
    ensure_campaign_directories()
    write_default_manifests()
    git_state = collect_git_state()
    specification_hashes, dut_hashes = _frozen_case_hashes()
    ngspice_path, ngspice_version = _resolve_ngspice_info()
    knowledge_catalog = ROOT / "results/knowledge_book_v1/knowledge_rule_catalog_v2.csv"
    if not knowledge_catalog.exists():
        knowledge_catalog = ROOT / "results/knowledge_book_v1/knowledge_rule_catalog.csv"
    knowledge_validation = ROOT / "results/knowledge_book_v1/knowledge_validation.json"
    response_schema = TestbenchPlan.model_json_schema()
    payload = {
        "campaign_name": CAMPAIGN_NAME,
        "protocol_date": CAMPAIGN_PROTOCOL_DATE,
        "generated_at": utc_now_iso(),
        "branch": git_state["branch"],
        "git_commit": git_state["git_commit"],
        "worktree_clean": git_state["worktree_clean"],
        "scientific_worktree_clean": git_state["scientific_worktree_clean"],
        "commit_present": git_state["commit_present"],
        "source_freeze_modified": git_state["source_freeze_modified"],
        "original_benchmark_files_modified": git_state["original_benchmark_files_modified"],
        "frozen_v3_files_modified": git_state["frozen_v3_files_modified"],
        "spice_book_pdf_ignored": git_state["spice_book_pdf_ignored"],
        "python_version": sys.version.split()[0],
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "ngspice_path": ngspice_path,
        "ngspice_version": ngspice_version,
        "knowledge_version": KNOWLEDGE_VERSION,
        "knowledge_catalog_sha256": sha256_file(knowledge_catalog) if knowledge_catalog.exists() else "",
        "knowledge_validation_sha256": sha256_file(knowledge_validation) if knowledge_validation.exists() else "",
        "retriever_version": RETRIEVER_VERSION,
        "retriever_source_sha256": sha256_file(ROOT / "spec2testbench/application/services/spice_knowledge.py"),
        "system_prompt_version": PROMPT_VERSION,
        "system_prompt_sha256": sha256_file(PROMPT_PATH),
        "user_prompt_template_sha256": _request_template_sha256(),
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "response_schema_sha256": json_sha256(response_schema),
        "compiler_version": COMPILER_VERSION,
        "compiler_source_sha256": sha256_file(ROOT / "spec2testbench/application/services/testbench_plan_compiler.py"),
        "checker_version": CHECKER_VERSION,
        "checker_source_sha256": sha256_file(ROOT / "spec2testbench/application/usecases/run_verification.py"),
        "metric_registry_sha256": sha256_file(ROOT / "spec2testbench/application/services/llm_metric_registry.py"),
        "canonical_harness_policy_sha256": sha256_file(ROOT / "knowledge/spec2testbench/canonical_harness_policies.yaml"),
        "frozen_v3_manifest_sha256": sha256_file(ROOT / "experiments/frozen_pilot_v3/frozen_manifest.yaml"),
        "frozen_v3_specification_hashes": specification_hashes,
        "canonical_dut_hashes": dut_hashes,
        "provider_adapter_source_sha256": sha256_file(ROOT / "spec2testbench/infrastructure/llm/deepseek_provider.py"),
        "status_short_lines": git_state["status_short_lines"],
        "scientific_dirty_paths": git_state["scientific_dirty_paths"],
        "diff_stat": git_state["diff_stat"],
        "source_freeze_diff": git_state["source_freeze_diff"],
        "go_code_freeze": "PASS" if git_state["go_code_freeze"] else "NO_GO",
    }
    write_json(RESULTS_DIR / "pre_live_manifest.json", payload)
    write_markdown(
        REPORTS_DIR / "pre_live_manifest.md",
        [
            "# DeepSeek Live Pre-Live Manifest",
            "",
            f"- Campaign: {CAMPAIGN_NAME}",
            f"- Generated at: {payload['generated_at']}",
            f"- Branch: {payload['branch']}",
            f"- Git commit: {payload['git_commit']}",
            f"- Worktree clean: {str(payload['worktree_clean']).lower()}",
            f"- Scientific worktree clean: {str(payload['scientific_worktree_clean']).lower()}",
            f"- Source-freeze modified: {str(payload['source_freeze_modified']).lower()}",
            f"- Original benchmark files modified: {str(payload['original_benchmark_files_modified']).lower()}",
            f"- Frozen V3 files modified: {str(payload['frozen_v3_files_modified']).lower()}",
            f"- Knowledge version: {payload['knowledge_version']}",
            f"- Prompt version: {payload['system_prompt_version']}",
            f"- Response schema version: {payload['response_schema_version']}",
            f"- GO_CODE_FREEZE: {payload['go_code_freeze']}",
        ],
    )
    if not git_state["worktree_clean"]:
        blocker_lines = [f"- `{line}`" for line in git_state["status_short_lines"]]
        write_markdown(
            PRE_LIVE_WORKTREE_BLOCKER,
            [
                "# DeepSeek Live Pre-Live Worktree Blocker",
                "",
                f"- Generated at: {utc_now_iso()}",
                f"- Branch: {payload['branch']}",
                f"- Git commit: {payload['git_commit']}",
                f"- Worktree clean: false",
                f"- Scientific worktree clean: {str(payload['scientific_worktree_clean']).lower()}",
                f"- GO_CODE_FREEZE: {payload['go_code_freeze']}",
                f"- GO_PROVIDER_SMOKE: NOT_EXECUTED",
                "",
                "## Uncommitted Files",
                *(blocker_lines or ["- None"]),
                "",
                "## Scientific Dirty Paths",
                *([f"- `{path}`" for path in payload["scientific_dirty_paths"]] or ["- None"]),
            ],
        )
    return payload


def load_stage_context() -> dict[str, Any]:
    context = {
        "pre_live_manifest": build_pre_live_manifest(),
        "secret_audit": run_secret_audit(),
    }
    model_discovery_path = RESULTS_DIR / "model_discovery.json"
    if model_discovery_path.exists():
        context["model_discovery"] = json.loads(model_discovery_path.read_text(encoding="utf-8"))
    else:
        context["model_discovery"] = {}
    return context


def live_guard_state(*, require_full_campaign: bool) -> dict[str, Any]:
    run_llm_live = os.getenv("RUN_LLM_LIVE", "").strip() == "1"
    confirmation_ok = (
        os.getenv("DEEPSEEK_LIVE_CONFIRMATION", "").strip()
        == "I_UNDERSTAND_THIS_MAKES_API_CALLS"
    )
    full_campaign_ok = os.getenv("DEEPSEEK_FULL_CAMPAIGN_APPROVED", "").strip() == "1"
    status = "READY"
    if not run_llm_live:
        status = "LIVE_BLOCKED"
    elif not confirmation_ok:
        status = "CONFIRMATION_MISSING"
    elif require_full_campaign and not full_campaign_ok:
        status = "FULL_CAMPAIGN_APPROVAL_MISSING"
    return {
        "run_llm_live": run_llm_live,
        "confirmation_ok": confirmation_ok,
        "full_campaign_ok": full_campaign_ok,
        "status": status,
        "allowed": status == "READY",
    }


def run_model_discovery(*, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        validation = load_model_discovery_reuse_state()
        return {
            "stage": "model_discovery",
            "timestamp": utc_now_iso(),
            "run_id": current_run_id(),
            "execution_mode": "DRY_RUN",
            "configured_model": validation["configured_model"],
            "configured_model_available": validation["configured_model_available"],
            "artifact_reused": validation["reused_from_artifact"],
            "artifact_live_confirmed": validation["live_confirmed"],
            "artifact_timestamp": validation["artifact_timestamp"],
            "artifact_response_sha256": validation["artifact_response_sha256"],
            "validation_errors": validation["errors"],
            "GO_MODEL_DISCOVERY": "PASS" if validation["valid"] else "NO_GO",
        }
    context = load_stage_context()
    guard = live_guard_state(require_full_campaign=False)
    config = DeepSeekProviderConfig.from_env()
    configured_model = config.model
    allow_legacy_alias = os.getenv("ALLOW_LEGACY_DEEPSEEK_ALIAS", "").strip() == "1"
    result = {
        "timestamp": utc_now_iso(),
        "api_key_configured": bool(config.api_key),
        "base_url": config.base_url,
        "configured_model": configured_model,
        "legacy_alias": configured_model in LEGACY_DEEPSEEK_ALIASES,
        "legacy_alias_allowed": allow_legacy_alias,
        "model_ids": [],
        "models_returned": 0,
        "http_status": None,
        "request_id": None,
        "response_sha256": "",
        "configured_model_available": False,
        "campaign_model_status": "NOT_EXECUTED",
        "suitable_for_canonical_reporting": False,
        "recommended_model": "",
        "go_model_discovery": "NO_GO",
        "live_guard_status": guard["status"],
    }
    if context["pre_live_manifest"]["go_code_freeze"] != "PASS":
        result["campaign_model_status"] = "BLOCKED_BY_CODE_FREEZE"
    elif context["secret_audit"]["go_secret_safety"] != "PASS":
        result["campaign_model_status"] = "BLOCKED_BY_SECRET_AUDIT"
    elif guard["status"] != "READY":
        result["campaign_model_status"] = guard["status"]
    elif not config.api_key:
        result["campaign_model_status"] = "API_KEY_MISSING"
    else:
        provider = DeepSeekProvider(config)
        discovery = provider.discover_models()
        result["model_ids"] = [item["id"] for item in discovery["models"]]
        result["models_returned"] = len(result["model_ids"])
        result["http_status"] = discovery["http_status"]
        result["request_id"] = discovery["request_id"]
        result["response_sha256"] = discovery["response_sha256"]
        recommended = [model for model in result["model_ids"] if model not in LEGACY_DEEPSEEK_ALIASES]
        result["recommended_model"] = recommended[0] if recommended else (result["model_ids"][0] if result["model_ids"] else "")
        result["configured_model_available"] = bool(configured_model) and configured_model in result["model_ids"]
        if not configured_model:
            result["campaign_model_status"] = "MODEL_NOT_CONFIGURED"
        elif configured_model not in result["model_ids"]:
            result["campaign_model_status"] = "MODEL_NOT_RETURNED_BY_API"
        elif configured_model in LEGACY_DEEPSEEK_ALIASES and not allow_legacy_alias:
            result["campaign_model_status"] = "LEGACY_ALIAS_BLOCKED"
        elif configured_model in LEGACY_DEEPSEEK_ALIASES:
            result["campaign_model_status"] = "LEGACY_ALIAS"
        else:
            result["campaign_model_status"] = "READY"
            result["suitable_for_canonical_reporting"] = True
            result["go_model_discovery"] = "PASS"
            append_csv_rows(
                LIVE_CALL_AUDIT_CSV,
                [
                    {
                        "stage": "model_discovery",
                        "run_id": current_run_id(),
                        "case_id": "model_discovery",
                        "opaque_case_id": "model_discovery",
                        "trial_id": "trial_01",
                        "provider_call_performed": True,
                        "provider_boundary_reached": True,
                        "provider_status": "SUCCESS",
                        "latency_seconds": 0.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "retries": 0,
                        "cache_key": "",
                        "prompt_sha256": "",
                        "knowledge_bundle_sha256": "",
                    }
                ],
            )
    write_json(RESULTS_DIR / "model_discovery.json", result)
    write_markdown(
        REPORTS_DIR / "model_discovery.md",
        [
            "# DeepSeek Live Model Discovery",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- API key configured: {str(result['api_key_configured']).lower()}",
            f"- Base URL: {result['base_url']}",
            f"- Configured model: {result['configured_model'] or '<unset>'}",
            f"- Models returned: {result['models_returned']}",
            f"- Configured model available: {str(result['configured_model_available']).lower()}",
            f"- Legacy alias: {str(result['legacy_alias']).lower()}",
            f"- Campaign model status: {result['campaign_model_status']}",
            f"- Suitable for canonical reporting: {str(result['suitable_for_canonical_reporting']).lower()}",
            f"- GO_MODEL_DISCOVERY: {result['go_model_discovery']}",
        ],
    )
    return result


def infer_use_case(metric_name: str) -> str:
    metric_lower = metric_name.lower()
    if metric_lower in {"operating_point"}:
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


def classification_from_ground_truth(ground_truth_label: str, compliance_status: str) -> str:
    if compliance_status == "NOT_EVALUATED":
        return "UNEVALUATED"
    if ground_truth_label == "GROUND_TRUTH_COMPLIANT" and compliance_status == "PASS":
        return "TRUE_ACCEPT"
    if ground_truth_label == "GROUND_TRUTH_NONCOMPLIANT" and compliance_status == "FAIL":
        return "TRUE_DETECTION"
    if ground_truth_label == "GROUND_TRUTH_COMPLIANT" and compliance_status == "FAIL":
        return "FALSE_REJECT"
    if ground_truth_label == "GROUND_TRUTH_NONCOMPLIANT" and compliance_status == "PASS":
        return "FALSE_ACCEPT"
    return "UNEVALUATED"


def build_opaque_case_id(internal_case_id: str) -> str:
    digest = hashlib.sha256(f"{CAMPAIGN_SALT}{internal_case_id}".encode("utf-8")).hexdigest()
    return digest[:16]


def sanitized_specification(source: Specification, opaque_case_id: str) -> Specification:
    return Specification(
        name=f"opaque_case_{opaque_case_id}",
        circuit_type=source.circuit_type,
        performance_targets=copy.deepcopy(source.performance_targets),
        input_conditions=copy.deepcopy(source.input_conditions),
        test_categories=list(source.test_categories),
        process_corners=list(source.process_corners),
        temperature_range=source.temperature_range,
        supply_variation=source.supply_variation,
        technology=source.technology,
        description="",
        raw_specs="",
        case_id=opaque_case_id,
        parent_circuit_id=None,
        variant_overrides=[],
        measurement=copy.deepcopy(source.measurement),
    )


def audit_prompt_payload(
    *,
    stage: str | None = None,
    internal_case_id: str | None = None,
    opaque_case_id: str | None = None,
    trial_id: str | None = None,
    system_prompt: str | None = None,
    request_payload: dict[str, Any] | None = None,
    audit_input: PromptAuditInput | None = None,
) -> dict[str, Any]:
    if audit_input is None:
        if stage is None or opaque_case_id is None or trial_id is None or system_prompt is None or request_payload is None:
            raise ValueError("audit_prompt_payload requires either audit_input or explicit prompt components.")
        audit_input = build_prompt_audit_input(
            stage=stage,
            opaque_case_id=opaque_case_id,
            trial_id=trial_id,
            system_prompt=system_prompt,
            request_payload=request_payload,
        )
    system_audit = _audit_text_zone("system_policy", audit_input.system_policy)
    knowledge_audit = _audit_dynamic_zone("retrieved_knowledge", audit_input.retrieved_knowledge)
    payload_audit = _audit_dynamic_zone("sanitized_dynamic_payload", audit_input.sanitized_dynamic_payload)
    schema_audit = _audit_text_zone("output_schema_instruction", audit_input.output_schema_instruction)

    zone_audits = [system_audit, knowledge_audit, payload_audit, schema_audit]
    matched_sections = [zone.section for zone in zone_audits if zone.matched_rules]
    matched_rules = list(dict.fromkeys(code for zone in zone_audits for code in zone.matched_rules))
    rejection_reasons = list(dict.fromkeys(code for zone in zone_audits for code in zone.rejection_reasons))
    prompt_safe = all(zone.safe for zone in zone_audits)
    result = PromptLeakageAuditResult(
        stage=audit_input.stage,
        opaque_case_id=audit_input.opaque_case_id,
        trial_id=audit_input.trial_id,
        run_id=current_run_id(),
        system_policy_safe=system_audit.safe,
        retrieved_knowledge_safe=knowledge_audit.safe,
        dynamic_payload_safe=payload_audit.safe,
        schema_instruction_safe=schema_audit.safe,
        ground_truth_found=any(zone.ground_truth_found for zone in zone_audits),
        historical_verdict_found=any(zone.historical_verdict_found for zone in zone_audits),
        historical_metric_found=any(zone.historical_metric_found for zone in zone_audits),
        mutation_id_found=any(zone.mutation_id_found for zone in zone_audits),
        benchmark_name_found=any(zone.benchmark_name_found for zone in zone_audits),
        local_path_found=any(zone.local_path_found for zone in zone_audits),
        actual_sensitive_value_present=any(zone.actual_sensitive_value_present for zone in zone_audits),
        negative_policy_instruction_only=prompt_safe
        and any(code.endswith("NEGATIVE_POLICY_INSTRUCTION") for code in matched_rules)
        and not rejection_reasons,
        matched_sections=matched_sections,
        matched_rules=matched_rules,
        finding_count=len(matched_rules),
        rejection_reasons=rejection_reasons,
        prompt_safe=prompt_safe,
        prompt_sha256=audit_input.prompt_sha256(),
    )
    return result.to_dict()


def validate_model_discovery_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    configured_model = str(payload.get("configured_model", "") or "")
    model_ids = payload.get("model_ids", [])
    base_url = str(payload.get("base_url", "") or "").rstrip("/")
    if not payload:
        errors.append("artifact_missing")
    if not payload.get("api_key_configured"):
        errors.append("api_key_not_configured")
    if base_url != "https://api.deepseek.com":
        errors.append("unexpected_base_url")
    if payload.get("http_status") != 200:
        errors.append("http_status_not_200")
    if not configured_model:
        errors.append("configured_model_missing")
    if payload.get("configured_model_available") is not True:
        errors.append("configured_model_not_available")
    if payload.get("go_model_discovery") != "PASS":
        errors.append("go_model_discovery_not_pass")
    if not str(payload.get("response_sha256", "") or "").strip():
        errors.append("response_sha256_missing")
    if not str(payload.get("timestamp", "") or "").strip():
        errors.append("timestamp_missing")
    if configured_model and configured_model not in model_ids:
        errors.append("configured_model_not_in_model_ids")
    live_confirmed = payload.get("http_status") == 200 and bool(str(payload.get("response_sha256", "") or "").strip())
    return {
        "valid": not errors,
        "errors": errors,
        "artifact_exists": bool(payload),
        "configured_model": configured_model,
        "configured_model_available": payload.get("configured_model_available") is True,
        "artifact_timestamp": str(payload.get("timestamp", "") or ""),
        "artifact_response_sha256": str(payload.get("response_sha256", "") or ""),
        "models_returned": int(payload.get("models_returned", 0) or 0),
        "http_status": payload.get("http_status"),
        "base_url": base_url,
        "model_ids": list(model_ids) if isinstance(model_ids, list) else [],
        "live_confirmed": live_confirmed,
        "reused_from_artifact": not errors,
        "performed_current_run": False,
    }


def load_model_discovery_reuse_state() -> dict[str, Any]:
    validation = validate_model_discovery_artifact(read_json(RESULTS_DIR / "model_discovery.json", {}))
    return {
        "GO_MODEL_DISCOVERY": "PASS" if validation["valid"] else "NO_GO",
        **validation,
    }


def build_provider_smoke_prompt_audit_input() -> PromptAuditInput:
    system_prompt = PROVIDER_SMOKE_PROMPT_PATH.read_text(encoding="utf-8")
    expected_response = provider_smoke_expected_shape_payload()
    retrieved_knowledge = {
        "rule_ids": [
            "CHECKER_DOES_NOT_INFER_PASS_FROM_MISSING_EVIDENCE",
            "MISSING_METRIC_RETURNS_NOT_EVALUATED",
        ],
        "recipe_ids": [],
        "tool_ids": [],
        "semantic_guard_ids": [],
        "notes": "Use only the supplied smoke schema and example. Do not include a verdict.",
    }
    sanitized_dynamic_payload = {
        "task": "Return exactly one JSON object conforming to ProviderSmokeResponseV1.",
        "smoke_id": "provider_smoke",
        "response_schema_name": "ProviderSmokeResponseV1",
        "response_schema_version": "1.0",
        "required_fields": list(expected_response.keys()),
        "allowed_capabilities": [item.value for item in ProviderSmokeCapability],
        "required_constraints": [item.value for item in ProviderSmokeConstraint],
        "example_response": expected_response,
        "provider_mode": "LIVE",
        "scientific_llm_evidence": False,
        "prompt_version": PROVIDER_SMOKE_PROMPT_VERSION,
        "schema_version": PROVIDER_SMOKE_RESPONSE_SCHEMA_VERSION,
    }
    output_schema_instruction = "\n".join(
        [
            "Return exactly one JSON object that conforms to the supplied schema.",
            "No Markdown. No code fence. No explanation. No extra fields.",
            "Use the exact enum values and field names from the schema and example.",
            f"Schema name: ProviderSmokeResponseV1",
            f"Schema version: {expected_response['schema_version']}",
            f"Example JSON: {json.dumps(expected_response, sort_keys=True, ensure_ascii=True)}",
            f"JSON Schema: {json.dumps(provider_smoke_json_schema_payload(), sort_keys=True, ensure_ascii=True)}",
        ]
    )
    return PromptAuditInput(
        system_policy=system_prompt,
        retrieved_knowledge=retrieved_knowledge,
        sanitized_dynamic_payload=sanitized_dynamic_payload,
        output_schema_instruction=output_schema_instruction,
        stage="provider_smoke",
        opaque_case_id="provider_smoke",
        trial_id="trial_01",
    )


def _provider_smoke_payload_analysis(audit_result: dict[str, Any], audit_input: PromptAuditInput) -> dict[str, Any]:
    dynamic_payload = audit_input.sanitized_dynamic_payload
    serialized_payload = json.dumps(dynamic_payload, sort_keys=True, ensure_ascii=True)
    sensitive_paths = []
    benchmark_identifiers = 0
    frozen_identifiers = 0
    historical_values = 0
    local_paths = 0
    for path, value in _iter_prompt_audit_nodes(dynamic_payload, path="sanitized_dynamic_payload"):
        path_normalized = _safe_prompt_audit_path(path)
        key_name = path_normalized.split(".")[-1].split("[", 1)[0].lower()
        if key_name in PROMPT_AUDIT_SENSITIVE_KEYS:
            sensitive_paths.append(path_normalized)
        if isinstance(value, str):
            if PROMPT_AUDIT_BENCHMARK_VALUE_RE.search(value):
                benchmark_identifiers += 1
            if "frozen" in value.lower():
                frozen_identifiers += 1
            if _string_contains_prompt_audit_value(value, PROMPT_AUDIT_SENSITIVE_VALUE_TOKENS) or _string_contains_prompt_audit_value(
                value,
                PROMPT_AUDIT_HISTORY_METRIC_TOKENS,
            ):
                historical_values += 1
            if PROMPT_AUDIT_ABSOLUTE_PATH_RE.search(value) and not _is_safe_relative_prompt_path(value):
                local_paths += 1
    return {
        "opaque_case_id": audit_input.opaque_case_id,
        "trial_id": audit_input.trial_id,
        "task": dynamic_payload.get("task", ""),
        "requested_metrics": dynamic_payload.get("requested_metrics", []),
        "available_analysis_types": dynamic_payload.get("available_analysis_types", []),
        "available_harness_policies": dynamic_payload.get("available_harness_policies", []),
        "available_recipe_ids": dynamic_payload.get("available_recipe_ids", []),
        "available_tool_ids": dynamic_payload.get("available_tool_ids", []),
        "available_semantic_guard_ids": dynamic_payload.get("available_semantic_guard_ids", []),
        "circuit_context": dynamic_payload.get("circuit_context", {}),
        "dynamic_sensitive_fields": len(sensitive_paths),
        "benchmark_identifiers": benchmark_identifiers,
        "frozen_identifiers": frozen_identifiers,
        "historical_values": historical_values,
        "local_paths": local_paths,
        "payload_safe": bool(audit_result["dynamic_payload_safe"]),
        "prompt_sha256": audit_result["prompt_sha256"],
        "serialized_payload_sha256": hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest(),
    }


def execute_provider_smoke_probe(
    *,
    dry_run: bool,
    provider_boundary_probe: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    model_state = load_model_discovery_reuse_state()
    audit_input = build_provider_smoke_prompt_audit_input()
    _write_provider_smoke_contract_artifacts()
    prompt_audit = audit_prompt_payload(audit_input=audit_input)
    payload_analysis = _provider_smoke_payload_analysis(prompt_audit, audit_input)
    write_json(PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON, payload_analysis)
    run_id = _provider_smoke_run_id()
    execution_mode = "DRY_RUN" if dry_run else "LIVE"
    configured_model = str(model_state.get("configured_model", "") or "")
    artifact_dir = _write_provider_smoke_request_artifacts(
        audit_input=audit_input,
        run_id=run_id,
        execution_mode=execution_mode,
        model=configured_model,
    )

    provider_boundary_reached = False
    real_call_attempted = False
    real_call_completed = False
    transport_response_received = False
    content_received = False
    json_parsed = False
    smoke_terminal_success = False
    json_valid = None
    schema_valid = None
    http_status = None
    http_status_detail = ""
    provider_failure = ""
    provider_failure_code = ""
    provider_failure_stage = ""
    provider_exception_class = ""
    provider_exception_message_sanitized = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    latency_seconds = 0.0
    provider_status = "PROMPT_LEAKAGE_BLOCKED"
    terminal_status = "PROMPT_LEAKAGE_BLOCKED"
    semantic_valid: str | bool | None = "NOT_EXECUTED"
    response_content: str | None = None
    parsed_response: dict[str, Any] | None = None
    json_error: Exception | None = None
    schema_error_rows: list[dict[str, Any]] = []
    validation_model = "ProviderSmokeResponseV1"
    provider_response_metadata = {
        "run_id": run_id,
        "provider": "deepseek",
        "model": configured_model,
        "http_status": None,
        "http_status_observation": "NOT_EXECUTED",
        "request_id": None,
        "response_id": None,
        "created": None,
        "finish_reason": None,
        "attempts": [],
        "headers": {},
    }

    if prompt_audit["prompt_safe"]:
        provider_boundary_reached = True
        if provider_boundary_probe is not None:
            provider_boundary_probe(
                {
                    "stage": "provider_smoke",
                    "opaque_case_id": audit_input.opaque_case_id,
                    "trial_id": audit_input.trial_id,
                    "execution_mode": execution_mode,
                }
            )
        if dry_run:
            provider_status = "PROVIDER_BOUNDARY_REACHED_DRY_RUN"
            terminal_status = provider_status
        else:
            real_call_attempted = True
            try:
                provider_config = DeepSeekProviderConfig.from_env()
                provider_config.validate_model_selection(allow_empty=False)
                provider = DeepSeekProvider(provider_config)
                response = provider.generate(
                    LLMRequest(
                        system_prompt=audit_input.system_policy,
                        user_payload={
                            "retrieved_knowledge": audit_input.retrieved_knowledge,
                            "sanitized_dynamic_payload": audit_input.sanitized_dynamic_payload,
                            "output_schema_instruction": audit_input.output_schema_instruction,
                        },
                        response_format={"type": "json_object"},
                        model=provider_config.model,
                        temperature=provider_config.temperature,
                        max_tokens=provider_config.max_tokens,
                        timeout_seconds=provider_config.timeout_seconds,
                        metadata={"stage": "provider_smoke"},
                    )
                )
                latency_seconds = float(response.latency_seconds or 0.0)
                prompt_tokens = int(response.prompt_tokens or 0)
                completion_tokens = int(response.completion_tokens or 0)
                total_tokens = int(response.total_tokens or 0)
                transport_response_received = True
                response_content = response.content
                content_received = bool((response_content or "").strip())
                provider_response_metadata = {
                    "run_id": run_id,
                    "provider": "deepseek",
                    "model": response.model,
                    "http_status": response.raw_metadata.get("http_status"),
                    "http_status_observation": response.raw_metadata.get(
                        "http_status_observation",
                        "HTTP_STATUS_NOT_EXPOSED_BY_CURRENT_CLIENT_PATH",
                    ),
                    "request_id": response.raw_metadata.get("request_id"),
                    "response_id": response.raw_metadata.get("id"),
                    "created": response.raw_metadata.get("created"),
                    "finish_reason": response.finish_reason,
                    "attempts": response.raw_metadata.get("attempts", []),
                    "headers": response.raw_metadata.get("response_headers", {}),
                }
                http_status = response.raw_metadata.get("http_status")
                http_status_detail = str(
                    response.raw_metadata.get("http_status_observation", "HTTP_STATUS_NOT_EXPOSED_BY_CURRENT_CLIENT_PATH")
                )
                parsed_candidate = json.loads(response.content)
                json_parsed = True
                json_valid = isinstance(parsed_candidate, dict)
                parsed_response = parsed_candidate if isinstance(parsed_candidate, dict) else None
                if json_valid and parsed_response is not None:
                    ProviderSmokeResponseV1.model_validate(parsed_response)
                    schema_valid = True
                    semantic_valid = "NOT_EXECUTED"
                    real_call_completed = True
                    smoke_terminal_success = True
                    provider_status = "SUCCESS"
                    terminal_status = "PROVIDER_SMOKE_COMPLETED"
                    provider_failure = ""
                    provider_failure_code = ""
                    provider_failure_stage = ""
                elif json_valid is False:
                    schema_valid = None
                    provider_failure = "JSON_ERROR"
                    provider_failure_code = "JSON_ERROR"
                    provider_failure_stage = "JSON_PARSING"
                    provider_status = provider_failure_code
                    terminal_status = "PROVIDER_SMOKE_FAILED"
            except ValidationError as exc:
                schema_valid = False
                provider_failure = "SCHEMA_ERROR"
                provider_failure_code = "SCHEMA_ERROR"
                provider_failure_stage = "SCHEMA_VALIDATION"
                provider_exception_class = type(exc).__name__
                provider_exception_message_sanitized = _redact_sensitive_text(str(exc))
                schema_error_rows = _serialize_validation_errors(exc, run_id=run_id, validation_model=validation_model)
                provider_status = provider_failure_code
                terminal_status = "PROVIDER_SMOKE_FAILED"
            except json.JSONDecodeError as exc:
                json_valid = False
                json_error = exc
                provider_failure = "JSON_ERROR"
                provider_failure_code = "JSON_ERROR"
                provider_failure_stage = "JSON_PARSING"
                provider_exception_class = type(exc).__name__
                provider_exception_message_sanitized = _redact_sensitive_text(str(exc))
                provider_status = provider_failure_code
                terminal_status = "PROVIDER_SMOKE_FAILED"
            except Exception as exc:  # noqa: BLE001
                provider_failure = "TRANSPORT_ERROR"
                provider_failure_code = "TRANSPORT_ERROR"
                provider_failure_stage = "TRANSPORT"
                provider_exception_class = type(exc).__name__
                provider_exception_message_sanitized = _redact_sensitive_text(str(exc))
                provider_status = provider_failure_code
                terminal_status = "PROVIDER_SMOKE_FAILED"

    if provider_failure_code == "":
        provider_failure_code = provider_failure
    if not provider_exception_class and provider_failure_stage:
        provider_exception_class = provider_exception_class or ""
    go_provider_transport = (
        "NOT_EXECUTED"
        if not real_call_attempted
        else "PASS"
        if transport_response_received
        else "NO_GO"
    )
    go_provider_json = (
        "NOT_EXECUTED"
        if not transport_response_received
        else "PASS"
        if json_valid is True
        else "NO_GO"
    )
    go_provider_smoke_schema = (
        "NOT_EXECUTED"
        if json_valid is not True
        else "PASS"
        if schema_valid is True
        else "NO_GO"
    )
    go_provider_smoke = (
        "NOT_EXECUTED"
        if dry_run and prompt_audit["prompt_safe"]
        else "PASS"
        if schema_valid is True
        else "NO_GO"
    )
    row = {
        "stage": "provider_smoke",
        "run_id": run_id,
        "case_id": "provider_smoke",
        "opaque_case_id": audit_input.opaque_case_id,
        "trial_id": audit_input.trial_id,
        "provider": "deepseek",
        "provider_mode": "LIVE",
        "execution_mode": execution_mode,
        "model": configured_model,
        "prompt_sha256": prompt_audit["prompt_sha256"],
        "prompt_safe": prompt_audit["prompt_safe"],
        "provider_boundary_reached": provider_boundary_reached,
        "real_call_attempted": real_call_attempted,
        "real_call_completed": real_call_completed,
        "transport_response_received": transport_response_received,
        "content_received": content_received,
        "json_parsed": json_parsed,
        "semantic_valid": semantic_valid,
        "smoke_terminal_success": smoke_terminal_success,
        "json_valid": json_valid,
        "schema_valid": schema_valid,
        "http_status": http_status,
        "http_status_detail": http_status_detail,
        "provider_failure": provider_failure,
        "provider_failure_code": provider_failure_code,
        "provider_failure_stage": provider_failure_stage,
        "provider_exception_class": provider_exception_class,
        "provider_exception_message_sanitized": provider_exception_message_sanitized,
        "provider_transport_success": transport_response_received,
        "validation_model": validation_model,
        "validation_method": f"{validation_model}.model_validate",
        "pydantic_version": PYDANTIC_VERSION,
        "terminal_status": terminal_status,
        "chat_completion_calls_current_run": 0 if dry_run else int(real_call_attempted),
        "GO_PROVIDER_TRANSPORT": go_provider_transport,
        "GO_PROVIDER_JSON": go_provider_json,
        "GO_PROVIDER_SMOKE_SCHEMA": go_provider_smoke_schema,
        "go_stage": "PASS" if go_provider_smoke == "PASS" else "NOT_EXECUTED" if go_provider_smoke == "NOT_EXECUTED" else "NO_GO",
    }
    call_audit = {
        "stage": "provider_smoke",
        "run_id": run_id,
        "case_id": "provider_smoke",
        "opaque_case_id": audit_input.opaque_case_id,
        "trial_id": audit_input.trial_id,
        "provider_call_performed": real_call_attempted,
        "provider_boundary_reached": provider_boundary_reached,
        "provider_status": provider_status,
        "latency_seconds": latency_seconds,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "retries": 0,
        "cache_key": "",
        "prompt_sha256": prompt_audit["prompt_sha256"],
        "knowledge_bundle_sha256": "",
    }
    budget_row = {
        "stage": "provider_smoke",
        "run_id": run_id,
        "case_id": "provider_smoke",
        "trial_id": audit_input.trial_id,
        "latency_seconds": latency_seconds,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    result = {
        "stage": "provider_smoke",
        "timestamp": utc_now_iso(),
        "run_id": run_id,
        "execution_mode": execution_mode,
        "provider_smoke_prompt_safe": prompt_audit["prompt_safe"],
        "provider_boundary_reached": provider_boundary_reached,
        "real_call_attempted": real_call_attempted,
        "real_call_completed": real_call_completed,
        "transport_response_received": transport_response_received,
        "content_received": content_received,
        "json_parsed": json_parsed,
        "semantic_valid": semantic_valid,
        "smoke_terminal_success": smoke_terminal_success,
        "chat_completion_calls_current_run": 0 if dry_run else int(real_call_attempted),
        "http_status": http_status,
        "http_status_detail": http_status_detail,
        "json_valid": json_valid,
        "schema_valid": schema_valid,
        "provider_failure": provider_failure,
        "provider_failure_code": provider_failure_code,
        "provider_failure_stage": provider_failure_stage,
        "provider_exception_class": provider_exception_class,
        "provider_exception_message_sanitized": provider_exception_message_sanitized,
        "provider_transport_success": transport_response_received,
        "validation_model": validation_model,
        "validation_method": f"{validation_model}.model_validate",
        "pydantic_version": PYDANTIC_VERSION,
        "terminal_status": terminal_status,
        "payload_safe": payload_analysis["payload_safe"],
        "dynamic_sensitive_fields": payload_analysis["dynamic_sensitive_fields"],
        "benchmark_identifiers": payload_analysis["benchmark_identifiers"],
        "frozen_identifiers": payload_analysis["frozen_identifiers"],
        "historical_values": payload_analysis["historical_values"],
        "local_paths": payload_analysis["local_paths"],
        "GO_PROVIDER_TRANSPORT": go_provider_transport,
        "GO_PROVIDER_JSON": go_provider_json,
        "GO_PROVIDER_SMOKE_SCHEMA": go_provider_smoke_schema,
        "GO_PROVIDER_SMOKE": go_provider_smoke,
    }
    _write_provider_smoke_response_artifacts(
        artifact_dir=artifact_dir,
        response_content=response_content,
        parsed_response=parsed_response,
        json_valid=json_valid,
        json_error=json_error,
        schema_valid=schema_valid,
        validation_model=validation_model,
        schema_error_rows=schema_error_rows,
        provider_response_metadata=provider_response_metadata,
        live_call_record=call_audit,
        provider_smoke_result=result,
        run_id=run_id,
    )
    write_json(provider_smoke_run_results_dir(run_id) / "provider_smoke.json", result)
    return result, prompt_audit, call_audit, budget_row


def _artifact_dir_for_stage(stage: str, case: CampaignCase, trial_id: str) -> Path:
    if stage == "provider_smoke":
        return ARTIFACTS_DIR / "provider_smoke" / case.case_id / trial_id
    if stage in {"single_ac", "single_transient", "single_oscillator", "single_schmitt"}:
        mapping = {
            "single_ac": "ac_gain",
            "single_transient": "transient_delay",
            "single_oscillator": "oscillator",
            "single_schmitt": "schmitt",
        }
        return ARTIFACTS_DIR / "single_cases" / mapping[stage] / trial_id
    if stage == "use_case_smoke":
        return ARTIFACTS_DIR / "use_case_smoke" / case.case_id / trial_id
    if stage == "frozen_trial_1":
        return ARTIFACTS_DIR / "frozen_v3" / "trial_1" / case.case_id
    if stage == "frozen_trials_2_3":
        return ARTIFACTS_DIR / "frozen_v3" / trial_id / case.case_id
    return ARTIFACTS_DIR / stage / case.case_id / trial_id


def _cache_key(
    *,
    opaque_case_id: str,
    trial_id: str,
    model: str,
    prompt_sha256: str,
    knowledge_bundle_sha256: str,
) -> str:
    return json_sha256(
        {
            "opaque_case_id": opaque_case_id,
            "trial_id": trial_id,
            "model": model,
            "prompt_sha256": prompt_sha256,
            "knowledge_bundle_sha256": knowledge_bundle_sha256,
        }
    )


def execute_live_case(
    *,
    stage: str,
    case: CampaignCase,
    trial_id: str,
    max_repairs: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    provider_config = DeepSeekProviderConfig.from_env()
    provider_config.validate_model_selection(
        allow_empty=False,
        allow_legacy_alias=os.getenv("ALLOW_LEGACY_DEEPSEEK_ALIAS", "").strip() == "1",
    )
    provider = DeepSeekProvider(provider_config)
    original_spec = Specification.from_yaml(case.specification_file)
    original_spec.case_id = case.case_id
    original_spec.parent_circuit_id = case.parent_circuit_id
    if case.targeted_metric and case.targeted_metric in original_spec.performance_targets:
        original_spec.performance_targets = {
            case.targeted_metric: original_spec.performance_targets[case.targeted_metric]
        }
    opaque_case_id = build_opaque_case_id(case.case_id)
    sanitized_spec = sanitized_specification(original_spec, opaque_case_id)
    bundle = retrieve_knowledge_bundle(
        knowledge_root=KNOWLEDGE_ROOT,
        case_id=opaque_case_id,
        circuit_family=case.circuit_family or sanitized_spec.circuit_type.value,
        requested_metrics=list(sanitized_spec.performance_targets.keys()),
        knowledge_version=KNOWLEDGE_VERSION,
    )
    knowledge_payload = bundle.to_prompt_payload()
    service = LLMGenerationService(provider, prompt_path=PROMPT_PATH)
    _, system_prompt, request_payload, prompt_sha = service.build_request_context(
        specification=sanitized_spec,
        netlist_path=case.netlist_file,
        deterministic_testbench=None,
        include_deterministic_summary=False,
        knowledge_bundle=knowledge_payload,
        knowledge_version=KNOWLEDGE_VERSION,
        provider_mode="LIVE",
        scientific_llm_evidence=False,
        request_overrides={
            "opaque_case_id": opaque_case_id,
            "prompt_version": PROMPT_VERSION,
            "schema_version": RESPONSE_SCHEMA_VERSION,
        },
    )
    prompt_audit = audit_prompt_payload(
        stage=stage,
        internal_case_id=case.case_id,
        opaque_case_id=opaque_case_id,
        trial_id=trial_id,
        system_prompt=system_prompt,
        request_payload=request_payload,
    )
    if not prompt_audit["prompt_safe"]:
        row = {
            "stage": stage,
            "run_id": current_run_id(),
            "case_id": case.case_id,
            "opaque_case_id": opaque_case_id,
            "trial_id": trial_id,
            "use_case": infer_use_case(case.targeted_metric),
            "circuit_family": case.circuit_family,
            "ground_truth_label": case.ground_truth_label,
            "provider": "deepseek",
            "provider_mode": "LIVE",
            "scientific_llm_evidence": False,
            "model": provider_config.model,
            "prompt_version": PROMPT_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
            "knowledge_bundle_sha256": bundle.bundle_sha256,
            "prompt_sha256": prompt_audit["prompt_sha256"],
            "prompt_safe": False,
            "initial_json_valid": False,
            "final_plan_valid": False,
            "repair_count": 0,
            "execution_status": "PROMPT_LEAKAGE_BLOCKED",
            "simulation_mode": "",
            "measurement_backend": "",
            "requested_metric_count": len(sanitized_spec.performance_targets),
            "evaluated_metric_count": 0,
            "metric_coverage": 0.0,
            "compliance_status": "NOT_EVALUATED",
            "scientific_category": "UNEVALUATED",
            "evaluation_outcome": "UNEVALUATED",
            "generation_latency_s": 0.0,
            "simulation_latency_s": 0.0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "netlist_sha256": sha256_file(case.netlist_file),
            "specification_sha256": json_sha256(sanitized_spec.to_dict()),
            "testbench_sha256": "",
            "cache_key": _cache_key(
                opaque_case_id=opaque_case_id,
                trial_id=trial_id,
                model=provider_config.model,
                prompt_sha256=prompt_sha,
                knowledge_bundle_sha256=bundle.bundle_sha256,
            ),
            "cache_hit": False,
            "artifact_dir": "",
            "go_stage": "NO_GO",
        }
        call_audit = {
            "stage": stage,
            "run_id": current_run_id(),
            "case_id": case.case_id,
            "opaque_case_id": opaque_case_id,
            "trial_id": trial_id,
            "provider_call_performed": False,
            "provider_status": "PROMPT_LEAKAGE_BLOCKED",
            "latency_seconds": 0.0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "retries": 0,
            "cache_key": row["cache_key"],
            "prompt_sha256": prompt_sha,
            "knowledge_bundle_sha256": bundle.bundle_sha256,
        }
        budget_row = {
            "stage": stage,
            "run_id": current_run_id(),
            "case_id": case.case_id,
            "trial_id": trial_id,
            "latency_seconds": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        return row, prompt_audit, call_audit, budget_row

    artifact_dir = _artifact_dir_for_stage(stage, case, trial_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    outcome = None
    compiled = None
    report = None
    simulation_results = None
    provider_error = None
    try:
        outcome = service.generate_plan(
            specification=sanitized_spec,
            netlist_path=case.netlist_file,
            deterministic_testbench=None,
            model=provider_config.model,
            temperature=provider_config.temperature,
            max_tokens=provider_config.max_tokens,
            timeout_seconds=provider_config.timeout_seconds,
            include_deterministic_summary=False,
            max_repairs=max_repairs,
            knowledge_bundle=knowledge_payload,
            knowledge_version=KNOWLEDGE_VERSION,
            provider_mode="LIVE",
            scientific_llm_evidence=False,
            request_overrides={
                "opaque_case_id": opaque_case_id,
                "prompt_version": PROMPT_VERSION,
                "schema_version": RESPONSE_SCHEMA_VERSION,
            },
        )
        if outcome.parsed_plan is not None:
            compiled = TestbenchPlanCompiler().compile(outcome.parsed_plan, specification=sanitized_spec)
            pipeline = VerificationPipeline(
                use_llm=False,
                allow_mock=False,
                timeout_seconds=int(provider_config.timeout_seconds),
            )
            pipeline.testbench_gen.generate = lambda specification, netlist_path=None: compiled.testbench
            simulation_results = pipeline._run_simulation_with_ngspice(case.netlist_file, compiled.testbench)
            report = pipeline.verify(
                sanitized_spec,
                netlist_path=case.netlist_file,
                simulation_results=simulation_results,
                spec_path=case.specification_file,
            )
    except Exception as exc:  # noqa: BLE001
        provider_error = exc

    if outcome is not None:
        write_json(artifact_dir / "request_payload.json", outcome.request_payload)
        (artifact_dir / "system_prompt.txt").write_text(outcome.system_prompt, encoding="utf-8")
        (artifact_dir / "raw_response.txt").write_text(outcome.raw_response, encoding="utf-8")
        (artifact_dir / "prompt_sha256.txt").write_text(outcome.prompt_sha256, encoding="utf-8")
        write_json(artifact_dir / "plan_validation.json", outcome.validation.to_dict())
        write_json(artifact_dir / "provider_metadata.json", outcome.provider_metadata)
        write_json(
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
        if outcome.parsed_plan is not None:
            write_json(artifact_dir / "parsed_plan.json", outcome.parsed_plan.model_dump(mode="json"))
    write_json(
        artifact_dir / "local_provenance.json",
        {
            "internal_case_id": case.case_id,
            "opaque_case_id": opaque_case_id,
            "campaign_name": CAMPAIGN_NAME,
            "prompt_version": PROMPT_VERSION,
            "knowledge_version": KNOWLEDGE_VERSION,
        },
    )
    if compiled is not None:
        deck = TestbenchPlanCompiler().compile_to_spice_deck(
            outcome.parsed_plan,
            specification=sanitized_spec,
            netlist_path=case.netlist_file,
        )
        (artifact_dir / "compiled_testbench.cir").write_text(deck, encoding="utf-8")
        (artifact_dir / "testbench_sha256.txt").write_text(hashlib.sha256(deck.encode("utf-8")).hexdigest(), encoding="utf-8")
    if simulation_results:
        write_json(artifact_dir / "metrics.json", simulation_results.get("metrics", {}))
        write_json(artifact_dir / "ngspice_command.json", simulation_results.get("ngspice_command", []))
        (artifact_dir / "ngspice_stdout.txt").write_text("\n".join(simulation_results.get("logs", [])), encoding="utf-8")
        (artifact_dir / "ngspice_stderr.txt").write_text("\n".join(simulation_results.get("errors", [])), encoding="utf-8")

    metadata = outcome.provider_metadata if outcome is not None else {}
    prompt_tokens = metadata.get("prompt_tokens")
    completion_tokens = metadata.get("completion_tokens")
    total_tokens = metadata.get("total_tokens")
    compliance_status = report.compliance_status.value if report is not None else "NOT_EVALUATED"
    execution_status = (
        report.execution_status.value
        if report is not None
        else type(provider_error).__name__ if provider_error is not None
        else "NOT_EXECUTED"
    )
    simulation_mode = report.simulation_mode.value if report is not None and report.simulation_mode else ""
    measurement_backend = report.measurement_backend or "" if report is not None else ""
    scientific_category = report.scientific_category.value if report is not None else "UNEVALUATED"
    evaluated_metric_count = (
        sum(1 for result in report.spec_results if result.measured_value is not None)
        if report is not None
        else 0
    )
    requested_metric_count = len(sanitized_spec.performance_targets)
    cache_key = _cache_key(
        opaque_case_id=opaque_case_id,
        trial_id=trial_id,
        model=provider_config.model,
        prompt_sha256=prompt_sha,
        knowledge_bundle_sha256=bundle.bundle_sha256,
    )
    row = {
        "stage": stage,
        "run_id": current_run_id(),
        "case_id": case.case_id,
        "opaque_case_id": opaque_case_id,
        "trial_id": trial_id,
        "use_case": infer_use_case(case.targeted_metric),
        "circuit_family": case.circuit_family,
        "ground_truth_label": case.ground_truth_label,
        "provider": "deepseek",
        "provider_mode": "LIVE",
        "scientific_llm_evidence": False,
        "model": provider_config.model,
        "prompt_version": PROMPT_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "knowledge_bundle_sha256": bundle.bundle_sha256,
        "prompt_sha256": prompt_audit["prompt_sha256"],
        "prompt_safe": True,
        "initial_json_valid": bool(outcome and outcome.validation.status.value != "INVALID_JSON"),
        "final_plan_valid": bool(outcome and outcome.validation.is_valid),
        "repair_count": len(outcome.repair_history) if outcome else 0,
        "execution_status": execution_status,
        "simulation_mode": simulation_mode,
        "measurement_backend": measurement_backend,
        "requested_metric_count": requested_metric_count,
        "evaluated_metric_count": evaluated_metric_count,
        "metric_coverage": (evaluated_metric_count / requested_metric_count) if requested_metric_count else 0.0,
        "compliance_status": compliance_status,
        "scientific_category": scientific_category,
        "evaluation_outcome": classification_from_ground_truth(case.ground_truth_label, compliance_status),
        "generation_latency_s": float(metadata.get("latency_seconds", 0.0) or 0.0),
        "simulation_latency_s": report.runtime_seconds if report is not None else 0.0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "netlist_sha256": sha256_file(case.netlist_file),
        "specification_sha256": json_sha256(sanitized_spec.to_dict()),
        "testbench_sha256": (
            (artifact_dir / "testbench_sha256.txt").read_text(encoding="utf-8").strip()
            if (artifact_dir / "testbench_sha256.txt").exists()
            else ""
        ),
        "cache_key": cache_key,
        "cache_hit": False,
        "artifact_dir": _safe_relative(artifact_dir),
        "go_stage": "PASS" if report is not None and execution_status == "SUCCESS" else "NO_GO",
    }
    attempts = list(metadata.get("attempts", [])) if isinstance(metadata, dict) else []
    call_audit = {
        "stage": stage,
        "run_id": current_run_id(),
        "case_id": case.case_id,
        "opaque_case_id": opaque_case_id,
        "trial_id": trial_id,
        "provider_call_performed": outcome is not None,
        "provider_status": execution_status,
        "latency_seconds": row["generation_latency_s"],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "retries": sum(1 for attempt in attempts if attempt.get("final_status") == "RETRY"),
        "cache_key": cache_key,
        "prompt_sha256": prompt_audit["prompt_sha256"],
        "knowledge_bundle_sha256": bundle.bundle_sha256,
    }
    budget_row = {
        "stage": stage,
        "run_id": current_run_id(),
        "case_id": case.case_id,
        "trial_id": trial_id,
        "latency_seconds": row["generation_latency_s"],
        "prompt_tokens": prompt_tokens or 0,
        "completion_tokens": completion_tokens or 0,
        "total_tokens": total_tokens or 0,
    }
    if provider_error is not None:
        write_json(
            artifact_dir / "provider_error.json",
            {
                "error_type": type(provider_error).__name__,
                "message": str(provider_error),
                "is_provider_error": isinstance(provider_error, LLMProviderError),
            },
        )
    return row, prompt_audit, call_audit, budget_row


def blocked_stage_result(
    *,
    stage: str,
    output_json: Path,
    output_md: Path,
    go_field: str,
    reason: str,
) -> dict[str, Any]:
    result = {
        "stage": stage,
        "timestamp": utc_now_iso(),
        go_field: "NOT_EXECUTED" if reason != "READY" else "NO_GO",
        "status": reason,
    }
    write_json(output_json, result)
    write_markdown(
        output_md,
        [
            f"# {stage.replace('_', ' ').title()}",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- Status: {reason}",
            f"- {go_field}: {result[go_field]}",
        ],
    )
    return result


def run_case_batch(
    *,
    stage: str,
    cases: list[CampaignCase],
    trials: int,
    output_csv: Path,
    output_json: Path,
    output_md: Path,
    go_field: str,
    require_full_campaign: bool,
    max_repairs: int,
) -> dict[str, Any]:
    context = load_stage_context()
    model_discovery = context.get("model_discovery") or {}
    guard = live_guard_state(require_full_campaign=require_full_campaign)
    if context["pre_live_manifest"]["go_code_freeze"] != "PASS":
        return blocked_stage_result(
            stage=stage,
            output_json=output_json,
            output_md=output_md,
            go_field=go_field,
            reason="BLOCKED_BY_CODE_FREEZE",
        )
    if context["secret_audit"]["go_secret_safety"] != "PASS":
        return blocked_stage_result(
            stage=stage,
            output_json=output_json,
            output_md=output_md,
            go_field=go_field,
            reason="BLOCKED_BY_SECRET_AUDIT",
        )
    if model_discovery.get("go_model_discovery") != "PASS":
        return blocked_stage_result(
            stage=stage,
            output_json=output_json,
            output_md=output_md,
            go_field=go_field,
            reason="BLOCKED_BY_MODEL_DISCOVERY",
        )
    if guard["status"] != "READY":
        return blocked_stage_result(
            stage=stage,
            output_json=output_json,
            output_md=output_md,
            go_field=go_field,
            reason=guard["status"],
        )

    rows: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    call_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    for case in cases:
        for trial_index in range(1, trials + 1):
            if stage == "frozen_trials_2_3":
                trial_id = f"trial_{trial_index}"
            elif stage == "frozen_trial_1":
                trial_id = "trial_1"
            else:
                trial_id = f"trial_{trial_index:02d}"
            row, prompt_row, call_row, budget_row = execute_live_case(
                stage=stage,
                case=case,
                trial_id=trial_id,
                max_repairs=max_repairs,
            )
            rows.append(row)
            prompt_rows.append(prompt_row)
            call_rows.append(call_row)
            budget_rows.append(budget_row)

    write_csv(output_csv, rows)
    append_csv_rows(PROMPT_AUDIT_CSV, prompt_rows)
    append_csv_rows(LIVE_CALL_AUDIT_CSV, call_rows)
    append_csv_rows(LIVE_BUDGET_CSV, budget_rows)
    go_stage = "PASS" if rows and all(row["go_stage"] == "PASS" for row in rows) else "NO_GO"
    result = {
        "stage": stage,
        "timestamp": utc_now_iso(),
        "cases_expected": len(cases),
        "trials_expected": len(cases) * trials,
        "rows_recorded": len(rows),
        "provider_calls": sum(1 for row in call_rows if row["provider_call_performed"]),
        "valid_plans": sum(1 for row in rows if row["final_plan_valid"]),
        "compiled_and_executed": sum(1 for row in rows if row["execution_status"] == "SUCCESS"),
        go_field: go_stage,
    }
    write_json(output_json, result)
    write_markdown(
        output_md,
        [
            f"# {stage.replace('_', ' ').title()}",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- Cases expected: {result['cases_expected']}",
            f"- Trials expected: {result['trials_expected']}",
            f"- Rows recorded: {result['rows_recorded']}",
            f"- Provider calls: {result['provider_calls']}",
            f"- Valid plans: {result['valid_plans']}",
            f"- Compiled and executed: {result['compiled_and_executed']}",
            f"- {go_field}: {result[go_field]}",
        ],
    )
    return result


def run_provider_smoke() -> dict[str, Any]:
    dry_run = current_execution_mode() == "DRY_RUN"
    context = load_stage_context()
    model_state = load_model_discovery_reuse_state()
    if context["secret_audit"]["go_secret_safety"] != "PASS":
        return blocked_stage_result(
            stage="provider_smoke",
            output_json=RESULTS_DIR / "provider_smoke.json",
            output_md=REPORTS_DIR / "provider_smoke.md",
            go_field="GO_PROVIDER_SMOKE",
            reason="BLOCKED_BY_SECRET_AUDIT",
        )
    if model_state["GO_MODEL_DISCOVERY"] != "PASS":
        return blocked_stage_result(
            stage="provider_smoke",
            output_json=RESULTS_DIR / "provider_smoke.json",
            output_md=REPORTS_DIR / "provider_smoke.md",
            go_field="GO_PROVIDER_SMOKE",
            reason="BLOCKED_BY_MODEL_DISCOVERY",
        )
    if not dry_run and context["pre_live_manifest"]["go_code_freeze"] != "PASS":
        return blocked_stage_result(
            stage="provider_smoke",
            output_json=RESULTS_DIR / "provider_smoke.json",
            output_md=REPORTS_DIR / "provider_smoke.md",
            go_field="GO_PROVIDER_SMOKE",
            reason="BLOCKED_BY_CODE_FREEZE",
        )
    if not dry_run and live_guard_state(require_full_campaign=False)["status"] != "READY":
        return blocked_stage_result(
            stage="provider_smoke",
            output_json=RESULTS_DIR / "provider_smoke.json",
            output_md=REPORTS_DIR / "provider_smoke.md",
            go_field="GO_PROVIDER_SMOKE",
            reason=live_guard_state(require_full_campaign=False)["status"],
        )
    result, prompt_audit, call_audit, budget_row = execute_provider_smoke_probe(dry_run=dry_run)
    write_csv(RESULTS_DIR / "provider_smoke_calls.csv", [result])
    write_json(RESULTS_DIR / "provider_smoke.json", result)
    append_csv_rows(PROMPT_AUDIT_CSV, [prompt_audit])
    append_csv_rows(LIVE_CALL_AUDIT_CSV, [call_audit])
    append_csv_rows(LIVE_BUDGET_CSV, [budget_row])
    _write_current_run_ledgers(result.get("run_id", ""))
    write_markdown(
        REPORTS_DIR / "provider_smoke.md",
        [
            "# DeepSeek Provider Smoke",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- Execution mode: {result['execution_mode']}",
            f"- Prompt safe: {str(result['provider_smoke_prompt_safe']).lower()}",
            f"- Provider boundary reached: {str(result['provider_boundary_reached']).lower()}",
            f"- Real call attempted: {str(result['real_call_attempted']).lower()}",
            f"- Transport response received: {str(result['transport_response_received']).lower()}",
            f"- JSON valid: {result['json_valid'] if result['json_valid'] is not None else 'NOT_EXECUTED'}",
            f"- Schema valid: {result['schema_valid'] if result['schema_valid'] is not None else 'NOT_EXECUTED'}",
            f"- GO_PROVIDER_TRANSPORT: {result['GO_PROVIDER_TRANSPORT']}",
            f"- GO_PROVIDER_JSON: {result['GO_PROVIDER_JSON']}",
            f"- GO_PROVIDER_SMOKE_SCHEMA: {result['GO_PROVIDER_SMOKE_SCHEMA']}",
            f"- Chat completion calls current run: {result['chat_completion_calls_current_run']}",
            f"- GO_PROVIDER_SMOKE: {result['GO_PROVIDER_SMOKE']}",
        ],
    )
    return result


def run_single_case(stage: str) -> dict[str, Any]:
    single_case = default_single_cases()[stage]
    output_name = {
        "single_ac": "single_ac_gain",
        "single_transient": "single_transient",
        "single_oscillator": "single_oscillator",
        "single_schmitt": "single_schmitt",
    }[stage]
    go_field = {
        "single_ac": "GO_LIVE_AC_GAIN",
        "single_transient": "GO_LIVE_TRANSIENT",
        "single_oscillator": "GO_LIVE_OSCILLATOR",
        "single_schmitt": "GO_LIVE_SCHMITT",
    }[stage]
    return run_case_batch(
        stage=stage,
        cases=[single_case],
        trials=1,
        output_csv=RESULTS_DIR / f"{output_name}.csv",
        output_json=RESULTS_DIR / f"{output_name}.json",
        output_md=REPORTS_DIR / f"{output_name}.md",
        go_field=go_field,
        require_full_campaign=True,
        max_repairs=int(os.getenv("DEEPSEEK_MAX_REPAIRS_SINGLE_CASE", "2")),
    )


def run_single_cases() -> dict[str, Any]:
    results = [
        run_single_case("single_ac"),
        run_single_case("single_transient"),
        run_single_case("single_oscillator"),
        run_single_case("single_schmitt"),
    ]
    go_single_cases = "PASS" if all(result.get(next(key for key in result if key.startswith("GO_")), "NO_GO") == "PASS" for result in results) else "NO_GO"
    payload = {
        "timestamp": utc_now_iso(),
        "GO_LIVE_SINGLE_CASES": go_single_cases,
    }
    write_json(RESULTS_DIR / "single_cases_summary.json", payload)
    return payload


def run_use_case_smoke() -> dict[str, Any]:
    return run_case_batch(
        stage="use_case_smoke",
        cases=default_use_case_cases(),
        trials=1,
        output_csv=RESULTS_DIR / "live_use_case_smoke.csv",
        output_json=RESULTS_DIR / "live_use_case_smoke_summary.json",
        output_md=REPORTS_DIR / "live_use_case_smoke.md",
        go_field="GO_LIVE_USE_CASE_SMOKE",
        require_full_campaign=True,
        max_repairs=int(os.getenv("DEEPSEEK_MAX_REPAIRS_SINGLE_CASE", "2")),
    )


def freeze_frozen_protocol() -> dict[str, Any]:
    context = load_stage_context()
    model_discovery = context.get("model_discovery") or {}
    result = {
        "timestamp": utc_now_iso(),
        "protocol_version": CAMPAIGN_NAME,
        "frozen_commit": context["pre_live_manifest"]["git_commit"],
        "frozen_model": model_discovery.get("configured_model", ""),
        "frozen_prompt": PROMPT_VERSION,
        "frozen_knowledge": KNOWLEDGE_VERSION,
        "frozen_compiler": COMPILER_VERSION,
        "frozen_checker": CHECKER_VERSION,
        "worktree_remained_clean": context["pre_live_manifest"]["worktree_clean"],
        "protocol_changes_after_freeze": not context["pre_live_manifest"]["worktree_clean"],
        "GO_FROZEN_PROTOCOL_FREEZE": "PASS" if context["pre_live_manifest"]["go_code_freeze"] == "PASS" and model_discovery.get("go_model_discovery") == "PASS" else "NO_GO",
    }
    write_json(RESULTS_DIR / "frozen_protocol_manifest.json", result)
    write_markdown(
        REPORTS_DIR / "frozen_protocol_manifest.md",
        [
            "# Frozen Protocol Manifest",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- Frozen commit: {result['frozen_commit']}",
            f"- Frozen model: {result['frozen_model'] or '<unset>'}",
            f"- Frozen prompt: {result['frozen_prompt']}",
            f"- Frozen knowledge: {result['frozen_knowledge']}",
            f"- Worktree remained clean: {str(result['worktree_remained_clean']).lower()}",
            f"- Protocol changes after freeze: {str(result['protocol_changes_after_freeze']).lower()}",
            f"- GO_FROZEN_PROTOCOL_FREEZE: {result['GO_FROZEN_PROTOCOL_FREEZE']}",
        ],
    )
    return result


def _stability_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["case_id"], []).append(row)
    summaries: list[dict[str, Any]] = []
    for case_id, items in grouped.items():
        latencies = [float(item.get("generation_latency_s") or 0.0) for item in items]
        summaries.append(
            {
                "case_id": case_id,
                "trial_count": len(items),
                "verdict_stability": len({item.get("evaluation_outcome", "") for item in items}) == 1,
                "analysis_agreement": len({item.get("use_case", "") for item in items}) == 1,
                "backend_agreement": len({item.get("measurement_backend", "") for item in items}) == 1,
                "mean_latency_s": statistics.mean(latencies) if latencies else 0.0,
                "p95_latency_s": max(latencies) if latencies else 0.0,
            }
        )
    return summaries


def audit_deepseek_live_cache() -> list[dict[str, Any]]:
    rows = read_csv(RESULTS_DIR / "frozen_three_trials.csv")
    cache_rows: list[dict[str, Any]] = []
    grouped: dict[str, set[str]] = {}
    for row in rows:
        grouped.setdefault(row["case_id"], set()).add(row.get("cache_key", ""))
    for row in rows:
        trial_count = sum(1 for item in rows if item["case_id"] == row["case_id"])
        unique_keys = grouped.get(row["case_id"], set())
        cache_rows.append(
            {
                "case_id": row["case_id"],
                "trial_id": row["trial_id"],
                "cache_key": row.get("cache_key", ""),
                "cache_hit": row.get("cache_hit", False),
                "expected_cache_hits": 0,
                "cache_contamination": len(unique_keys) != trial_count,
            }
        )
    write_csv(RESULTS_DIR / "frozen_cache_audit.csv", cache_rows, fieldnames=["case_id", "trial_id", "cache_key", "cache_hit", "expected_cache_hits", "cache_contamination"])
    write_markdown(
        REPORTS_DIR / "frozen_cache_audit.md",
        [
            "# Frozen Cache Audit",
            "",
            f"- Rows audited: {len(cache_rows)}",
            f"- Cache contamination cases: {sum(1 for row in cache_rows if row['cache_contamination'])}",
        ],
    )
    return cache_rows


def audit_deepseek_prompt_leakage() -> dict[str, Any]:
    rows = read_csv(PROMPT_AUDIT_CSV)
    summary = {
        "rows": len(rows),
        "unsafe_prompts": sum(1 for row in rows if str(row.get("prompt_safe", "")).lower() == "false"),
        "ground_truth_exposures": sum(1 for row in rows if str(row.get("ground_truth_found", "")).lower() == "true"),
        "historical_verdict_exposures": sum(1 for row in rows if str(row.get("historical_verdict_found", "")).lower() == "true"),
        "mutation_exposures": sum(1 for row in rows if str(row.get("mutation_id_found", "")).lower() == "true"),
        "local_path_exposures": sum(1 for row in rows if str(row.get("local_path_found", "")).lower() == "true"),
    }
    write_markdown(
        REPORTS_DIR / "prompt_leakage_audit.md",
        [
            "# Prompt Leakage Audit",
            "",
            f"- Rows: {summary['rows']}",
            f"- Unsafe prompts: {summary['unsafe_prompts']}",
            f"- Ground-truth exposures: {summary['ground_truth_exposures']}",
            f"- Historical verdict exposures: {summary['historical_verdict_exposures']}",
            f"- Mutation exposures: {summary['mutation_exposures']}",
            f"- Local path exposures: {summary['local_path_exposures']}",
        ],
    )
    return summary


def run_frozen_trial_one() -> dict[str, Any]:
    return run_case_batch(
        stage="frozen_trial_1",
        cases=default_frozen_cases(),
        trials=1,
        output_csv=RESULTS_DIR / "frozen_trial_1.csv",
        output_json=RESULTS_DIR / "frozen_trial_1_summary.json",
        output_md=REPORTS_DIR / "frozen_trial_1.md",
        go_field="GO_LIVE_FROZEN_TRIAL_1",
        require_full_campaign=True,
        max_repairs=int(os.getenv("DEEPSEEK_MAX_REPAIRS_CAMPAIGN", "1")),
    )


def run_frozen_three_trials() -> dict[str, Any]:
    result = run_case_batch(
        stage="frozen_trials_2_3",
        cases=default_frozen_cases(),
        trials=3,
        output_csv=RESULTS_DIR / "frozen_three_trials.csv",
        output_json=RESULTS_DIR / "frozen_three_trials_summary.json",
        output_md=REPORTS_DIR / "frozen_three_trials.md",
        go_field="GO_LIVE_FROZEN_THREE_TRIALS",
        require_full_campaign=True,
        max_repairs=int(os.getenv("DEEPSEEK_MAX_REPAIRS_CAMPAIGN", "1")),
    )
    rows = read_csv(RESULTS_DIR / "frozen_three_trials.csv")
    stability_rows = _stability_rows(rows)
    write_csv(RESULTS_DIR / "frozen_trial_stability.csv", stability_rows)
    write_markdown(
        REPORTS_DIR / "frozen_trial_stability.md",
        [
            "# Frozen Trial Stability",
            "",
            f"- Cases summarized: {len(stability_rows)}",
        ],
    )
    plan_delta_rows = [
        {
            "case_id": row["case_id"],
            "trial_id": row["trial_id"],
            "prompt_sha256": row.get("prompt_sha256", ""),
            "knowledge_bundle_sha256": row.get("knowledge_bundle_sha256", ""),
            "measurement_backend": row.get("measurement_backend", ""),
            "evaluation_outcome": row.get("evaluation_outcome", ""),
        }
        for row in rows
    ]
    write_csv(RESULTS_DIR / "frozen_plan_deltas.csv", plan_delta_rows)
    audit_deepseek_live_cache()
    return result


def run_post_live_deterministic_parity() -> dict[str, Any]:
    result = {
        "timestamp": utc_now_iso(),
        "GO_POST_LIVE_DETERMINISTIC_PARITY": "NOT_EXECUTED",
        "status": "NOT_IMPLEMENTED_AUTOMATICALLY",
    }
    write_json(RESULTS_DIR / "post_live_deterministic_parity.csv", [result])
    write_markdown(
        REPORTS_DIR / "post_live_deterministic_parity.md",
        [
            "# Post-Live Deterministic Parity",
            "",
            f"- Timestamp: {result['timestamp']}",
            f"- Status: {result['status']}",
            f"- GO_POST_LIVE_DETERMINISTIC_PARITY: {result['GO_POST_LIVE_DETERMINISTIC_PARITY']}",
        ],
    )
    return result


def compare_deterministic_stub_deepseek() -> dict[str, Any]:
    deterministic_rows = read_csv(DETERMINISTIC_REFERENCE_CSV)
    stub_rows = read_csv(STUB_REFERENCE_CSV)
    deepseek_rows = read_csv(RESULTS_DIR / "frozen_three_trials.csv")

    def _count(rows: list[dict[str, str]], key: str, value: str) -> int:
        return sum(1 for row in rows if row.get(key) == value)

    comparison = {
        "Deterministic TRUE_ACCEPT": _count(deterministic_rows, "evaluation_outcome", "TRUE_ACCEPT"),
        "Deterministic TRUE_DETECTION": _count(deterministic_rows, "evaluation_outcome", "TRUE_DETECTION"),
        "Deterministic FALSE_ACCEPT": _count(deterministic_rows, "evaluation_outcome", "FALSE_ACCEPT"),
        "Deterministic FALSE_REJECT": _count(deterministic_rows, "evaluation_outcome", "FALSE_REJECT"),
        "Stub TRUE_ACCEPT": _count(stub_rows, "evaluation_outcome", "TRUE_ACCEPT"),
        "Stub TRUE_DETECTION": _count(stub_rows, "evaluation_outcome", "TRUE_DETECTION"),
        "Stub FALSE_ACCEPT": _count(stub_rows, "evaluation_outcome", "FALSE_ACCEPT"),
        "Stub FALSE_REJECT": _count(stub_rows, "evaluation_outcome", "FALSE_REJECT"),
        "DeepSeek TRUE_ACCEPT": _count(deepseek_rows, "evaluation_outcome", "TRUE_ACCEPT"),
        "DeepSeek TRUE_DETECTION": _count(deepseek_rows, "evaluation_outcome", "TRUE_DETECTION"),
        "DeepSeek FALSE_ACCEPT": _count(deepseek_rows, "evaluation_outcome", "FALSE_ACCEPT"),
        "DeepSeek FALSE_REJECT": _count(deepseek_rows, "evaluation_outcome", "FALSE_REJECT"),
        "DeepSeek UNEVALUATED": _count(deepseek_rows, "evaluation_outcome", "UNEVALUATED"),
    }
    rows = [{"metric": key, "value": value} for key, value in comparison.items()]
    write_csv(RESULTS_DIR / "deterministic_vs_stub_vs_deepseek.csv", rows)
    write_markdown(
        REPORTS_DIR / "deterministic_vs_stub_vs_deepseek.md",
        [
            "# Deterministic vs Stub vs DeepSeek",
            "",
            *(f"- {key}: {value}" for key, value in comparison.items()),
        ],
    )
    return comparison


def _csv_truthy(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def build_provider_smoke_blocker_analysis() -> dict[str, Any]:
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    triggering_line = next(
        (line.strip() for line in prompt_text.splitlines() if "compliance verdict or expected outcome" in line),
        "- return a compliance verdict or expected outcome;",
    )
    call_rows = read_csv(LIVE_CALL_AUDIT_CSV)
    provider_called = any(
        row.get("stage") == "provider_smoke" and _csv_truthy(row.get("provider_call_performed"))
        for row in call_rows
    )
    analysis = {
        "root_cause": "Naive monolithic full-prompt substring scanning treated generic security-policy wording as leaked historical verdict data.",
        "triggering_line": triggering_line,
        "triggering_pattern": "generic verdict/outcome wording inside the system policy scanned without zone awareness",
        "matched_section": "system_policy",
        "actual_sensitive_value_present": False,
        "negative_security_instruction": True,
        "false_positive": True,
        "provider_called": provider_called,
        "chat_completion_called": provider_called,
        "recommended_code_changes": [
            "split_prompt_into_zones",
            "audit_dynamic_payload_recursively",
            "treat_negative_policy_instructions_as_safe",
            "reuse_model_discovery_artifact_in_dry_run",
            "stop_provider_smoke_at_boundary_in_dry_run",
            "use_stage_specific_reporting_templates",
        ],
    }
    write_json(PROVIDER_SMOKE_BLOCKER_ANALYSIS_JSON, analysis)
    write_markdown(
        PROVIDER_SMOKE_BLOCKER_ANALYSIS_MD,
        [
            "# Provider Smoke Blocker Analysis",
            "",
            f"- Root cause: {analysis['root_cause']}",
            f"- Triggering line: {analysis['triggering_line']}",
            f"- Triggering pattern: {analysis['triggering_pattern']}",
            f"- Matched section: {analysis['matched_section']}",
            f"- Actual sensitive value present: {str(analysis['actual_sensitive_value_present']).lower()}",
            f"- Negative security instruction: {str(analysis['negative_security_instruction']).lower()}",
            f"- False positive: {str(analysis['false_positive']).lower()}",
            f"- Provider called: {str(analysis['provider_called']).lower()}",
            f"- Chat completion called: {str(analysis['chat_completion_called']).lower()}",
            "",
            "## Recommended Code Changes",
            *(f"- {item}" for item in analysis["recommended_code_changes"]),
        ],
    )
    return analysis


def _comparison_for_stage(requested_stage: str) -> dict[str, Any]:
    if requested_stage in {"frozen_trial_1", "frozen_trials_2_3", "post_live_deterministic", "final_summary"}:
        return compare_deterministic_stub_deepseek()
    return {"status": "NOT_APPLICABLE"}


def _provider_smoke_report_lines(summary: dict[str, Any]) -> list[str]:
    worktree = summary["worktree"]
    network = summary["network_accounting"]
    model = summary["model_discovery"]
    prompt = summary["prompt_audits"]
    provider_smoke = summary["provider_smoke"]
    ready = summary["ready"]
    tests = summary["tests"]
    pytest_counts = tests.get("pytest", {})
    historical_issues = summary.get("historical_resolved_issues", [])
    current_blockers = summary.get("current_blockers", [])
    return [
        "DEEPSEEK PROVIDER SMOKE — FINAL STATUS",
        "",
        "SAFETY",
        f"Branch: {worktree['branch']}",
        f"Commit: {worktree['git_commit']}",
        f"Scientific worktree clean: {str(worktree['scientific_worktree_clean']).lower()}",
        f"Source-freeze modified: {str(worktree['source_freeze_modified']).lower()}",
        f"Original benchmarks modified: {str(worktree['original_benchmarks_modified']).lower()}",
        f"Frozen V3 modified: {str(worktree['frozen_v3_modified']).lower()}",
        f"Knowledge modified: {str(worktree['knowledge_modified']).lower()}",
        f"Live chat calls current run: {network['chat_completion_calls_current_run']}",
        f"Network calls current run: {network['current_run_network_calls']}",
        f"Campaign known network calls: {network['campaign_known_network_calls']}",
        f"API key configured: {str(model['api_key_configured']).lower()}",
        f"API key logged: {str(summary['secret_audit']['api_key_logged']).lower()}",
        f"Authorization logged: {str(summary['secret_audit']['authorization_logged']).lower()}",
        "Mock executions: 0",
        "",
        "MODEL DISCOVERY",
        f"Configured model: {model['configured_model'] or '<unset>'}",
        f"Configured model available: {str(model['configured_model_available']).lower()}",
        f"Artifact loaded before call: {str(model['artifact_loaded_before_call']).lower()}",
        f"Live discovery performed: {str(model['live_discovery_performed']).lower()}",
        f"Artifact refreshed after call: {str(model['artifact_refreshed_after_call']).lower()}",
        f"Artifact reused without network: {str(model['artifact_reused_without_network']).lower()}",
        f"Artifact live confirmed: {str(model['live_confirmed']).lower()}",
        f"HTTP status from artifact: {model['http_status'] if model['http_status'] is not None else 'NOT_AVAILABLE'}",
        f"Models returned: {model['models_returned']}",
        f"Response SHA-256: {model['artifact_response_sha256'] or 'NOT_AVAILABLE'}",
        f"GO_MODEL_DISCOVERY: {summary['go_model_discovery']}",
        "",
        "PROMPT AUDIT",
        f"Prompts audited: {prompt['count']}",
        f"Unsafe prompts: {prompt['unsafe_prompts']}",
        f"System policy safe: {str(prompt['system_policy_safe']).lower()}",
        f"Retrieved knowledge safe: {str(prompt['retrieved_knowledge_safe']).lower()}",
        f"Dynamic payload safe: {str(prompt['dynamic_payload_safe']).lower()}",
        f"Schema instruction safe: {str(prompt['schema_instruction_safe']).lower()}",
        f"Negative policy instruction only: {str(prompt['negative_policy_instruction_only']).lower()}",
        f"Actual sensitive values: {prompt['actual_sensitive_values']}",
        f"Provider smoke payload safe: {str(provider_smoke['payload_safe']).lower()}",
        f"Provider boundary reached: {str(provider_smoke['provider_boundary_reached']).lower()}",
        f"PROVIDER_SMOKE_PROMPT_SAFE: {str(summary['provider_smoke_prompt_safe']).lower()}",
        "",
        "PROVIDER SMOKE",
        f"Execution mode: {summary['execution_mode']}",
        f"Real call attempted: {str(provider_smoke['real_call_attempted']).lower()}",
        f"Transport response received: {str(provider_smoke['transport_response_received']).lower()}",
        f"Content received: {str(provider_smoke['content_received']).lower()}",
        f"JSON parsed: {str(provider_smoke['json_parsed']).lower()}",
        f"Real call completed: {str(provider_smoke['real_call_completed']).lower()}",
        f"Chat completion calls: {provider_smoke['chat_completion_calls_current_run']}",
        f"HTTP status: {provider_smoke['http_status'] if provider_smoke['http_status'] is not None else provider_smoke['http_status_detail']}",
        f"JSON valid: {provider_smoke['json_valid'] if provider_smoke['json_valid'] is not None else 'NOT_EXECUTED'}",
        f"Schema valid: {provider_smoke['schema_valid'] if provider_smoke['schema_valid'] is not None else 'NOT_EXECUTED'}",
        f"Failure code: {provider_smoke['provider_failure_code'] or 'NONE'}",
        f"Failure stage: {provider_smoke['provider_failure_stage'] or 'NONE'}",
        f"Exception class: {provider_smoke['provider_exception_class'] or 'NONE'}",
        f"GO_PROVIDER_TRANSPORT: {provider_smoke['GO_PROVIDER_TRANSPORT']}",
        f"GO_PROVIDER_JSON: {provider_smoke['GO_PROVIDER_JSON']}",
        f"GO_PROVIDER_SMOKE_SCHEMA: {provider_smoke['GO_PROVIDER_SMOKE_SCHEMA']}",
        f"GO_PROVIDER_SMOKE: {summary['go_provider_smoke']}",
        "",
        "CAMPAIGN ISOLATION",
        "Circuit cases executed: 0",
        "Use cases executed: 0",
        "Frozen cases executed: 0",
        "Ngspice benchmark executions: 0",
        "Full campaign approved: false",
        f"Historical dry-run records: {network['historical_dry_run_records']}",
        "Comparison metrics: NOT_APPLICABLE",
        "",
        "BLOCKERS",
        f"Current blockers: {', '.join(current_blockers) if current_blockers else 'none'}",
        f"Historical resolved issues: {', '.join(item['code'] for item in historical_issues) if historical_issues else 'none'}",
        "",
        "READY",
        f"Ready for new freeze commit: {str(ready['ready_for_new_freeze_commit']).lower()}",
        f"Ready for real provider smoke after commit: {str(ready['ready_for_real_provider_smoke']).lower()}",
        f"Ready for provider smoke retry after fix: {str(ready['ready_for_provider_smoke_retry_after_fix']).lower()}",
        f"Ready for single cases: {str(ready['ready_for_single_cases']).lower()}",
        f"Ready for seven use cases: {str(ready['ready_for_seven_use_cases']).lower()}",
        f"Ready for Frozen: {str(ready['ready_for_frozen']).lower()}",
        f"Ready for full campaign: {str(ready['ready_for_full_campaign']).lower()}",
        f"Remaining blockers: {'; '.join(ready['remaining_blockers']) if ready['remaining_blockers'] else 'none'}",
        f"Final decision: {ready['final_decision']}",
        "",
        "TESTS",
        f"pytest passed: {pytest_counts.get('passed', 0)}",
        f"pytest failed: {pytest_counts.get('failed', 0)}",
        f"pytest skipped: {pytest_counts.get('skipped', 0)}",
        f"ngspice integration passed: {str(tests.get('ngspice_integration_passed', False)).lower()}",
        f"PySpice-disabled passed: {str(tests.get('pyspice_disabled_passed', False)).lower()}",
        f"Live tests executed: {str(tests.get('live_tests_executed', False)).lower()}",
    ]


def _preflight_report_lines(summary: dict[str, Any]) -> list[str]:
    tests = summary["tests"]
    pytest_counts = tests.get("pytest", {})
    worktree = summary["worktree"]
    network = summary["network_accounting"]
    return [
        "PRE-LIVE BLOCKER RESOLUTION - FINAL STATUS",
        "",
        f"Branch: {worktree['branch']}",
        "Commit created: false",
        "Push performed: false",
        f"Source-freeze modified: {str(worktree['source_freeze_modified']).lower()}",
        f"Original benchmarks modified: {str(worktree['original_benchmarks_modified']).lower()}",
        f"Frozen V3 modified: {str(worktree['frozen_v3_modified']).lower()}",
        f"Knowledge modified: {str(worktree['knowledge_modified']).lower()}",
        f"Live LLM calls: {network['campaign_chat_completion_calls']}",
        f"Network calls: {network['campaign_known_network_calls']}",
        "",
        "TESTS",
        f"pytest passed: {pytest_counts.get('passed', 0)}",
        f"pytest failed: {pytest_counts.get('failed', 0)}",
        f"pytest skipped: {pytest_counts.get('skipped', 0)}",
        f"ngspice integration passed: {str(tests.get('ngspice_integration_passed', False)).lower()}",
        f"PySpice-disabled passed: {str(tests.get('pyspice_disabled_passed', False)).lower()}",
        f"Live tests executed: {str(tests.get('live_tests_executed', False)).lower()}",
        "",
        "READY",
        f"GO_CODE_FREEZE: {summary['go_code_freeze']}",
        f"GO_SECRET_SAFETY: {summary['go_secret_safety']}",
        f"GO_MODEL_DISCOVERY: {summary['go_model_discovery']}",
        f"GO_PROVIDER_SMOKE: {summary['go_provider_smoke']}",
        f"Remaining blockers: {'; '.join(summary['ready']['remaining_blockers']) if summary['ready']['remaining_blockers'] else 'none'}",
        f"Final decision: {summary['ready']['final_decision']}",
    ]


def build_final_status_lines(summary: dict[str, Any]) -> list[str]:
    if summary.get("requested_stage") == "provider_smoke":
        return _provider_smoke_report_lines(summary)
    return _preflight_report_lines(summary)


def build_deepseek_live_summary(
    *,
    requested_stage: str | None = None,
    execution_mode: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    requested_stage = requested_stage or os.getenv("DEEPSEEK_LIVE_REQUESTED_STAGE", "final_summary").strip() or "final_summary"
    execution_mode = execution_mode or current_execution_mode()
    run_id = current_run_id() if run_id is None else run_id
    pre_live = read_json(RESULTS_DIR / "pre_live_manifest.json", {})
    secret = read_json(RESULTS_DIR / "secret_audit.json", {})
    env_example = read_json(ENV_EXAMPLE_AUDIT_JSON, secret.get("env_example_audit", {}))
    if requested_stage == "provider_smoke" and run_id:
        reconciliation = reconcile_provider_smoke_run_artifacts(run_id)
        provider_smoke = reconciliation["provider_smoke"]
        current_root_cause = reconciliation["root_cause"]
    else:
        provider_smoke = read_json(RESULTS_DIR / "provider_smoke.json", {})
        current_root_cause = read_json(PROVIDER_SMOKE_ROOT_CAUSE_JSON, {})
    inventory = build_pre_commit_inventory()
    commit_plan = build_clean_commit_plan()
    test_matrix = read_json(
        OFFLINE_TEST_MATRIX_JSON,
        {
            "pytest": {"passed": 0, "failed": 0, "skipped": 0},
            "ngspice_integration_passed": False,
            "pyspice_disabled_passed": False,
            "live_tests_executed": False,
        },
    )
    call_rows = read_csv(LIVE_CALL_AUDIT_CSV)
    budget_rows = read_csv(LIVE_BUDGET_CSV)
    prompt_rows = read_csv(PROMPT_AUDIT_CSV)
    current_prompt_rows = [row for row in prompt_rows if not run_id or row.get("run_id", "") == run_id]
    current_call_rows = [row for row in call_rows if not run_id or row.get("run_id", "") == run_id]
    current_budget_rows = [row for row in budget_rows if not run_id or row.get("run_id", "") == run_id]
    current_live_calls = [row for row in current_call_rows if _csv_truthy(row.get("provider_call_performed"))]
    campaign_live_calls = [row for row in call_rows if _csv_truthy(row.get("provider_call_performed"))]
    historical_dry_run_records = sum(1 for row in call_rows if str(row.get("execution_mode", "")).strip().upper() == "DRY_RUN")
    model_state = load_model_discovery_reuse_state()
    git_state = collect_git_state()
    inventory_rows = inventory["rows"]
    inventory_counts = inventory["counts"]
    tracked_secret_matches = secret.get("tracked_secret_matches", [])
    untracked_secret_matches = secret.get("untracked_secret_matches", [])
    current_model_discovery_calls = sum(1 for row in current_live_calls if row.get("stage") == "model_discovery")
    current_chat_completion_calls = sum(1 for row in current_live_calls if row.get("stage") != "model_discovery")
    campaign_model_discovery_calls = max(
        1 if model_state["live_confirmed"] else 0,
        sum(1 for row in campaign_live_calls if row.get("stage") == "model_discovery"),
    )
    campaign_chat_calls = sum(1 for row in campaign_live_calls if row.get("stage") != "model_discovery")
    prompt_summary = {
        "count": len(current_prompt_rows),
        "unsafe_prompts": sum(1 for row in current_prompt_rows if str(row.get("prompt_safe", "")).lower() == "false"),
        "system_policy_safe": all(str(row.get("system_policy_safe", "false")).lower() == "true" for row in current_prompt_rows)
        if current_prompt_rows
        else False,
        "retrieved_knowledge_safe": all(
            str(row.get("retrieved_knowledge_safe", "false")).lower() == "true" for row in current_prompt_rows
        )
        if current_prompt_rows
        else False,
        "dynamic_payload_safe": all(str(row.get("dynamic_payload_safe", "false")).lower() == "true" for row in current_prompt_rows)
        if current_prompt_rows
        else False,
        "schema_instruction_safe": all(
            str(row.get("schema_instruction_safe", "false")).lower() == "true" for row in current_prompt_rows
        )
        if current_prompt_rows
        else False,
        "negative_policy_instruction_only": any(
            str(row.get("negative_policy_instruction_only", "false")).lower() == "true" for row in current_prompt_rows
        ),
        "actual_sensitive_values": sum(
            1 for row in current_prompt_rows if str(row.get("actual_sensitive_value_present", "false")).lower() == "true"
        ),
    }
    provider_smoke_prompt_safe = bool(provider_smoke.get("provider_smoke_prompt_safe", prompt_summary["count"] > 0))
    artifact_loaded_before_call = model_state["valid"]
    live_discovery_performed = current_model_discovery_calls > 0
    artifact_refreshed_after_call = live_discovery_performed
    artifact_reused_without_network = model_state["valid"] and not live_discovery_performed
    provider_smoke_failed_live = bool(provider_smoke.get("real_call_attempted")) and provider_smoke.get("GO_PROVIDER_SMOKE") != "PASS"
    ready_for_new_freeze_commit = (
        secret.get("go_secret_safety") == "PASS"
        and not git_state.get("source_freeze_modified", False)
        and not git_state.get("original_benchmark_files_modified", False)
        and not git_state.get("knowledge_files_modified", False)
        and not git_state.get("frozen_v3_files_modified", False)
    )
    ready_for_real_provider_smoke = (
        execution_mode == "DRY_RUN"
        and pre_live.get("go_code_freeze", "NO_GO") == "PASS"
        and secret.get("go_secret_safety") == "PASS"
        and model_state["valid"]
        and provider_smoke_prompt_safe
        and bool(provider_smoke.get("provider_boundary_reached", False))
        and not provider_smoke_failed_live
    )
    full_campaign_guard = live_guard_state(require_full_campaign=True)
    ready_for_provider_smoke_retry_after_fix = (
        provider_smoke.get("provider_failure_code") == "SCHEMA_ERROR"
        and secret.get("go_secret_safety") == "PASS"
        and model_state["valid"]
        and provider_smoke_prompt_safe
        and bool(provider_smoke.get("provider_boundary_reached", False))
    )
    ready_for_single_cases = provider_smoke.get("GO_PROVIDER_SMOKE") == "PASS" and full_campaign_guard["allowed"]
    ready_for_seven_use_cases = False
    ready_for_frozen = False
    ready_for_full_campaign = False
    remaining_blockers: list[str] = []
    current_blockers: list[str] = []
    if pre_live.get("go_code_freeze") != "PASS":
        remaining_blockers.append("commit the current source changes to restore GO_CODE_FREEZE=PASS")
        current_blockers.append("CODE_FREEZE")
    if secret.get("go_secret_safety") != "PASS":
        remaining_blockers.append("secret audit must pass before any live stage")
        current_blockers.append("SECRET_AUDIT")
    if not model_state["valid"]:
        remaining_blockers.append("model_discovery.json must remain valid and reusable")
        current_blockers.append("MODEL_DISCOVERY")
    if not provider_smoke_prompt_safe:
        remaining_blockers.append("provider smoke prompt audit must stay safe")
        current_blockers.append("PROMPT_AUDIT")
    if not provider_smoke.get("provider_boundary_reached", False):
        remaining_blockers.append("provider smoke dry-run must reach the provider boundary")
        current_blockers.append("PROVIDER_BOUNDARY")
    if provider_smoke.get("GO_PROVIDER_SMOKE_SCHEMA") == "NO_GO":
        remaining_blockers.append("provider smoke schema validation failure")
        current_blockers.append("SCHEMA_ERROR")
    if provider_smoke.get("GO_PROVIDER_SMOKE") == "PASS" and not full_campaign_guard["allowed"]:
        remaining_blockers.append("DEEPSEEK_FULL_CAMPAIGN_APPROVED remains disabled for wider live stages")
    historical_issue = build_provider_smoke_blocker_analysis()
    historical_resolved_issues = [
        {
            "code": "RESOLVED_PROMPT_AUDIT_FALSE_POSITIVE",
            "status": "RESOLVED",
            "summary": historical_issue["root_cause"],
        }
    ]
    summary = {
        "campaign_name": CAMPAIGN_NAME,
        "generated_at": utc_now_iso(),
        "requested_stage": requested_stage,
        "execution_mode": execution_mode,
        "go_code_freeze": pre_live.get("go_code_freeze", "NO_GO"),
        "go_secret_safety": secret.get("go_secret_safety", "NO_GO"),
        "go_model_discovery": "PASS" if model_state["valid"] else "NO_GO",
        "provider_smoke_prompt_safe": provider_smoke_prompt_safe,
        "go_provider_smoke": provider_smoke.get("GO_PROVIDER_SMOKE", "NOT_EXECUTED"),
        "env_example": env_example,
        "secret_audit": {
            "tracked_secrets": len(tracked_secret_matches),
            "untracked_secrets": len(untracked_secret_matches),
            "authorization_headers": secret.get("authorization_header_matches", 0),
            "values_redacted": secret.get("values_redacted", True),
            "false_positive_rules_corrected": secret.get("false_positive_rules_corrected", True),
            "api_key_logged": bool(tracked_secret_matches or untracked_secret_matches),
            "authorization_logged": bool(secret.get("authorization_header_matches", 0)),
        },
        "model_discovery": {
            "configured_model": model_state["configured_model"],
            "configured_model_available": model_state["configured_model_available"],
            "reused_from_artifact": artifact_reused_without_network,
            "performed_current_run": live_discovery_performed,
            "artifact_loaded_before_call": artifact_loaded_before_call,
            "live_discovery_performed": live_discovery_performed,
            "artifact_refreshed_after_call": artifact_refreshed_after_call,
            "artifact_reused_without_network": artifact_reused_without_network,
            "artifact_timestamp": model_state["artifact_timestamp"],
            "artifact_response_sha256": model_state["artifact_response_sha256"],
            "calls_current_run": current_model_discovery_calls,
            "live_confirmed": model_state["live_confirmed"],
            "models_returned": model_state["models_returned"],
            "http_status": model_state["http_status"],
            "api_key_configured": read_json(RESULTS_DIR / "model_discovery.json", {}).get("api_key_configured", False),
            "validation_errors": model_state["errors"],
        },
        "provider_smoke": {
            "prompt_safe": provider_smoke_prompt_safe,
            "payload_safe": provider_smoke.get("payload_safe", False),
            "provider_boundary_reached": bool(provider_smoke.get("provider_boundary_reached", False)),
            "real_call_attempted": bool(provider_smoke.get("real_call_attempted", False)),
            "real_call_completed": bool(provider_smoke.get("real_call_completed", False)),
            "transport_response_received": bool(provider_smoke.get("transport_response_received", False)),
            "content_received": bool(provider_smoke.get("content_received", False)),
            "json_parsed": bool(provider_smoke.get("json_parsed", False)),
            "chat_completion_calls_current_run": int(provider_smoke.get("chat_completion_calls_current_run", 0) or 0),
            "http_status": provider_smoke.get("http_status"),
            "http_status_detail": provider_smoke.get("http_status_detail", ""),
            "json_valid": provider_smoke.get("json_valid"),
            "schema_valid": provider_smoke.get("schema_valid"),
            "semantic_valid": provider_smoke.get("semantic_valid", "NOT_EXECUTED"),
            "terminal_status": provider_smoke.get("terminal_status", "NOT_EXECUTED"),
            "provider_failure": provider_smoke.get("provider_failure", ""),
            "provider_failure_code": provider_smoke.get("provider_failure_code", provider_smoke.get("provider_failure", "")),
            "provider_failure_stage": provider_smoke.get("provider_failure_stage", ""),
            "provider_exception_class": provider_smoke.get("provider_exception_class", ""),
            "provider_exception_message_sanitized": provider_smoke.get("provider_exception_message_sanitized", ""),
            "provider_transport_success": bool(provider_smoke.get("provider_transport_success", False)),
            "GO_PROVIDER_TRANSPORT": provider_smoke.get("GO_PROVIDER_TRANSPORT", "NOT_EXECUTED"),
            "GO_PROVIDER_JSON": provider_smoke.get("GO_PROVIDER_JSON", "NOT_EXECUTED"),
            "GO_PROVIDER_SMOKE_SCHEMA": provider_smoke.get("GO_PROVIDER_SMOKE_SCHEMA", "NOT_EXECUTED"),
            "dynamic_sensitive_fields": int(provider_smoke.get("dynamic_sensitive_fields", 0) or 0),
            "benchmark_identifiers": int(provider_smoke.get("benchmark_identifiers", 0) or 0),
            "frozen_identifiers": int(provider_smoke.get("frozen_identifiers", 0) or 0),
            "historical_values": int(provider_smoke.get("historical_values", 0) or 0),
            "local_paths": int(provider_smoke.get("local_paths", 0) or 0),
        },
        "prompt_audits": prompt_summary,
        "network_accounting": {
            "model_discovery_performed_current_run": current_model_discovery_calls > 0,
            "model_discovery_reused_from_artifact": model_state["reused_from_artifact"],
            "model_discovery_artifact_live_confirmed": model_state["live_confirmed"],
            "model_discovery_artifact_timestamp": model_state["artifact_timestamp"],
            "model_discovery_artifact_response_sha256": model_state["artifact_response_sha256"],
            "model_discovery_calls_current_run": current_model_discovery_calls,
            "chat_completion_calls_current_run": current_chat_completion_calls,
            "current_run_network_calls": current_model_discovery_calls + current_chat_completion_calls,
            "campaign_model_discovery_calls": campaign_model_discovery_calls,
            "campaign_chat_completion_calls": campaign_chat_calls,
            "campaign_known_network_calls": campaign_model_discovery_calls + campaign_chat_calls,
            "historical_dry_run_records": historical_dry_run_records,
        },
        "worktree": {
            "branch": git_state.get("branch", ""),
            "git_commit": git_state.get("git_commit", ""),
            "modified_files": len(inventory_rows),
            "source_files": inventory_counts.get("SOURCE_CODE", 0),
            "test_files": inventory_counts.get("TEST", 0),
            "prompt_files": inventory_counts.get("PROMPT", 0),
            "generated_artifacts": inventory_counts.get("GENERATED_PRELIVE_ARTIFACT", 0),
            "temporary_files": inventory_counts.get("TEMPORARY", 0),
            "files_proposed_for_commit": len(commit_plan["FILES_TO_COMMIT"]),
            "files_proposed_for_exclusion": len(commit_plan["FILES_TO_EXCLUDE"]),
            "scientific_worktree_clean": inventory["scientific_worktree_clean"],
            "source_freeze_modified": git_state.get("source_freeze_modified", False),
            "original_benchmarks_modified": git_state.get("original_benchmark_files_modified", False),
            "knowledge_modified": git_state.get("knowledge_files_modified", False),
            "frozen_v3_modified": git_state.get("frozen_v3_files_modified", False),
        },
        "tests": {
            **test_matrix,
            "current_run_prompt_tokens": sum(int(float(row.get("prompt_tokens", 0) or 0)) for row in current_budget_rows),
            "current_run_completion_tokens": sum(int(float(row.get("completion_tokens", 0) or 0)) for row in current_budget_rows),
            "current_run_total_tokens": sum(int(float(row.get("total_tokens", 0) or 0)) for row in current_budget_rows),
        },
        "current_blockers": current_blockers,
        "historical_resolved_issues": historical_resolved_issues,
        "blocker_analysis": historical_issue,
        "provider_smoke_root_cause": current_root_cause,
        "comparison": _comparison_for_stage(requested_stage),
        "ready": {
            "ready_for_new_freeze_commit": ready_for_new_freeze_commit,
            "ready_for_real_provider_smoke": ready_for_real_provider_smoke,
            "ready_for_provider_smoke_retry_after_fix": ready_for_provider_smoke_retry_after_fix,
            "ready_for_single_cases": ready_for_single_cases,
            "ready_for_seven_use_cases": ready_for_seven_use_cases,
            "ready_for_frozen": ready_for_frozen,
            "ready_for_full_campaign": ready_for_full_campaign,
            "remaining_blockers": remaining_blockers,
            "final_decision": (
                "FIX_PROVIDER_SMOKE_SCHEMA_THEN_RETRY"
                if "SCHEMA_ERROR" in current_blockers
                else "READY_FOR_REAL_PROVIDER_SMOKE"
                if ready_for_real_provider_smoke
                else "NO_GO"
            ),
        },
    }
    write_json(FINAL_SUMMARY_JSON, summary)
    if run_id:
        write_json(provider_smoke_run_results_dir(run_id) / "deepseek_live_campaign_summary.json", summary)
    lines = build_final_status_lines(summary)
    write_markdown(FINAL_STATUS_MD, lines)
    if requested_stage == "provider_smoke":
        write_markdown(REPORTS_DIR / "provider_smoke.md", lines)
        if run_id:
            write_markdown(provider_smoke_run_reports_dir(run_id) / "provider_smoke.md", lines)
    return summary


def run_stage(stage: str, *, dry_run: bool = False) -> dict[str, Any]:
    if stage == "model_discovery":
        return run_model_discovery(dry_run=dry_run)
    if stage == "provider_smoke":
        return run_provider_smoke()
    if stage == "single_ac":
        return run_single_case("single_ac")
    if stage == "single_transient":
        return run_single_case("single_transient")
    if stage == "single_oscillator":
        return run_single_case("single_oscillator")
    if stage == "single_schmitt":
        return run_single_case("single_schmitt")
    if stage == "use_case_smoke":
        return run_use_case_smoke()
    if stage == "frozen_protocol_freeze":
        return freeze_frozen_protocol()
    if stage == "frozen_trial_1":
        return run_frozen_trial_one()
    if stage == "frozen_trials_2_3":
        return run_frozen_three_trials()
    if stage == "post_live_deterministic":
        return run_post_live_deterministic_parity()
    if stage == "final_summary":
        return build_deepseek_live_summary(
            requested_stage=os.getenv("DEEPSEEK_LIVE_REQUESTED_STAGE", "final_summary"),
            execution_mode=current_execution_mode(),
            run_id=current_run_id(),
        )
    raise ValueError(f"Unsupported stage: {stage}")
