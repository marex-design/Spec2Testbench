from __future__ import annotations

from pathlib import Path

from scripts.run_deepseek_testbench_campaign import (
    build_deterministic_use_case_row,
    classification_from_ground_truth,
    load_frozen_v3_reference_rows,
    provider_mode_for_run,
    resolve_manifest_cases,
    run_deterministic_case,
    scientific_llm_evidence,
)
from spec2testbench.application.services.llm_cache import LLMCacheKey
from spec2testbench.domain.value_objects.llm_status import GenerationMode


def test_llm_campaign_deterministic_mode_matches_frozen_v3_case_by_case():
    manifest = Path("experiments/llm_deepseek/frozen_manifest.yaml")
    cases = resolve_manifest_cases(manifest)
    historical_rows = load_frozen_v3_reference_rows()

    assert len(cases) == 16
    for case in cases:
        specification, deterministic = run_deterministic_case(
            case,
            timeout=60,
            deterministic_source="frozen_v3_reference",
        )
        row = build_deterministic_use_case_row(
            run_id="test_reference",
            case=case,
            specification=specification,
            deterministic=deterministic,
        )
        historical = historical_rows[case.case_id]
        assert row["generation_mode"] == GenerationMode.DETERMINISTIC.value
        assert row["compliance_status"] == historical["compliance_status"]
        assert row["evaluation_outcome"] == historical["evaluation_outcome"]
        assert row["measurement_backend"] == historical["measurement_backend"]
        assert str(row["metric_threshold"]) == historical["threshold"]
        assert str(row["metric_operator"]) == historical["operator"]


def test_ground_truth_mapping_classification_covers_all_outcomes():
    assert classification_from_ground_truth("GROUND_TRUTH_COMPLIANT", "PASS") == "TRUE_ACCEPT"
    assert classification_from_ground_truth("GROUND_TRUTH_NONCOMPLIANT", "FAIL") == "TRUE_DETECTION"
    assert classification_from_ground_truth("GROUND_TRUTH_COMPLIANT", "FAIL") == "FALSE_REJECT"
    assert classification_from_ground_truth("GROUND_TRUTH_NONCOMPLIANT", "PASS") == "FALSE_ACCEPT"
    assert classification_from_ground_truth("GROUND_TRUTH_COMPLIANT", "NOT_EVALUATED") == "UNEVALUATED"


def test_trial_cache_key_is_unique_per_trial():
    base = dict(
        case_id="case",
        mode="deepseek_refinement",
        provider="deepseek_stub",
        model="deepseek-stub-v1",
        prompt_sha256="prompt",
        specification_sha256="spec",
        netlist_sha256="netlist",
        capability_registry_sha256="registry",
        temperature=0.1,
        max_tokens=512,
    )
    key_one = LLMCacheKey(trial_id="trial_01", **base)
    key_two = LLMCacheKey(trial_id="trial_02", **base)

    assert key_one.digest() != key_two.digest()


def test_stub_provider_is_not_scientific_evidence():
    provider_mode = provider_mode_for_run("stub", {"provider": "deepseek_stub"})
    assert provider_mode == "STUB"
    assert scientific_llm_evidence(provider_mode) is False
