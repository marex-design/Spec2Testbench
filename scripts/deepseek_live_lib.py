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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spec2testbench.application.ports.llm_provider import LLMProviderError
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
COMPILER_VERSION = "testbench_plan_compiler_v1"
CHECKER_VERSION = "verification_pipeline_v1"
RETRIEVER_VERSION = "deterministic_book_retriever_v1"
EXPERIMENTS_DIR = ROOT / "experiments" / CAMPAIGN_NAME
ARTIFACTS_DIR = ROOT / "artifacts" / CAMPAIGN_NAME
RESULTS_DIR = ROOT / "results" / CAMPAIGN_NAME
REPORTS_DIR = ROOT / "reports" / CAMPAIGN_NAME
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
    "benchmarks_normalized/",
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


def sha256_tree(root: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        entries.append({"path": relative, "sha256": sha256_file(path)})
    return json_sha256(entries)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


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


def append_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    existing = read_csv(path)
    combined = existing + [{key: value for key, value in row.items()} for row in rows]
    write_csv(path, combined)


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
    if path.startswith("benchmark/") or path.startswith("benchmarks_normalized/"):
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
    if path.startswith("benchmark/") or path.startswith("benchmarks_normalized/"):
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
    _, paper_diff, _ = _git_output("diff", "--", "paper_final/")
    _, head, _ = _git_output("rev-parse", "HEAD")
    _, branch, _ = _git_output("branch", "--show-current")
    modified_lines = [line for line in status_short.splitlines() if line.strip()]
    modified_paths = [path for _, path in (parse_status_line(line) for line in modified_lines) if path]
    paper_modified = bool(paper_diff.strip()) or any(path.startswith("paper_final/") for path in modified_paths)
    benchmark_modified = any(path.startswith("benchmark/analogcoder_pro/") for path in modified_paths)
    frozen_v3_modified = any(
        path.startswith("experiments/frozen_pilot_v3/")
        or path == "results/frozen_pilot_results_v3.csv"
        or path == "reports/frozen_pilot_results_v3.md"
        for path in modified_paths
    )
    scientific_dirty_paths = sorted(path for path in modified_paths if invalidates_source_freeze(path))
    scientific_worktree_clean = not scientific_dirty_paths
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
        and not paper_modified
        and not benchmark_modified
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
        "paper_diff": paper_diff.strip(),
        "paper_files_modified": paper_modified,
        "original_benchmark_files_modified": benchmark_modified,
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
        "paper_files_modified": git_state["paper_files_modified"],
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
        "paper_diff": git_state["paper_diff"],
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
            f"- Paper files modified: {str(payload['paper_files_modified']).lower()}",
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


def run_model_discovery() -> dict[str, Any]:
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
    stage: str,
    internal_case_id: str,
    opaque_case_id: str,
    trial_id: str,
    system_prompt: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    combined = f"{system_prompt}\n{json.dumps(request_payload, sort_keys=True, ensure_ascii=True)}"
    combined_upper = combined.upper()
    ground_truth_found = any(token in combined_upper for token in GROUND_TRUTH_TOKENS)
    historical_verdict_found = any(token in combined_upper for token in {"PASS", "FAIL", "TRUE_ACCEPT", "TRUE_DETECTION", "FALSE_ACCEPT", "FALSE_REJECT"})
    historical_metric_found = "MEASURED_VALUE" in combined_upper or "HISTORICAL_METRIC" in combined_upper
    mutation_id_found = bool(re.search(r"\b(FP\d+_CV_\d+|MUTATION_ID|WRDATA_)", combined_upper))
    benchmark_name_found = "ANALOGCODER-PRO" in combined_upper or "FROZEN PILOT" in combined_upper or internal_case_id.upper() in combined_upper
    local_path_found = bool(re.search(r"[A-Za-z]:\\\\|[A-Za-z]:/|benchmark/analogcoder_pro/|paper_final/", combined))
    unsafe_comment_found = bool(re.search(r"IGNORE PREVIOUS|EXPECTED_VERDICT|GROUND_TRUTH|NONCOMPLIANT", combined_upper))
    prompt_safe = not any(
        [
            ground_truth_found,
            historical_verdict_found,
            historical_metric_found,
            mutation_id_found,
            benchmark_name_found,
            local_path_found,
            unsafe_comment_found,
        ]
    )
    return {
        "stage": stage,
        "opaque_case_id": opaque_case_id,
        "trial_id": trial_id,
        "ground_truth_found": ground_truth_found,
        "historical_verdict_found": historical_verdict_found,
        "historical_metric_found": historical_metric_found,
        "mutation_id_found": mutation_id_found,
        "benchmark_name_found": benchmark_name_found,
        "local_path_found": local_path_found,
        "unsafe_comment_found": unsafe_comment_found,
        "prompt_safe": prompt_safe,
        "prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
    }


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
            "prompt_sha256": prompt_sha,
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
        "prompt_sha256": prompt_sha,
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
        "prompt_sha256": prompt_sha,
        "knowledge_bundle_sha256": bundle.bundle_sha256,
    }
    budget_row = {
        "stage": stage,
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
    return run_case_batch(
        stage="provider_smoke",
        cases=[default_use_case_cases()[3] if len(default_use_case_cases()) > 3 else default_use_case_cases()[0]],
        trials=1,
        output_csv=RESULTS_DIR / "provider_smoke_calls.csv",
        output_json=RESULTS_DIR / "provider_smoke.json",
        output_md=REPORTS_DIR / "provider_smoke.md",
        go_field="GO_PROVIDER_SMOKE",
        require_full_campaign=False,
        max_repairs=int(os.getenv("DEEPSEEK_MAX_REPAIRS_SINGLE_CASE", "2")),
    )


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


def build_deepseek_live_summary() -> dict[str, Any]:
    pre_live = read_json(RESULTS_DIR / "pre_live_manifest.json", {})
    secret = read_json(RESULTS_DIR / "secret_audit.json", {})
    env_example = read_json(ENV_EXAMPLE_AUDIT_JSON, secret.get("env_example_audit", {}))
    model = read_json(RESULTS_DIR / "model_discovery.json", {})
    provider_smoke = read_json(RESULTS_DIR / "provider_smoke.json", {})
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
    comparison = compare_deterministic_stub_deepseek()
    live_call_rows = [row for row in call_rows if row.get("provider_call_performed") in {"True", "true", True}]
    model_discovery_calls = sum(1 for row in live_call_rows if row.get("stage") == "model_discovery")
    chat_completion_calls = sum(1 for row in live_call_rows if row.get("stage") != "model_discovery")
    inventory_rows = inventory["rows"]
    inventory_counts = inventory["counts"]
    tracked_secret_matches = secret.get("tracked_secret_matches", [])
    untracked_secret_matches = secret.get("untracked_secret_matches", [])
    ready_for_clean_commit = (
        secret.get("go_secret_safety") == "PASS"
        and not pre_live.get("paper_files_modified", False)
        and not pre_live.get("original_benchmark_files_modified", False)
        and not pre_live.get("frozen_v3_files_modified", False)
    )
    ready_for_model_discovery_after_commit = ready_for_clean_commit
    ready_for_provider_smoke_after_commit = ready_for_model_discovery_after_commit and model.get("go_model_discovery") == "PASS"
    remaining_blockers: list[str] = []
    if pre_live.get("go_code_freeze") != "PASS":
        remaining_blockers.append("uncommitted worktree keeps GO_CODE_FREEZE at NO_GO")
    if secret.get("go_secret_safety") != "PASS":
        remaining_blockers.append("secret audit must pass before any live stage")
    if not ready_for_provider_smoke_after_commit:
        remaining_blockers.append("model discovery has not been executed and live approval remains disabled")
    summary = {
        "campaign_name": CAMPAIGN_NAME,
        "generated_at": utc_now_iso(),
        "go_code_freeze": pre_live.get("go_code_freeze", "NO_GO"),
        "go_secret_safety": secret.get("go_secret_safety", "NO_GO"),
        "go_model_discovery": model.get("go_model_discovery", "NO_GO"),
        "go_provider_smoke": provider_smoke.get("GO_PROVIDER_SMOKE", "NOT_EXECUTED"),
        "live_calls_attempted": len(live_call_rows),
        "network_llm_calls": len(live_call_rows),
        "model_discovery_calls": model_discovery_calls,
        "chat_completion_calls": chat_completion_calls,
        "prompt_audits": len(prompt_rows),
        "unsafe_prompts": sum(1 for row in prompt_rows if str(row.get("prompt_safe", "")).lower() == "false"),
        "input_tokens": sum(int(float(row.get("prompt_tokens", 0) or 0)) for row in budget_rows),
        "output_tokens": sum(int(float(row.get("completion_tokens", 0) or 0)) for row in budget_rows),
        "total_tokens": sum(int(float(row.get("total_tokens", 0) or 0)) for row in budget_rows),
        "env_example": env_example,
        "secret_audit": {
            "tracked_secrets": len(tracked_secret_matches),
            "untracked_secrets": len(untracked_secret_matches),
            "authorization_headers": secret.get("authorization_header_matches", 0),
            "values_redacted": secret.get("values_redacted", True),
            "false_positive_rules_corrected": secret.get("false_positive_rules_corrected", True),
        },
        "worktree": {
            "modified_files": len(inventory_rows),
            "source_files": inventory_counts.get("SOURCE_CODE", 0),
            "test_files": inventory_counts.get("TEST", 0),
            "prompt_files": inventory_counts.get("PROMPT", 0),
            "generated_artifacts": inventory_counts.get("GENERATED_PRELIVE_ARTIFACT", 0),
            "temporary_files": inventory_counts.get("TEMPORARY", 0),
            "files_proposed_for_commit": len(commit_plan["FILES_TO_COMMIT"]),
            "files_proposed_for_exclusion": len(commit_plan["FILES_TO_EXCLUDE"]),
            "scientific_worktree_clean": inventory["scientific_worktree_clean"],
        },
        "tests": test_matrix,
        "ready": {
            "ready_for_clean_commit": ready_for_clean_commit,
            "ready_for_push": False,
            "ready_for_model_discovery_after_commit": ready_for_model_discovery_after_commit,
            "ready_for_provider_smoke_after_commit": ready_for_provider_smoke_after_commit,
            "remaining_blockers": remaining_blockers,
            "final_decision": "NO_GO",
        },
        "comparison": comparison,
    }
    write_json(FINAL_SUMMARY_JSON, summary)
    pytest_counts = test_matrix.get("pytest", {})
    expected_blocker = "uncommitted worktree changes" if pre_live.get("go_code_freeze") != "PASS" else "none"
    lines = [
        "PRE-LIVE BLOCKER RESOLUTION - FINAL STATUS",
        "",
        f"Branch: {pre_live.get('branch', '')}",
        "Commit created: false",
        "Push performed: false",
        f"Paper modified: {str(pre_live.get('paper_files_modified', False)).lower()}",
        f"Original benchmarks modified: {str(pre_live.get('original_benchmark_files_modified', False)).lower()}",
        f"Frozen V3 modified: {str(pre_live.get('frozen_v3_files_modified', False)).lower()}",
        f"Live LLM calls: {summary['live_calls_attempted']}",
        f"Network calls: {summary['network_llm_calls']}",
        "",
        "ENV EXAMPLE",
        f"File found: {str(env_example.get('file_exists', False)).lower()}",
        f"Tracked: {str(env_example.get('tracked_by_git', False)).lower()}",
        f"API key variable: {str(env_example.get('api_key_variable_present', False)).lower()}",
        f"API key value empty: {str(env_example.get('api_key_value_empty', False)).lower()}",
        f"Realistic secret placeholder: {str(env_example.get('realistic_key_placeholder_present', False)).lower()}",
        f"Safe: {str(env_example.get('safe', False)).lower()}",
        "",
        "SECRET AUDIT",
        f"Tracked secrets: {len(tracked_secret_matches)}",
        f"Untracked secrets: {len(untracked_secret_matches)}",
        f"Authorization headers: {secret.get('authorization_header_matches', 0)}",
        f"Values redacted: {str(secret.get('values_redacted', True)).lower()}",
        f"False-positive rules corrected: {str(secret.get('false_positive_rules_corrected', True)).lower()}",
        f"GO_SECRET_SAFETY: {summary['go_secret_safety']}",
        "",
        "WORKTREE",
        f"Modified files: {len(inventory_rows)}",
        f"Source files: {inventory_counts.get('SOURCE_CODE', 0)}",
        f"Test files: {inventory_counts.get('TEST', 0)}",
        f"Prompt files: {inventory_counts.get('PROMPT', 0)}",
        f"Generated artifacts: {inventory_counts.get('GENERATED_PRELIVE_ARTIFACT', 0)}",
        f"Temporary files: {inventory_counts.get('TEMPORARY', 0)}",
        f"Files proposed for commit: {len(commit_plan['FILES_TO_COMMIT'])}",
        f"Files proposed for exclusion: {len(commit_plan['FILES_TO_EXCLUDE'])}",
        f"Scientific worktree clean: {str(inventory['scientific_worktree_clean']).lower()}",
        f"GO_CODE_FREEZE: {summary['go_code_freeze']}",
        "",
        "TESTS",
        f"pytest passed: {pytest_counts.get('passed', 0)}",
        f"pytest failed: {pytest_counts.get('failed', 0)}",
        f"pytest skipped: {pytest_counts.get('skipped', 0)}",
        f"ngspice integration passed: {str(test_matrix.get('ngspice_integration_passed', False)).lower()}",
        f"PySpice-disabled passed: {str(test_matrix.get('pyspice_disabled_passed', False)).lower()}",
        f"Live tests executed: {str(test_matrix.get('live_tests_executed', False)).lower()}",
        "",
        "DRY RUN",
        f"Provider network calls: {summary['network_llm_calls']}",
        f"Model discovery calls: {summary['model_discovery_calls']}",
        f"Chat completion calls: {summary['chat_completion_calls']}",
        f"GO_PROVIDER_SMOKE: {summary['go_provider_smoke']}",
        f"Expected blocker: {expected_blocker}",
        "",
        "READY",
        f"Ready for clean commit: {str(ready_for_clean_commit).lower()}",
        f"Ready for push: false",
        f"Ready for model discovery after commit: {str(ready_for_model_discovery_after_commit).lower()}",
        f"Ready for provider smoke after commit: {str(ready_for_provider_smoke_after_commit).lower()}",
        f"Remaining blockers: {'; '.join(remaining_blockers) if remaining_blockers else 'none'}",
        "Final decision: NO_GO",
    ]
    write_markdown(FINAL_STATUS_MD, lines)
    return summary


def run_stage(stage: str) -> dict[str, Any]:
    if stage == "model_discovery":
        return run_model_discovery()
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
        return build_deepseek_live_summary()
    raise ValueError(f"Unsupported stage: {stage}")
