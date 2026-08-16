from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from spec2testbench.infrastructure.waveform_checker.waveform_plotter import WaveformPlotter


def test_scale_time_axis_uses_microseconds_for_short_transients(tmp_path: Path) -> None:
    plotter = WaveformPlotter(output_dir=tmp_path)

    scaled, scale, label = plotter._scale_time_axis(np.array([0.0, 2e-6]))

    assert label == "Time (us)"
    assert scale == pytest.approx(1e-6)
    assert scaled[-1] == pytest.approx(2.0)


def test_to_db_clips_null_spectrum_to_practical_floor(tmp_path: Path) -> None:
    plotter = WaveformPlotter(output_dir=tmp_path)

    db_values = plotter._to_db(np.zeros(4))

    assert np.all(db_values == pytest.approx(plotter.DB_FLOOR_DB))


def test_apply_transient_ylim_expands_flat_positive_signal(tmp_path: Path) -> None:
    plotter = WaveformPlotter(output_dir=tmp_path)
    fig, ax = plt.subplots()

    try:
        plotter._apply_transient_ylim(ax, [np.full(64, 2.5)])
        lower, upper = ax.get_ylim()
    finally:
        plt.close(fig)

    assert lower == pytest.approx(0.0)
    assert upper == pytest.approx(5.0)


def test_add_branding_injects_spec2testbench_text(tmp_path: Path) -> None:
    plotter = WaveformPlotter(output_dir=tmp_path)
    fig = plt.figure()

    try:
        plotter._add_branding(fig)
        assert any(text.get_text() == plotter.BRAND_TEXT for text in fig.texts)
    finally:
        plt.close(fig)


def test_plot_fft_skips_dc_bin_and_saves_png(tmp_path: Path) -> None:
    plotter = WaveformPlotter(output_dir=tmp_path)

    image_path = plotter.plot_fft(
        frequency=np.array([0.0, 1e3, 1e4]),
        spectrum=np.array([0.0, 1.0, 0.1]),
        title="FFT",
        filename="fft_test.png",
        save=True,
    )

    assert image_path == tmp_path / "fft_test.png"
    assert image_path.exists()
