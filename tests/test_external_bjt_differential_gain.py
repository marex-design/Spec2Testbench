import numpy as np
import pytest

from spec2testbench.infrastructure.simulator.result_backends import (
    compute_differential_gain_db,
)


def test_differential_gain_db_reference_frequency():
    """
    Deterministic unit test for the post-freeze external
    differential-gain metric.

    WRDATA columns:
        0 frequency
        1 Re(Vin+)
        2 Im(Vin+)
        3 Re(Vin-)
        4 Im(Vin-)
        5 Re(Vout)
        6 Im(Vout)
    """

    vid = 10e-3
    expected_gain_db = 36.3203
    gain_linear = 10 ** (expected_gain_db / 20.0)

    data = np.array([
        [
            1000.0,
            +vid / 2.0,
            0.0,
            -vid / 2.0,
            0.0,
            -(gain_linear * vid),
            0.0,
        ]
    ])

    request = {
        "reference_frequency_hz": 1000.0,
        "in_pos_real_column": 1,
        "in_pos_imag_column": 2,
        "in_neg_real_column": 3,
        "in_neg_imag_column": 4,
        "out_real_column": 5,
        "out_imag_column": 6,
    }

    value = compute_differential_gain_db(
        {"data": data},
        request,
    )

    assert value == pytest.approx(
        expected_gain_db,
        abs=1e-6,
    )
