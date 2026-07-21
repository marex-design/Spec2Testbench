from pathlib import Path

import pytest

from spec2testbench.infrastructure.simulator.result_backends import (
    compute_amplitude_pp,
    compute_cutoff_frequency,
    compute_dc_gain_db,
    compute_frequency_hz,
    compute_hysteresis_width,
    compute_switching_threshold_falling,
    compute_switching_threshold_rising,
    interpolate_crossing,
    parse_measure_file,
    parse_wrdata_file,
)


def test_parse_measure_valid(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text("dc_gain_db = 1.234e+01\n", encoding="utf-8")
    parsed = parse_measure_file(path)
    assert parsed["dc_gain_db"]["value"] == 12.34


def test_parse_measure_negative_zero_and_failed(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text("offset = -1.0e-03\nzero_metric = 0\nmissing = failed\n", encoding="utf-8")
    parsed = parse_measure_file(path)
    assert parsed["offset"]["value"] == -1.0e-03
    assert parsed["zero_metric"]["value"] == 0.0
    assert parsed["missing"]["status"] == "NOT_EVALUATED"


def test_parse_measure_not_found_nan_and_inf(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text(
        "delay = not found\nnan_metric = NaN\ninf_metric = Inf\n",
        encoding="utf-8",
    )
    parsed = parse_measure_file(path)
    assert parsed["delay"] == {"value": None, "status": "NOT_EVALUATED", "error": "NGSPICE_MEASURE_FAILED"}
    assert parsed["nan_metric"] == {"value": None, "status": "NOT_EVALUATED", "error": "NON_FINITE_MEASURE"}
    assert parsed["inf_metric"] == {"value": None, "status": "NOT_EVALUATED", "error": "NON_FINITE_MEASURE"}


def test_parse_measure_empty_file_is_not_a_zero(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text("", encoding="utf-8")
    assert parse_measure_file(path) == {}


def test_parse_measure_unparsable_text_is_not_a_zero(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text("delay = invalid value\n", encoding="utf-8")
    parsed = parse_measure_file(path)
    assert parsed["delay"] == {"value": None, "status": "NOT_EVALUATED", "error": "UNPARSABLE_MEASURE"}


def test_parse_measure_with_trig_targ_suffix(tmp_path):
    path = tmp_path / "measures.txt"
    path.write_text("propagation_delay =  -7.830496e-08 targ=  4.216950e-07 trig=  5.000000e-07\n", encoding="utf-8")
    parsed = parse_measure_file(path)
    assert parsed["propagation_delay"]["value"] == -7.830496e-08


def test_parse_measure_missing_file():
    assert parse_measure_file(Path("does_not_exist.txt")) == {}


def test_parse_wrdata_valid(tmp_path):
    path = tmp_path / "vectors.dat"
    path.write_text("0 0 1\n1 1 2\n", encoding="utf-8")
    parsed = parse_wrdata_file(path)
    assert parsed["data"].shape == (2, 3)


def test_parse_wrdata_empty_nan_inf_and_bad_columns(tmp_path):
    empty = tmp_path / "empty.dat"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_wrdata_file(empty)

    nanf = tmp_path / "nan.dat"
    nanf.write_text("0 nan\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_wrdata_file(nanf)

    bad = tmp_path / "bad.dat"
    bad.write_text("0 1\n1 2 3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_wrdata_file(bad)


def test_interpolation_and_switching_thresholds():
    parsed = {"data": __import__("numpy").array([
        [0.0, 1.0, 0.0],
        [1.0, 3.0, 5.0],
        [2.0, 2.0, 5.0],
        [3.0, 1.0, 0.0],
    ])}
    assert interpolate_crossing(0.0, 0.0, 1.0, 5.0, 2.5) == 0.5
    assert compute_switching_threshold_rising(parsed, {"time_column": 0, "vin_column": 1, "vout_column": 2, "output_threshold": 2.5}) == 2.0
    assert compute_switching_threshold_falling(parsed, {"time_column": 0, "vin_column": 1, "vout_column": 2, "output_threshold": 2.5}) == 1.5
    assert compute_hysteresis_width(parsed, {"time_column": 0, "vin_column": 1, "vout_column": 2, "output_threshold": 2.5}) == 0.5


def test_frequency_and_amplitude_pp():
    import numpy as np

    time = np.linspace(0.0, 4.0, 9)
    vout = np.array([0.0, 1.0, 0.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0])
    parsed = {"data": np.column_stack([time, vout])}
    assert compute_amplitude_pp(parsed, {"value_column": 1}) == 2.0
    assert round(compute_frequency_hz(parsed, {"time_column": 0, "value_column": 1}), 6) == 0.5


def test_gain_and_cutoff():
    import numpy as np

    freq = np.array([1.0, 10.0, 100.0, 1000.0])
    ratio = np.array([10.0, 10.0, 7.07106781, 1.0])
    parsed = {"data": np.column_stack([freq, ratio, np.zeros_like(ratio), np.ones_like(ratio), np.zeros_like(ratio)])}
    assert round(compute_dc_gain_db(parsed, {}), 6) == 20.0
    assert round(compute_cutoff_frequency(parsed, {}), 3) == 100.0


def test_gain_uses_transfer_ratio_not_absolute_output_for_unity_input():
    import math
    import numpy as np

    parsed = {"data": np.array([[1.0, 10.0, 0.0, 1.0, 0.0]])}
    gain_db = compute_dc_gain_db(parsed, {})
    vout_dbv = 20.0 * math.log10(10.0)
    assert round(gain_db, 6) == 20.0
    assert round(vout_dbv, 6) == 20.0


def test_gain_with_ac_nanovolt_input_stays_at_20db_while_output_dbv_is_negative():
    import math
    import numpy as np

    parsed = {"data": np.array([[1.0, 1e-8, 0.0, 1e-9, 0.0]])}
    gain_db = compute_dc_gain_db(parsed, {})
    vout_dbv = 20.0 * math.log10(1e-8)
    assert round(gain_db, 6) == 20.0
    assert round(vout_dbv, 6) == -160.0


def test_gain_unit_ratio_with_ac_nanovolt_input_is_zero_db():
    import math
    import numpy as np

    parsed = {"data": np.array([[1.0, 1e-9, 0.0, 1e-9, 0.0]])}
    gain_db = compute_dc_gain_db(parsed, {})
    vout_dbv = 20.0 * math.log10(1e-9)
    assert round(gain_db, 6) == 0.0
    assert round(vout_dbv, 6) == -180.0


def test_gain_with_zero_input_is_not_evaluated():
    import numpy as np

    parsed = {"data": np.array([[1.0, 1.0, 0.0, 0.0, 0.0]])}
    with pytest.raises(ValueError):
        compute_dc_gain_db(parsed, {})


def test_gain_inversion_preserves_magnitude():
    import numpy as np

    parsed = {"data": np.array([[1.0, -10.0, 0.0, 1.0, 0.0]])}
    assert round(compute_dc_gain_db(parsed, {}), 6) == 20.0
