from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deepseek_live_lib as live_lib  # noqa: E402
from deepseek_live_lib import (  # noqa: E402
    PromptAuditInput,
    ProviderSmokeResponseV1,
    _scan_secrets_in_file,
    audit_env_example,
    audit_prompt_payload,
    build_deepseek_live_summary,
    build_final_status_lines,
    build_provider_smoke_expected_response,
    build_provider_smoke_prompt_audit_input,
    execute_provider_smoke_probe,
    freeze_invalidation_reason,
    invalidates_source_freeze,
    is_git_ignored,
    provider_smoke_expected_shape_payload,
    scan_text_for_secret_matches,
)
from spec2testbench.application.ports.llm_provider import LLMResponse  # noqa: E402
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan as DomainTestbenchPlan  # noqa: E402


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
            "artifact_loaded_before_call": True,
            "live_discovery_performed": False,
            "artifact_refreshed_after_call": False,
            "artifact_reused_without_network": True,
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
            "transport_response_received": False,
            "content_received": False,
            "json_parsed": False,
            "chat_completion_calls_current_run": 0,
            "http_status": None,
            "http_status_detail": "HTTP_STATUS_NOT_EXPOSED_BY_CURRENT_CLIENT_PATH",
            "json_valid": None,
            "schema_valid": None,
            "provider_failure": "",
            "provider_failure_code": "",
            "provider_failure_stage": "",
            "provider_exception_class": "",
            "GO_PROVIDER_TRANSPORT": "NOT_EXECUTED",
            "GO_PROVIDER_JSON": "NOT_EXECUTED",
            "GO_PROVIDER_SMOKE_SCHEMA": "NOT_EXECUTED",
        },
        "network_accounting": {
            "chat_completion_calls_current_run": 0,
            "current_run_network_calls": 0,
            "campaign_known_network_calls": 1,
            "campaign_chat_completion_calls": 0,
            "historical_dry_run_records": 1,
        },
        "worktree": {
            "branch": "test",
            "git_commit": "abc123",
            "scientific_worktree_clean": False,
            "source_freeze_modified": False,
            "original_benchmarks_modified": False,
            "frozen_v3_modified": False,
            "knowledge_modified": False,
        },
        "current_blockers": ["CODE_FREEZE"],
        "historical_resolved_issues": [{"code": "RESOLVED_PROMPT_AUDIT_FALSE_POSITIVE"}],
        "ready": {
            "ready_for_new_freeze_commit": False,
            "ready_for_real_provider_smoke": False,
            "ready_for_provider_smoke_retry_after_fix": False,
            "ready_for_single_cases": False,
            "ready_for_seven_use_cases": False,
            "ready_for_frozen": False,
            "ready_for_full_campaign": False,
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


def _configure_tmp_campaign_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    results_dir = tmp_path / "results"
    reports_dir = tmp_path / "reports"
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(live_lib, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(live_lib, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(live_lib, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(live_lib, "RUN_RESULTS_DIR", results_dir / "runs")
    monkeypatch.setattr(live_lib, "RUN_REPORTS_DIR", reports_dir / "runs")
    monkeypatch.setattr(live_lib, "PROMPT_AUDIT_CSV", results_dir / "prompt_leakage_audit.csv")
    monkeypatch.setattr(live_lib, "LIVE_CALL_AUDIT_CSV", results_dir / "live_call_audit.csv")
    monkeypatch.setattr(live_lib, "LIVE_BUDGET_CSV", results_dir / "live_budget_tracking.csv")
    monkeypatch.setattr(live_lib, "FINAL_SUMMARY_JSON", results_dir / "deepseek_live_campaign_summary.json")
    monkeypatch.setattr(live_lib, "FINAL_STATUS_MD", reports_dir / "final_status.md")
    monkeypatch.setattr(live_lib, "OFFLINE_TEST_MATRIX_JSON", results_dir / "offline_test_matrix.json")
    monkeypatch.setattr(live_lib, "ENV_EXAMPLE_AUDIT_JSON", results_dir / "env_example_audit.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SANITIZED_PAYLOAD_JSON", results_dir / "provider_smoke_sanitized_payload.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_EXPECTED_SHAPE_JSON", results_dir / "provider_smoke_expected_shape.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_JSON_SCHEMA_JSON", results_dir / "provider_smoke_json_schema.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_VALIDATION_INVENTORY_CSV", results_dir / "provider_smoke_validation_inventory.csv")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_VALIDATION_INVENTORY_MD", reports_dir / "provider_smoke_validation_inventory.md")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SCHEMA_ERRORS_JSON", results_dir / "provider_smoke_schema_errors.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SCHEMA_ERRORS_CSV", results_dir / "provider_smoke_schema_errors.csv")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_SCHEMA_ERRORS_MD", reports_dir / "provider_smoke_schema_errors.md")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_ROOT_CAUSE_JSON", results_dir / "provider_smoke_root_cause.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_ROOT_CAUSE_MD", reports_dir / "provider_smoke_root_cause.md")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_BLOCKER_ANALYSIS_JSON", results_dir / "provider_smoke_blocker_analysis.json")
    monkeypatch.setattr(live_lib, "PROVIDER_SMOKE_BLOCKER_ANALYSIS_MD", reports_dir / "provider_smoke_blocker_analysis.md")
    return results_dir, reports_dir, artifacts_dir


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


def test_provider_smoke_response_v1_schema():
    payload = provider_smoke_expected_shape_payload()
    parsed = ProviderSmokeResponseV1.model_validate(payload)
    assert parsed.smoke_id == "provider_smoke"
    assert parsed.status == "READY"


def test_provider_smoke_prompt_example_validates():
    expected = build_provider_smoke_expected_response()
    assert ProviderSmokeResponseV1.model_validate(expected.model_dump(mode="json")).status == "READY"


def test_provider_smoke_does_not_claim_testbench_plan_v2_validation():
    audit_input = build_provider_smoke_prompt_audit_input()
    serialized = json.dumps(audit_input.sanitized_dynamic_payload, sort_keys=True)
    assert "TestbenchPlanV2" not in serialized
    assert "TestbenchPlanV2" not in audit_input.output_schema_instruction
    assert "ProviderSmokeResponseV1" in audit_input.output_schema_instruction


def test_production_testbench_plan_schema_is_not_weakened():
    with pytest.raises(ValidationError):
        DomainTestbenchPlan.model_validate(provider_smoke_expected_shape_payload())


def test_provider_smoke_live_schema_error_is_serialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    results_dir, _, _ = _configure_tmp_campaign_paths(monkeypatch, tmp_path)
    _write_valid_model_discovery_artifact(results_dir)
    monkeypatch.setattr(live_lib, "current_run_id", lambda: "run-schema-error")

    class FakeProvider:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, _request):
            return LLMResponse(
                content='{"unexpected": true}',
                provider="deepseek",
                model="deepseek-v4-flash",
                finish_reason="stop",
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
                latency_seconds=0.5,
                raw_metadata={
                    "id": "resp_123",
                    "created": 123,
                    "http_status": 200,
                    "http_status_observation": 200,
                    "request_id": "req_123",
                    "response_headers": {"x-request-id": "req_123"},
                    "attempts": [{"attempt_number": 1, "http_status": 200, "final_status": "SUCCESS"}],
                },
            )

    monkeypatch.setattr(live_lib, "DeepSeekProvider", FakeProvider)
    monkeypatch.setattr(
        live_lib.DeepSeekProviderConfig,
        "from_env",
        classmethod(lambda cls: cls(api_key="test-key", model="deepseek-v4-flash")),
    )

    result, _, call_audit, _ = execute_provider_smoke_probe(dry_run=False)

    assert result["transport_response_received"] is True
    assert result["json_valid"] is True
    assert result["schema_valid"] is False
    assert result["provider_failure_code"] == "SCHEMA_ERROR"
    assert result["provider_failure_stage"] == "SCHEMA_VALIDATION"
    assert result["GO_PROVIDER_TRANSPORT"] == "PASS"
    assert result["GO_PROVIDER_JSON"] == "PASS"
    assert result["GO_PROVIDER_SMOKE_SCHEMA"] == "NO_GO"
    assert result["GO_PROVIDER_SMOKE"] == "NO_GO"
    assert call_audit["provider_status"] == "SCHEMA_ERROR"
    error_report = json.loads((tmp_path / "artifacts" / "provider_smoke" / "run-schema-error" / "schema_validation_errors.json").read_text(encoding="utf-8"))
    assert error_report
    assert {row["root_cause_category"] for row in error_report} >= {"MISSING_REQUIRED_FIELD", "EXTRA_FORBIDDEN_FIELD"}


def test_provider_smoke_summary_filters_live_call_audit_by_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    results_dir, reports_dir, _ = _configure_tmp_campaign_paths(monkeypatch, tmp_path)
    run_id = "run-current"
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "provider_smoke.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "provider_smoke_prompt_safe": True,
                "provider_boundary_reached": True,
                "real_call_attempted": True,
                "real_call_completed": False,
                "transport_response_received": True,
                "content_received": True,
                "json_parsed": True,
                "chat_completion_calls_current_run": 1,
                "json_valid": True,
                "schema_valid": False,
                "provider_failure": "SCHEMA_ERROR",
                "provider_failure_code": "SCHEMA_ERROR",
                "provider_failure_stage": "SCHEMA_VALIDATION",
                "provider_exception_class": "ValidationError",
                "GO_PROVIDER_TRANSPORT": "PASS",
                "GO_PROVIDER_JSON": "PASS",
                "GO_PROVIDER_SMOKE_SCHEMA": "NO_GO",
                "GO_PROVIDER_SMOKE": "NO_GO",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (results_dir / "pre_live_manifest.json").write_text(json.dumps({"go_code_freeze": "PASS"}), encoding="utf-8")
    (results_dir / "secret_audit.json").write_text(json.dumps({"go_secret_safety": "PASS"}), encoding="utf-8")
    (results_dir / "env_example_audit.json").write_text(json.dumps({}), encoding="utf-8")
    (results_dir / "offline_test_matrix.json").write_text(
        json.dumps({"pytest": {"passed": 2, "failed": 0, "skipped": 0}, "ngspice_integration_passed": True, "pyspice_disabled_passed": True, "live_tests_executed": False}),
        encoding="utf-8",
    )
    live_lib.write_csv(
        results_dir / "live_call_audit.csv",
        [
            {"stage": "model_discovery", "run_id": run_id, "provider_call_performed": True, "execution_mode": "LIVE"},
            {"stage": "provider_smoke", "run_id": run_id, "provider_call_performed": True, "execution_mode": "LIVE"},
            {"stage": "provider_smoke", "run_id": "old-live", "provider_call_performed": True, "execution_mode": "LIVE"},
            {"stage": "provider_smoke", "run_id": "old-dry", "provider_call_performed": False, "execution_mode": "DRY_RUN"},
        ],
    )
    live_lib.write_csv(
        results_dir / "live_budget_tracking.csv",
        [
            {"run_id": run_id, "prompt_tokens": 2111, "completion_tokens": 554, "total_tokens": 2665},
        ],
    )
    live_lib.write_csv(
        results_dir / "prompt_leakage_audit.csv",
        [
            {
                "run_id": run_id,
                "prompt_safe": True,
                "system_policy_safe": True,
                "retrieved_knowledge_safe": True,
                "dynamic_payload_safe": True,
                "schema_instruction_safe": True,
                "negative_policy_instruction_only": True,
                "actual_sensitive_value_present": False,
            },
            {
                "run_id": "old-live",
                "prompt_safe": False,
                "system_policy_safe": False,
                "retrieved_knowledge_safe": False,
                "dynamic_payload_safe": False,
                "schema_instruction_safe": False,
                "negative_policy_instruction_only": False,
                "actual_sensitive_value_present": False,
            },
        ],
    )
    monkeypatch.setattr(
        live_lib,
        "load_model_discovery_reuse_state",
        lambda: {
            "valid": True,
            "configured_model": "deepseek-v4-flash",
            "configured_model_available": True,
            "artifact_timestamp": "2026-07-23T14:45:19+00:00",
            "artifact_response_sha256": "abc123",
            "models_returned": 2,
            "http_status": 200,
            "base_url": "https://api.deepseek.com",
            "model_ids": ["deepseek-v4-flash"],
            "live_confirmed": True,
            "reused_from_artifact": True,
            "performed_current_run": False,
            "errors": [],
        },
    )
    monkeypatch.setattr(
        live_lib,
        "collect_git_state",
        lambda: {
            "branch": "test",
            "git_commit": "abc123",
            "source_freeze_modified": False,
            "original_benchmark_files_modified": False,
            "knowledge_files_modified": False,
            "frozen_v3_files_modified": False,
        },
    )
    monkeypatch.setattr(live_lib, "build_pre_commit_inventory", lambda: {"rows": [], "counts": {}, "scientific_worktree_clean": True})
    monkeypatch.setattr(live_lib, "build_clean_commit_plan", lambda: {"FILES_TO_COMMIT": [], "FILES_TO_EXCLUDE": []})
    monkeypatch.setattr(
        live_lib,
        "build_provider_smoke_blocker_analysis",
        lambda: {"root_cause": "historical false positive", "provider_called": True, "chat_completion_called": True},
    )
    monkeypatch.setattr(live_lib, "live_guard_state", lambda require_full_campaign: {"allowed": False, "status": "FULL_CAMPAIGN_APPROVAL_MISSING"})

    summary = build_deepseek_live_summary(requested_stage="final_summary", execution_mode="LIVE", run_id=run_id)

    assert summary["network_accounting"]["current_run_network_calls"] == 2
    assert summary["network_accounting"]["chat_completion_calls_current_run"] == 1
    assert summary["network_accounting"]["historical_dry_run_records"] == 1
    assert summary["current_blockers"] == ["SCHEMA_ERROR"]
    assert summary["historical_resolved_issues"][0]["code"] == "RESOLVED_PROMPT_AUDIT_FALSE_POSITIVE"
    assert summary["ready"]["ready_for_real_provider_smoke"] is False
    assert summary["ready"]["ready_for_provider_smoke_retry_after_fix"] is True
    assert summary["ready"]["final_decision"] == "FIX_PROVIDER_SMOKE_SCHEMA_THEN_RETRY"
    assert (results_dir / "runs" / run_id / "deepseek_live_campaign_summary.json").exists()
    assert reports_dir.joinpath("final_status.md").exists()


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


def test_provider_smoke_report_is_valid_utf8():
    report = "\n".join(build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke")))
    assert report.encode("utf-8").decode("utf-8") == report


def test_provider_smoke_report_contains_unicode_em_dash():
    lines = build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke"))
    assert lines[0] == "DEEPSEEK PROVIDER SMOKE — FINAL STATUS"


def test_provider_smoke_report_has_no_mojibake():
    report = "\n".join(build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke")))
    assert "Ã" not in report
    assert "â" not in report


def test_preflight_report_keeps_preflight_title():
    lines = build_final_status_lines(_provider_smoke_summary(requested_stage="final_summary"))
    assert lines[0] == "PRE-LIVE BLOCKER RESOLUTION - FINAL STATUS"


def test_final_report_template_depends_on_stage():
    provider_lines = build_final_status_lines(_provider_smoke_summary(requested_stage="provider_smoke"))
    preflight_lines = build_final_status_lines(_provider_smoke_summary(requested_stage="final_summary"))
    assert provider_lines[0] != preflight_lines[0]
