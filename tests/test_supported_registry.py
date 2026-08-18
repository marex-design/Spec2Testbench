from spec2testbench.domain.registry.supported_circuits import SUPPORTED_CIRCUITS
from spec2testbench.domain.registry.supported_tests import SUPPORTED_TESTS, count_supported_tests


def test_supported_circuits_count():
    assert len(SUPPORTED_CIRCUITS) == 35


def test_supported_tests_count():
    assert count_supported_tests() == 28


def test_supported_test_groups_count():
    assert len(SUPPORTED_TESTS) == 6


def test_required_test_groups_exist():
    required_groups = ["DC", "AC", "Transient", "Spectral", "Differential", "PVT"]

    for group in required_groups:
        assert group in SUPPORTED_TESTS