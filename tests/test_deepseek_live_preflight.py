from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deepseek_live_lib as live_lib  # noqa: E402
from deepseek_live_lib import (  # noqa: E402
    PromptAuditInput,
    _scan_secrets_in_file,
    audit_env_example,
    audit_prompt_payload,
    build_final_status_lines,
    build_provider_smoke_prompt_audit_input,
    execute_provider_smoke_probe,
    freeze_invalidation_reason,
    invalidates_source_freeze,
    is_git_ignored,
    scan_text_for_secret_matches,
)


def _fake_secret_value() -> str:
    return "".join(
        [
            "AbCdEfGhIjKl",
            "MnOpQrStUvWx",
            "Yz1234567890",
            "AlphaBeta42",
        ]
    )


def _deepseek_api_key_name() -> str:
    return "DEEPSEEK" "_API_KEY"


def _authorization_header_name() -> str:
    return "Author" "ization"


def _bearer_scheme() -> str:
    return "Be" "arer"


def _audit_result(
    *,
    system_policy: str = "Return JSON only.",
    retrieved_knowledge=None,
    sanitized_dynamic_payload=None,
    output_schema_instruction: str = "{}",
):
    audit_input = PromptAuditInput(
        system_policy=system_policy,
        retrieved_knowledge={} if retrieved_knowledge is None else retrieved_knowledge,
        sanitized_dynamic_payload={} if sanitized_dynamic_payload is None else sanitized_dynamic_payload,
        output_schema_instruction=output_schema_instruction,
        stage="provider_smoke",
        opaque_case_id="opaque_case",
        trial_id="trial_01",
    )
    return audit_prompt_payload(audit_input=audit_input)


def _provider_smoke_summary(*, requested_stage: str) -> dict:
    return {
        "requested_stage": requested_stage,
        "execution_mode": "DRY_RUN",
        "go_model_discovery": "PASS",
        "go_provider_smoke": "NOT_EXECUTED",
        "go_code_freeze": "NO_GO",
        "go_secret_safety": "PASS",
        "provider_smoke_prompt_safe": True,
        "secret_audit": {"api_key_logged": False, "authorization_logged": False},
        "model_discovery": {
            "configured_model": "deepseek-v4-flash",
            "configured_model_available": True,
            "reused_from_artifact": True,
            "live_confirmed": True,
            "performed_current_run": False,
            "http_status": 200,
            "models_returned": 2,
            "artifact_response_sha256": "abc123",
            "api_key_configured": True,
        },
        "prompt_audits": {
            "count": 1,
            "unsafe_prompts": 0,
            "system_policy_safe": True,
            "retrieved_knowledge_safe": True,
            "dynamic_payload_safe": True,
            "schema_instruction_safe": True,
            "negative_policy_instruction_only": True,
            "actual_sensitive_values": 0,
        },
        "provider_smoke": {
            "payload_safe": True,
            "provider_boundary_reached": True,
            "real_call_attempted": False,
            "real_call_completed": False,
            "chat_completion_calls_current_run": 0,
            "json_valid": None,
            "schema_valid": None,
            "provider_failure": "",
        },
        "network_accounting": {
            "chat_completion_calls_current_run": 0,
            "current_run_network_calls": 0,
            "campaign_known_network_calls": 1,
            "campaign_chat_completion_calls": 0,
        },
        "worktree": {
            "branch": "test",
            "git_commit": "abc123",
            "scientific_worktree_clean": False,
            "paper_modified": False,
            "original_benchmarks_modified": False,
            "frozen_v3_modified": False,
            "knowledge_modified": False,
        },
        "ready": {
            "ready_for_new_freeze_commit": False,
            "ready_for_real_provider_smoke": False,
            "ready_for_single_cases": False,
            "ready_for_frozen": False,
            "remaining_blockers": ["commit the current source changes to restore GO_CODE_FREEZE=PASS"],
            "final_decision": "NO_GO",
        },
        "tests": {
            "pytest": {"passed": 1, "failed": 0, "skipped": 0},
            "ngspice_integration_passed": True,
            "pyspice_disabled_passed": True,
            "live_tests_executed": False,
        },
    }


def _write_valid_model_discovery_artifact(results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "model_discovery.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-07-23T08:18:02+00:00",
                "api_key_configured": True,
                "base_url": "https://api.deepseek.com",
                "configured_model": "deepseek-v4-flash",
                "legacy_alias": False,
                "legacy_alias_allowed": False,
                "model_ids": ["deepseek-v4-flash", "deepseek-v4-pro"],
                "models_returned": 2,
                "http_status": 200,
                "request_id": None,
                "response_sha256": "8a31d8b828b0d089344a4f0ffcecc51cc0342b8b4c35e9fa11154892d229c9c5",
                "configured_model_available": True,
                "campaign_model_status": "READY",
                "suitable_for_canonical_reporting": True,
                "recommended_model": "deepseek-v4-flash",
                "go_model_discovery": "PASS",
                "live_guard_status": "READY",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_empty_deepseek_key_assignment_is_safe():
    assert scan_text_for_secret_matches("DEEPSEEK_API_KEY=\n") == []


def test_variable_name_without_value_is_safe():
    assert scan_text_for_secret_matches("Set DEEPSEEK_API_KEY before running the live provider.\n") == []


def test_realistic_nonempty_key_is_flagged():
    matches = scan_text_for_secret_matches(f"{_deepseek_api_key_name()}={_fake_secret_value()}\n")
    assert matches == [{"match_type": "deepseek_env_assignment"}]


def test_authorization_header_is_flagged():
    matches = scan_text_for_secret_matches(
        f'"{_authorization_header_name()}": "{_bearer_scheme()} {_fake_secret_value()}"'
    )
    assert matches == [{"match_type": "authorization_header"}]


def test_secret_value_is_redacted_from_report(tmp_path: Path):
    secret_value = _fake_secret_value()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text(f"{_deepseek_api_key_name()}={secret_value}\n", encoding="utf-8")

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


def test_committed_experiment_manifests_do_not_use_dynamic_created_at():
    manifest_paths = [
        ROOT / "experiments/deepseek_live_v1/provider_smoke_manifest.yaml",
        ROOT / "experiments/deepseek_live_v1/single_case_manifest.yaml",
        ROOT / "experiments/deepseek_live_v1/use_case_smoke_manifest.yaml",
        ROOT / "experiments/deepseek_live_v1/frozen_case_manifest.yaml",
        ROOT / "experiments/deepseek_live_v1/frozen_protocol_manifest.yaml",
    ]
    for path in manifest_paths:
        content = path.read_text(encoding="utf-8")
        assert "created_at:" not in content
        assert "protocol_date:" in content


def test_pre_live_manifest_is_not_versioned_under_experiments():
    assert not (ROOT / "experiments/deepseek_live_v1/pre_live_manifest.yaml").exists()


def test_negative_compliance_verdict_instruction_is_safe():
    result = _audit_result(system_policy="Do not return a compliance verdict.")
    assert result["system_policy_safe"] is True
    assert result["historical_verdict_found"] is False
    assert result["prompt_safe"] is True


def test_negative_expected_outcome_instruction_is_safe():
    result = _audit_result(system_policy="Do not reveal any expected outcome.")
    assert result["prompt_safe"] is True
    assert result["historical_verdict_found"] is False


def test_negative_ground_truth_instruction_is_safe():
    result = _audit_result(system_policy="Do not include ground truth.")
    assert result["prompt_safe"] is True
    assert result["ground_truth_found"] is False


def test_negative_historical_result_instruction_is_safe():
    result = _audit_result(system_policy="Do not expose historical outcomes.")
    assert result["prompt_safe"] is True
    assert result["historical_verdict_found"] is False


def test_generic_word_verdict_is_not_a_leak():
    result = _audit_result(system_policy="The schema may mention verdict as a generic field label.")
    assert result["prompt_safe"] is True
    assert result["historical_verdict_found"] is False


def test_generic_word_outcome_is_not_a_leak():
    result = _audit_result(system_policy="Outcome is discussed only as a generic concept here.")
    assert result["prompt_safe"] is True
    assert result["historical_verdict_found"] is False


def test_system_policy_sensitive_assignment_is_unsafe():
    result = _audit_result(system_policy="expected_verdict = NONCOMPLIANT")
    assert result["system_policy_safe"] is False
    assert result["historical_verdict_found"] is True
    assert result["prompt_safe"] is False


@pytest.mark.parametrize(
    ("payload", "flag"),
    [
        ({"ground_truth": "SAFE"}, "ground_truth_found"),
        ({"expected_verdict": "COMPLIANT"}, "historical_verdict_found"),
        ({"historical_verdict": "SAFE"}, "historical_verdict_found"),
        ({"historical_metric": "1.0"}, "historical_metric_found"),
        ({"mutation_id": "cv_019"}, "mutation_id_found"),
        ({"internal_case_id": "p22_oscillator"}, "benchmark_name_found"),
        ({"benchmark_case_id": "smoke_p10_cutoff"}, "benchmark_name_found"),
    ],
)
def test_dynamic_sensitive_keys_are_unsafe(payload: dict, flag: str):
    result = _audit_result(sanitized_dynamic_payload=payload)
    assert result["dynamic_payload_safe"] is False
    assert result[flag] is True
    assert result["prompt_safe"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "TRUE_ACCEPT"},
        {"label": "FALSE_ACCEPT"},
        {"label": "FALSE_REJECT"},
        {"label": "SIMULABLE_COMPLIANT"},
    ],
)
def test_dynamic_sensitive_values_are_unsafe(payload: dict):
    result = _audit_result(sanitized_dynamic_payload=payload)
    assert result["dynamic_payload_safe"] is False
    assert result["historical_verdict_found"] is True


def test_dynamic_windows_absolute_path_is_unsafe():
    result = _audit_result(sanitized_dynamic_payload={"source_file_path": r"E:\my_organisation\Memoire Maruba\secret.txt"})
    assert result["dynamic_payload_safe"] is False
    assert result["local_path_found"] is True


def test_dynamic_unix_absolute_path_is_unsafe():
    result = _audit_result(sanitized_dynamic_payload={"source_file_path": "/home/admin/private.txt"})
    assert result["dynamic_payload_safe"] is False
    assert result["local_path_found"] is True


def test_relative_knowledge_path_is_safe():
    result = _audit_result(retrieved_knowledge={"rule_path": "knowledge/spec2testbench"})
    assert result["retrieved_knowledge_safe"] is True
    assert result["local_path_found"] is False


def test_generic_not_evaluated_rule_is_safe():
    result = _audit_result(retrieved_knowledge={"rule_id": "MISSING_METRIC_RETURNS_NOT_EVALUATED"})
    assert result["retrieved_knowledge_safe"] is True
    assert result["prompt_safe"] is True


def test_provider_smoke_payload_is_safe():
    result = audit_prompt_payload(audit_input=build_provider_smoke_prompt_audit_input())
    assert result["prompt_safe"] is True
    assert result["dynamic_payload_safe"] is True
    assert result["historical_verdict_found"] is False
    assert result["actual_sensitive_value_present"] is False
    assert result["negative_policy_instruction_only"] is True


def test_provider_smoke_payload_has_no_real_circuit():
    payload = build_provider_smoke_prompt_audit_input().sanitized_dynamic_payload
    serialized = json.dumps(payload, sort_keys=True)
    assert "analogcoder" not in serialized.lower()
    assert "p01_" not in serialized.lower()
    assert "p22_" not in serialized.lower()


def test_provider_smoke_payload_has_no_benchmark_identifier():
    result = audit_prompt_payload(audit_input=build_provider_smoke_prompt_audit_input())
    assert result["benchmark_name_found"] is False


def test_provider_smoke_payload_has_no_frozen_identifier():
    payload = build_provider_smoke_prompt_audit_input().sanitized_dynamic_payload
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "frozen" not in serialized


def test_provider_smoke_payload_has_no_historical_metric():
    result = audit_prompt_payload(audit_input=build_provider_smoke_prompt_audit_input())
    assert result["historical_metric_found"] is False


def test_provider_smoke_payload_has_no_local_path():
    result = audit_prompt_payload(audit_input=build_provider_smoke_prompt_audit_input())
    assert result["local_path_found"] is False


def test_unsafe_prompt_blocks_provider_transport(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_valid_model_discovery_artifact(tmp_path)
    monkeypatch.setattr(live_lib, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON", tmp_path / "provider_smoke_sanitized_payload.json")
    monkeypatch.setattr(
        live_lib,
        "build_provider_smoke_prompt_audit_input",
        lambda: PromptAuditInput(
            system_policy="expected_verdict = NONCOMPLIANT",
            retrieved_knowledge={},
            sanitized_dynamic_payload={},
            output_schema_instruction="{}",
            stage="provider_smoke",
            opaque_case_id="provider_smoke",
            trial_id="trial_01",
        ),
    )
    boundary_hits: list[dict] = []
    result, _, call_audit, _ = execute_provider_smoke_probe(
        dry_run=True,
        provider_boundary_probe=lambda event: boundary_hits.append(event),
    )
    assert boundary_hits == []
    assert result["provider_boundary_reached"] is False
    assert result["GO_PROVIDER_SMOKE"] == "NO_GO"
    assert call_audit["provider_call_performed"] is False


def test_safe_prompt_reaches_mocked_provider_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_valid_model_discovery_artifact(tmp_path)
    monkeypatch.setattr(live_lib, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON", tmp_path / "provider_smoke_sanitized_payload.json")
    boundary_hits: list[dict] = []
    result, _, call_audit, _ = execute_provider_smoke_probe(
        dry_run=True,
        provider_boundary_probe=lambda event: boundary_hits.append(event),
    )
    assert len(boundary_hits) == 1
    assert result["provider_boundary_reached"] is True
    assert result["GO_PROVIDER_SMOKE"] == "NOT_EXECUTED"
    assert call_audit["provider_call_performed"] is False


def test_dry_run_never_calls_real_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_valid_model_discovery_artifact(tmp_path)
    monkeypatch.setattr(live_lib, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON", tmp_path / "provider_smoke_sanitized_payload.json")
    monkeypatch.setattr(
        live_lib.DeepSeekProvider,
        "generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )
    result, _, _, _ = execute_provider_smoke_probe(dry_run=True)
    assert result["real_call_attempted"] is False
    assert result["chat_completion_calls_current_run"] == 0


def test_api_key_is_not_in_prompt():
    fake_key = _fake_secret_value()
    audit_input = build_provider_smoke_prompt_audit_input()
    serialized = json.dumps(
        {
            "system_policy": audit_input.system_policy,
            "retrieved_knowledge": audit_input.retrieved_knowledge,
            "sanitized_dynamic_payload": audit_input.sanitized_dynamic_payload,
            "output_schema_instruction": audit_input.output_schema_instruction,
        },
        sort_keys=True,
    )
    assert fake_key not in serialized


def test_api_key_is_not_in_audit_report():
    fake_key = _fake_secret_value()
    result = audit_prompt_payload(audit_input=build_provider_smoke_prompt_audit_input())
    assert fake_key not in json.dumps(result, sort_keys=True)


def test_sensitive_values_are_redacted_from_findings():
    result = _audit_result(
        sanitized_dynamic_payload={
            "expected_verdict": "TRUE_ACCEPT",
            "source_file_path": r"E:\very\secret\trace.txt",
        }
    )
    serialized = json.dumps(result, sort_keys=True)
    assert "TRUE_ACCEPT" not in serialized
    assert r"E:\very\secret\trace.txt" not in serialized
    assert result["prompt_safe"] is False


def test_provider_smoke_report_has_correct_title():
    lines = build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke"))
    assert lines[0] == "DEEPSEEK PROVIDER SMOKE — FINAL STATUS"


def test_provider_smoke_report_has_no_stub_scores():
    report = "\n".join(build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke")))
    assert "Stub TRUE_ACCEPT" not in report
    assert "Stub FALSE_ACCEPT" not in report


def test_provider_smoke_report_has_no_deterministic_scores():
    report = "\n".join(build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke")))
    assert "Deterministic TRUE_ACCEPT" not in report
    assert "Deterministic FALSE_REJECT" not in report


def test_provider_smoke_report_marks_campaign_comparison_not_applicable():
    report = "\n".join(build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke")))
    assert "Comparison metrics: NOT_APPLICABLE" in report


def test_preflight_report_keeps_preflight_title():
    lines = build_final_status_lines(_provider_smoke_summary(requested_stage="final_summary"))
    assert lines[0] == "PRE-LIVE BLOCKER RESOLUTION - FINAL STATUS"


def test_final_report_template_depends_on_stage():
    provider_lines = build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke"))
    preflight_lines = build_final_status_lines(_provider_smoke_summary(requested_stage="final_summary"))
    assert provider_lines[0] != preflight_lines[0]
