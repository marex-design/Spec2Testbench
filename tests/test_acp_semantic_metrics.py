import math

import pytest

from spec2testbench.infrastructure.spec_checker.metric_extractor import MetricExtractor


@pytest.fixture
def ex():
    return MetricExtractor()


def test_lowpass_and_highpass_semantic_metrics(ex):
    low = {"ac": {"frequency": [1, 10, 100, 1000], "magnitude": [1.0, 0.8, 0.2, 0.05]}}
    assert ex.extract(low, "lowpass_attenuation_db") > 20
    assert ex.extract(low, "lowpass_monotonicity_percent") == 100.0

    high = {"ac": {"frequency": [1, 10, 100, 1000], "magnitude": [0.05, 0.2, 0.8, 1.0]}}
    assert ex.extract(high, "highpass_attenuation_db") > 20
    assert ex.extract(high, "highpass_monotonicity_percent") == 100.0


def test_bandpass_and_bandstop_semantic_metrics(ex):
    bp = {"ac": {"frequency": [1, 2, 3, 4, 5], "magnitude": [0.1, 0.2, 1.0, 0.2, 0.1]}}
    assert ex.extract(bp, "bandpass_peak_separation_db") > 10

    bs = {"ac": {"frequency": [1, 2, 3, 4, 5], "magnitude": [1.0, 0.8, 0.05, 0.8, 1.0]}}
    assert ex.extract(bs, "bandstop_notch_depth_db") > 10


def test_inverter_and_comparator_metrics(ex):
    inv = {"dc": {"vin": [0, 1, 2, 3, 4, 5], "vout_values": [5, 4.9, 4.5, 0.5, 0.1, 0.0]}}
    assert ex.extract(inv, "inverter_low_input_output_v") == pytest.approx(5.0)
    assert ex.extract(inv, "inverter_high_input_output_v") == pytest.approx(0.0)

    cmp_data = {"dc": {"vin": [0, 1, 2, 3, 4, 5], "vout_values": [0, 0, 0.1, 4.9, 5, 5]}}
    assert ex.extract(cmp_data, "comparator_output_separation_v") > 4
    assert ex.extract(cmp_data, "comparator_monotonicity_percent") == 100.0


def test_current_stability_delta(ex):
    data = {"dc": {"current_waveforms": {"Vdd": [1.00e-3, 1.0002e-3, 0.9999e-3]}}}
    assert ex.extract(data, "current_stability_delta_a") == pytest.approx(3e-7)


def test_output_swing(ex):
    data = {"transient": {"time": [0, 1, 2], "vout": [0.2, 4.8, 0.3]}}
    assert ex.extract(data, "output_swing_v") == pytest.approx(4.6)


def test_oscillation_cycle_count_and_period_cv(ex):
    # Five clean rising mean crossings in the latter half -> stable periods.
    t = [i * 0.01 for i in range(200)]
    y = [math.sin(2 * math.pi * 5 * x) for x in t]
    data = {"transient": {"time": t, "vout": y}}
    cycles = ex.extract(data, "oscillation_cycle_count")
    cv = ex.extract(data, "oscillation_period_cv")
    assert cycles is not None and cycles >= 4
    assert cv is not None and cv < 0.05
