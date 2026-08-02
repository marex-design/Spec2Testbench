from pathlib import Path

import yaml

from spec2testbench.application.services.llm_metric_registry import get_metric_definition
from spec2testbench.application.verification_tests import VerificationApplicabilityEngine
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.verification_tests import VerificationApplicabilityStatus, VerificationTestId, get_verification_test_registry
from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_BENCH_DIR = ROOT / "benchmark" / "reference_28"
REFERENCE_SPEC_DIR = ROOT / "examples" / "reference_28_specs"


def test_reference_28_suite_covers_all_final_tests():
    spec_paths = sorted(REFERENCE_SPEC_DIR.glob("*.yaml"))

    assert len(spec_paths) == 28
    assert (REFERENCE_BENCH_DIR / "manifest.csv").exists()
    assert len(list(REFERENCE_BENCH_DIR.glob("*.cir"))) == 28

    engine = VerificationApplicabilityEngine()
    covered = set()

    for spec_path in spec_paths:
        specification = Specification.from_dict(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
        included_tests = tuple(specification.verification.include_tests)

        assert len(included_tests) == 1

        test_id = VerificationTestId(included_tests[0])
        covered.add(test_id)

        evaluation = engine.evaluate(specification, test_id)
        assert evaluation.status == VerificationApplicabilityStatus.REQUIRED

    assert covered == set(VerificationTestId)


def test_all_registry_metrics_are_supported_by_framework():
    extractor = MetricExtractor()

    for definition in get_verification_test_registry():
        for metric_name in definition.metric_definitions:
            assert extractor.supports_metric(metric_name), metric_name
            assert get_metric_definition(metric_name) is not None, metric_name
