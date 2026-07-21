from __future__ import annotations

import math

from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor


def test_metric_extractor_frequency_with_real_oscillation():
    extractor = MetricExtractor()
    time = [index * 1e-4 for index in range(1000)]
    vout = [math.sin(2.0 * math.pi * 50.0 * sample) for sample in time]

    value = extractor.extract(
        {
            "oscillation_validation": {"status": "VALID_OSCILLATION"},
            "transient": {"time": time, "vout": vout},
        },
        "oscillator_frequency",
    )

    assert value is not None
    assert abs(value - 50.0) < 2.0


def test_metric_extractor_frequency_without_valid_oscillation():
    extractor = MetricExtractor()
    time = [index * 1e-4 for index in range(1000)]
    vout = [math.sin(2.0 * math.pi * 50.0 * sample) for sample in time]

    value = extractor.extract(
        {
            "oscillation_validation": {"status": "AMPLITUDE_TOO_LOW"},
            "transient": {"time": time, "vout": vout},
        },
        "oscillator_frequency",
    )

    assert value is None


def test_metric_extractor_hysteresis_width_with_two_transitions():
    extractor = MetricExtractor()
    results = {
        "transient": {
            "time": [0.0, 1.0, 2.0, 3.0, 4.0],
            "vin": [0.0, 1.2, 2.8, 2.4, 1.5],
            "vout": [0.0, 0.0, 5.0, 5.0, 0.0],
        }
    }

    value = extractor.extract(results, "hysteresis_width")

    assert value is not None
    assert abs(value - 1.3) < 1e-12


def test_metric_extractor_hysteresis_width_without_transition():
    extractor = MetricExtractor()
    results = {
        "transient": {
            "time": [0.0, 1.0, 2.0, 3.0],
            "vin": [0.0, 0.5, 1.0, 1.5],
            "vout": [0.0, 0.0, 0.0, 0.0],
        }
    }

    assert extractor.extract(results, "hysteresis_width") is None
