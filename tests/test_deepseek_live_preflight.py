from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from deepseek_live_lib import (  # noqa: E402
    _scan_secrets_in_file,
    audit_env_example,
    freeze_invalidation_reason,
    invalidates_source_freeze,
    is_git_ignored,
    scan_text_for_secret_matches,
)


def test_empty_deepseek_key_assignment_is_safe():
    assert scan_text_for_secret_matches("DEEPSEEK_API_KEY=\n") == []


def test_variable_name_without_value_is_safe():
    assert scan_text_for_secret_matches("Set DEEPSEEK_API_KEY before running the live provider.\n") == []


def test_realistic_nonempty_key_is_flagged():
    matches = scan_text_for_secret_matches("DEEPSEEK_API_KEY=sk-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890\n")
    assert matches == [{"match_type": "deepseek_env_assignment"}]


def test_authorization_header_is_flagged():
    matches = scan_text_for_secret_matches('"Authorization": "Bearer sk-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"')
    assert matches == [{"match_type": "authorization_header"}]


def test_secret_value_is_redacted_from_report(tmp_path: Path):
    secret_value = "sk-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text(f"DEEPSEEK_API_KEY={secret_value}\n", encoding="utf-8")

    payload = _scan_secrets_in_file(secret_file)

    assert payload == [{"path": str(secret_file).replace("\\", "/"), "match_type": "deepseek_env_assignment"}]
    assert secret_value not in json.dumps(payload)


def test_env_example_is_safe():
    audit = audit_env_example(ROOT / ".env.example")
    assert audit["safe"] is True


def test_env_file_is_ignored():
    assert is_git_ignored(".env") is True


@pytest.mark.parametrize(
    "relative_path",
    [
        "artifacts/deepseek_live_v1/provider_smoke/dry_run.json",
        "results/deepseek_live_v1/pre_live_manifest.json",
        "reports/deepseek_live_v1/final_status.md",
    ],
)
def test_campaign_artifacts_do_not_invalidate_source_freeze(relative_path: str):
    assert invalidates_source_freeze(relative_path) is False


def test_source_change_invalidates_freeze():
    assert invalidates_source_freeze("scripts/deepseek_live_lib.py") is True


def test_prompt_change_invalidates_freeze():
    assert invalidates_source_freeze(
        "spec2testbench/infrastructure/llm/prompts/deepseek_testbench_planner_book_v1.txt"
    ) is True


def test_knowledge_change_invalidates_freeze():
    assert invalidates_source_freeze("knowledge/spec2testbench/canonical_harness_policies.yaml") is True


def test_checker_change_invalidates_freeze():
    assert freeze_invalidation_reason("spec2testbench/application/usecases/run_verification.py") == "CHECKER"
    assert invalidates_source_freeze("spec2testbench/application/usecases/run_verification.py") is True


def test_benchmark_change_invalidates_freeze():
    assert invalidates_source_freeze("benchmark/analogcoder_pro/p10_lowpass.cir") is True


def test_artifact_outside_allowed_root_invalidates_freeze():
    assert freeze_invalidation_reason("artifacts/some_other_campaign/output.json") == "ARTIFACT_OUTSIDE_ALLOWED_ROOT"
    assert invalidates_source_freeze("artifacts/some_other_campaign/output.json") is True
