# spec2testbench/infrastructure/waveform_checker/waveform_plotter.py

"""
WaveformPlotter - Generates PNG images from simulation data.
"""

import math
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Matplotlib configuration for clean rendering
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["figure.dpi"] = 100
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["font.size"] = 10
plt.rcParams["lines.linewidth"] = 1.5

logger = logging.getLogger(__name__)


class WaveformPlotter:
    """
    Generate PNG waveform images from simulation data.

    Supports:
    - Transient waveforms (time vs voltage)
    - AC frequency response (Bode plots)
    - FFT spectra
    - Eye diagrams
    """

    BRAND_TEXT = "Spec2Testbench"
    BRAND_COLOR = "#0B3D91"
    DB_FLOOR_DB = -180.0

    def __init__(self, output_dir: Path = Path("./output/waveforms")):
        """
        Initialize the waveform plotter.

        Args:
            output_dir: Directory to save generated images
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _finite_array(values: np.ndarray) -> np.ndarray:
        """Return a 1D array containing only finite float values."""
        array = np.asarray(values, dtype=float).ravel()
        return array[np.isfinite(array)]

    @staticmethod
    def _positive_frequency_mask(frequency: np.ndarray) -> np.ndarray:
        """Keep only strictly positive finite frequencies for log-scale plots."""
        frequency_array = np.asarray(frequency, dtype=float)
        return np.isfinite(frequency_array) & (frequency_array > 0.0)

    def _scale_time_axis(self, time: np.ndarray) -> Tuple[np.ndarray, float, str]:
        """Scale a time axis to engineering units and return the matching label."""
        time_array = np.asarray(time, dtype=float)
        finite_time = self._finite_array(time_array)
        reference = float(np.max(np.abs(finite_time))) if finite_time.size else 0.0

        if reference >= 1.0:
            scale, unit = 1.0, "s"
        elif reference >= 1e-3:
            scale, unit = 1e-3, "ms"
        elif reference >= 1e-6:
            scale, unit = 1e-6, "us"
        elif reference >= 1e-9:
            scale, unit = 1e-9, "ns"
        else:
            scale, unit = 1e-12, "ps"

        scaled = time_array / scale if scale else time_array
        return scaled, scale, f"Time ({unit})"

    def _to_db(self, magnitude: np.ndarray) -> np.ndarray:
        """Convert a linear magnitude to dB with a practical visual floor."""
        floor_linear = 10 ** (self.DB_FLOOR_DB / 20.0)
        array = np.asarray(magnitude, dtype=float)
        safe = np.abs(array)
        safe = np.where(np.isfinite(safe), safe, floor_linear)
        db_values = 20.0 * np.log10(np.maximum(safe, floor_linear))
        return np.clip(db_values, self.DB_FLOOR_DB, None)

    def _apply_transient_ylim(self, ax: plt.Axes, arrays: List[np.ndarray]) -> None:
        """Expand flat traces to a meaningful viewing window."""
        finite_arrays = [self._finite_array(values) for values in arrays]
        finite_arrays = [values for values in finite_arrays if values.size]
        if not finite_arrays:
            return

        combined = np.concatenate(finite_arrays)
        data_min = float(np.min(combined))
        data_max = float(np.max(combined))
        span = data_max - data_min
        abs_peak = max(abs(data_min), abs(data_max), 1e-12)

        if span <= max(abs_peak * 0.05, 1e-9):
            if data_min >= 0.0:
                ax.set_ylim(0.0, max(data_max * 2.0, 1.0))
                return
            if data_max <= 0.0:
                ax.set_ylim(min(data_min * 2.0, -1.0), 0.0)
                return

            limit = max(abs_peak * 1.5, 1.0)
            ax.set_ylim(-limit, limit)
            return

        margin = max(span * 0.1, abs_peak * 0.02, 1e-6)
        lower = data_min - margin
        upper = data_max + margin
        if data_min >= 0.0 and data_max > 0.0:
            lower = min(0.0, lower)
        if data_max <= 0.0 and data_min < 0.0:
            upper = max(0.0, upper)
        ax.set_ylim(lower, upper)

    def _apply_db_ylim(self, ax: plt.Axes, db_values: np.ndarray) -> None:
        """Keep dB plots readable and avoid useless ultra-low ranges."""
        finite_db = self._finite_array(db_values)
        if not finite_db.size:
            ax.set_ylim(self.DB_FLOOR_DB - 5.0, 5.0)
            return

        data_min = float(np.min(finite_db))
        data_max = float(np.max(finite_db))
        span = data_max - data_min
        margin = max(span * 0.1, 3.0)
        lower = max(self.DB_FLOOR_DB - 5.0, data_min - margin)
        upper = max(5.0, data_max + margin)

        if span < 1.0 and data_max <= self.DB_FLOOR_DB + 3.0:
            lower = self.DB_FLOOR_DB - 5.0
            upper = 5.0
        elif upper - lower < 20.0:
            upper = lower + 20.0

        ax.set_ylim(lower, upper)

    def _apply_phase_ylim(self, ax: plt.Axes, phase_deg: np.ndarray) -> None:
        """Apply a stable phase range with a sensible margin."""
        finite_phase = self._finite_array(phase_deg)
        if not finite_phase.size:
            return

        data_min = float(np.min(finite_phase))
        data_max = float(np.max(finite_phase))
        span = data_max - data_min
        margin = max(span * 0.15, 10.0)
        lower = data_min - margin
        upper = data_max + margin
        if lower < 0.0 < upper:
            lower = min(lower, -5.0)
            upper = max(upper, 5.0)
        ax.set_ylim(lower, upper)

    def _add_branding(self, fig: plt.Figure) -> None:
        """Add a visible framework mark to every generated figure."""
        fig.text(
            0.985,
            0.015,
            self.BRAND_TEXT,
            ha="right",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color=self.BRAND_COLOR,
            bbox={
                "boxstyle": "round,pad=0.25",
                "facecolor": "white",
                "edgecolor": self.BRAND_COLOR,
                "linewidth": 0.8,
                "alpha": 0.9,
            },
        )

    def _finalize_figure(self, fig: plt.Figure) -> None:
        """Finalize layout and ensure the figure carries the framework brand."""
        self._add_branding(fig)
        fig.tight_layout(rect=(0.02, 0.04, 0.98, 0.98))

    def _save_or_show(
        self,
        fig: plt.Figure,
        filename: Optional[str],
        default_prefix: str,
        save: bool,
    ) -> Optional[Path]:
        """Persist a figure with consistent metadata or display it interactively."""
        self._finalize_figure(fig)

        if save:
            resolved = filename or f"{default_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.output_dir / resolved
            fig.savefig(
                filepath,
                dpi=150,
                bbox_inches="tight",
                metadata={"Creator": self.BRAND_TEXT},
            )
            plt.close(fig)
            return filepath

        plt.show()
        plt.close(fig)
        return None

    def plot_transient(
        self,
        time: np.ndarray,
        signals: Dict[str, np.ndarray],
        title: str = "Transient Response",
        xlabel: str = "Time (s)",
        ylabel: str = "Voltage (V)",
        markers: Optional[Dict[str, Tuple[float, float]]] = None,
        filename: Optional[str] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """
        Plot transient waveforms.

        Args:
            time: Time array (seconds)
            signals: Dictionary {signal_name: voltage_array}
            title: Plot title
            xlabel: X-axis label
            ylabel: Y-axis label
            markers: Optional markers for specific points
            save: If True, save to file

        Returns:
            Path to saved image
        """
        time_array = np.asarray(time, dtype=float)
        scaled_time, time_scale, scaled_xlabel = self._scale_time_axis(time_array)
        fig, ax = plt.subplots(figsize=(12, 6))

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for index, (name, data) in enumerate(signals.items()):
            color = colors[index % len(colors)]
            ax.plot(scaled_time, data, label=name, color=color, linewidth=1.5)

        if markers:
            for name, (marker_time, marker_value) in markers.items():
                scaled_marker_time = float(marker_time) / time_scale if time_scale else float(marker_time)
                ax.plot(scaled_marker_time, marker_value, "ro", markersize=8)
                ax.annotate(
                    name,
                    (scaled_marker_time, marker_value),
                    xytext=(5, 5),
                    textcoords="offset points",
                )

        ax.set_xlabel(scaled_xlabel if xlabel == "Time (s)" else xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="best")
        self._apply_transient_ylim(ax, list(signals.values()))

        return self._save_or_show(fig, filename, "transient", save)

    def plot_ac_response(
        self,
        frequency: np.ndarray,
        magnitude: np.ndarray,
        phase: Optional[np.ndarray] = None,
        title: str = "AC Frequency Response",
        filename: Optional[str] = None,
        phase_in_degrees: bool = False,
        save: bool = True,
    ) -> Optional[Path]:
        """
        Plot AC frequency response (Bode plot).

        Args:
            frequency: Frequency array (Hz)
            magnitude: Magnitude array (linear, will be converted to dB)
            phase: Phase array (radians, optional)
            title: Plot title
            save: If True, save to file

        Returns:
            Path to saved image
        """
        mask = self._positive_frequency_mask(frequency)
        frequency_array = np.asarray(frequency, dtype=float)[mask]
        magnitude_array = np.asarray(magnitude, dtype=float)[mask]
        phase_array = np.asarray(phase, dtype=float)[mask] if phase is not None else None

        if not frequency_array.size or not magnitude_array.size:
            raise ValueError("AC response plotting requires strictly positive finite frequencies")

        if phase_array is not None:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        else:
            fig, ax1 = plt.subplots(figsize=(12, 6))

        mag_db = self._to_db(magnitude_array)

        ax1.semilogx(frequency_array, mag_db, "b-", linewidth=1.5)
        ax1.set_ylabel("Magnitude (dB)")
        ax1.set_title(title)
        ax1.grid(True, alpha=0.3, linestyle="--")
        self._apply_db_ylim(ax1, mag_db)

        if len(mag_db) > 0:
            dc_gain = mag_db[0]
            ax1.axhline(y=dc_gain - 3.0, color="r", linestyle="--", alpha=0.5, label="-3dB")

        if phase_array is not None:
            phase_deg = phase_array if phase_in_degrees else phase_array * 180.0 / np.pi
            ax2.semilogx(frequency_array, phase_deg, "r-", linewidth=1.5)
            ax2.set_xlabel("Frequency (Hz)")
            ax2.set_ylabel("Phase (degrees)")
            ax2.grid(True, alpha=0.3, linestyle="--")
            ax2.axhline(y=-180.0, color="k", linestyle="--", alpha=0.3)
            ax2.axhline(y=0.0, color="k", linestyle="--", alpha=0.3)
            self._apply_phase_ylim(ax2, phase_deg)
        else:
            ax1.set_xlabel("Frequency (Hz)")

        ax1.legend(loc="best")
        return self._save_or_show(fig, filename, "ac_response", save)

    def plot_fft(
        self,
        frequency: np.ndarray,
        spectrum: np.ndarray,
        title: str = "FFT Spectrum",
        fundamental_freq: Optional[float] = None,
        filename: Optional[str] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """
        Plot FFT spectrum.

        Args:
            frequency: Frequency array (Hz)
            spectrum: Magnitude spectrum (linear)
            title: Plot title
            fundamental_freq: Fundamental frequency to highlight
            save: If True, save to file

        Returns:
            Path to saved image
        """
        mask = self._positive_frequency_mask(frequency)
        frequency_array = np.asarray(frequency, dtype=float)[mask]
        spectrum_array = np.asarray(spectrum, dtype=float)[mask]

        if not frequency_array.size or not spectrum_array.size:
            raise ValueError("FFT plotting requires strictly positive finite frequencies")

        fig, ax = plt.subplots(figsize=(12, 6))
        spec_db = self._to_db(spectrum_array)

        ax.semilogx(frequency_array, spec_db, "b-", linewidth=1.0)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle="--")
        self._apply_db_ylim(ax, spec_db)

        if fundamental_freq:
            ax.axvline(
                x=fundamental_freq,
                color="r",
                linestyle="--",
                alpha=0.5,
                label=f"Fundamental ({fundamental_freq / 1e6:.1f} MHz)",
            )
            for harmonic_index in range(2, 6):
                ax.axvline(x=harmonic_index * fundamental_freq, color="g", linestyle=":", alpha=0.3)

        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend(loc="best")
        return self._save_or_show(fig, filename, "fft", save)

    def plot_eye_diagram(
        self,
        signal: np.ndarray,
        period: float,
        samples_per_period: int,
        title: str = "Eye Diagram",
        filename: Optional[str] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """
        Plot eye diagram for high-speed signals.

        Args:
            signal: Signal array
            period: Period of the signal (seconds)
            samples_per_period: Number of samples per period
            title: Plot title
            save: If True, save to file

        Returns:
            Path to saved image
        """
        time_axis = np.linspace(0.0, period, samples_per_period)
        scaled_time, _, time_label = self._scale_time_axis(time_axis)
        signal_array = np.asarray(signal, dtype=float)
        fig, ax = plt.subplots(figsize=(12, 6))

        num_periods = len(signal_array) // samples_per_period
        for index in range(num_periods - 1):
            start = index * samples_per_period
            end = start + samples_per_period
            ax.plot(scaled_time, signal_array[start:end], "b-", alpha=0.3, linewidth=0.8)

        unit = time_label.split("(")[1].rstrip(")")
        period_label = f"{scaled_time[-1]:.3g} {unit}" if len(scaled_time) else f"0 {unit}"
        ax.set_xlabel(f"Time within period - {period_label}")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle="--")
        self._apply_transient_ylim(ax, [signal_array])

        return self._save_or_show(fig, filename, "eye_diagram", save)

    def plot_comparison(
        self,
        waveforms: Dict[str, np.ndarray],
        time: np.ndarray,
        title: str = "Waveform Comparison",
        filename: Optional[str] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """
        Plot multiple waveforms for comparison.

        Args:
            waveforms: Dictionary {name: waveform_data}
            time: Time array
            title: Plot title
            save: If True, save to file

        Returns:
            Path to saved image
        """
        scaled_time, _, xlabel = self._scale_time_axis(time)
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

        for index, (name, data) in enumerate(waveforms.items()):
            color = colors[index % len(colors)]
            ax.plot(scaled_time, data, label=name, color=color, linewidth=1.5)

        ax.set_xlabel(xlabel)
        ax.set_ylabel("Voltage (V)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="best")
        self._apply_transient_ylim(ax, list(waveforms.values()))

        return self._save_or_show(fig, filename, "comparison", save)

    def add_annotations(
        self,
        image_path: Path,
        annotations: List[Dict],
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Add annotations to an existing image.

        Args:
            image_path: Path to existing image
            annotations: List of annotations with 'x', 'y', 'text', 'color'
            output_path: Output path (default: overwrite or create new)

        Returns:
            Path to annotated image
        """
        import matplotlib.image as mpimg

        fig, ax = plt.subplots(figsize=(12, 6))
        img = mpimg.imread(image_path)
        ax.imshow(img)

        for annotation in annotations:
            ax.annotate(
                annotation["text"],
                xy=(annotation["x"], annotation["y"]),
                xytext=(
                    annotation.get("text_x", annotation["x"] + 10),
                    annotation.get("text_y", annotation["y"] + 10),
                ),
                color=annotation.get("color", "red"),
                fontsize=annotation.get("fontsize", 10),
                arrowprops=dict(arrowstyle="->", color=annotation.get("color", "red")),
            )

        ax.axis("off")

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"annotated_{timestamp}.png"

        self._finalize_figure(fig)
        fig.savefig(
            output_path,
            dpi=150,
            bbox_inches="tight",
            metadata={"Creator": self.BRAND_TEXT},
        )
        plt.close(fig)
        return output_path

    def plot_scalar_summary(
        self,
        metrics: Dict[str, Union[int, float]],
        title: str = "Scalar Summary",
        ylabel: str = "Value",
        filename: Optional[str] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot scalar DC/summary metrics as a bar chart."""
        clean_metrics = {
            str(name): float(value)
            for name, value in metrics.items()
            if value is not None and isinstance(value, (int, float)) and math.isfinite(float(value))
        }
        if not clean_metrics:
            raise ValueError("No finite scalar metrics available for summary plotting")

        fig, ax = plt.subplots(figsize=(max(8, len(clean_metrics) * 1.5), 6))
        names = list(clean_metrics.keys())
        values = [clean_metrics[name] for name in names]
        bars = ax.bar(names, values, color="#1f77b4", alpha=0.9)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3, linestyle="--")
        ax.tick_params(axis="x", rotation=25)

        for bar, value in zip(bars, values):
            ax.annotate(
                f"{value:.4g}",
                (bar.get_x() + bar.get_width() / 2.0, bar.get_height()),
                textcoords="offset points",
                xytext=(0, 5),
                ha="center",
            )

        return self._save_or_show(fig, filename, "scalar_summary", save)

    def optimize_for_vision_llm(
        self,
        image_path: Path,
        test_name: Optional[str] = None,
        circuit_type: Optional[str] = None,
        specification: Optional[Dict[str, Any]] = None,
        anomalies: Optional[List[str]] = None,
    ) -> Path:
        """
        Optimize waveform image for vision LLM analysis.

        Enhances image with:
        - Larger text annotations
        - Specification threshold overlays
        - Anomaly highlighting (red zones)
        - Test metadata in image
        - Increased contrast for vision model

        Args:
            image_path: Path to original waveform image
            test_name: Name of the test (for display)
            circuit_type: Circuit type (for display)
            specification: Dict with thresholds {metric: {min, max}}
            anomalies: List of detected anomalies to highlight

        Returns:
            Path to optimized image
        """
        from PIL import Image, ImageDraw, ImageFont

        logger.info(f"Optimizing image for vision LLM: {image_path}")

        try:
            img = Image.open(image_path)

            if img.mode != "RGB":
                img = img.convert("RGB")

            width, height = img.size
            max_width = 1280
            max_height = 720
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                width, height = new_size

            from PIL import ImageEnhance

            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)

            img_annotated = img.copy()
            draw = ImageDraw.Draw(img_annotated)

            try:
                font_large = ImageFont.truetype("arial.ttf", int(height * 0.04))
                font_small = ImageFont.truetype("arial.ttf", int(height * 0.025))
            except Exception:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

            margin = int(height * 0.02)
            y_offset = margin

            metadata_lines = []
            if test_name:
                metadata_lines.append(f"TEST: {test_name}")
            if circuit_type:
                metadata_lines.append(f"CIRCUIT: {circuit_type}")
            metadata_lines.append(f"FRAMEWORK: {self.BRAND_TEXT}")
            metadata_lines.append(f"TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            header_bg_height = len(metadata_lines) * int(height * 0.04) + 2 * margin
            draw.rectangle(
                [(0, 0), (width, header_bg_height)],
                fill=(240, 240, 240),
                outline=(100, 100, 100),
            )

            for line in metadata_lines:
                draw.text((margin * 2, y_offset), line, fill=(0, 0, 0), font=font_small)
                y_offset += int(height * 0.04)

            if specification:
                spec_text = "SPEC: "
                for metric, bounds in specification.items():
                    if "min" in bounds and "max" in bounds:
                        spec_text += f"{metric}: [{bounds['min']}-{bounds['max']}]  "

                text_bbox = draw.textbbox((0, 0), spec_text, font=font_small)
                text_height = text_bbox[3] - text_bbox[1]

                y_spec = height - text_height - margin
                draw.rectangle(
                    [(margin, y_spec - margin), (width - margin, height - margin)],
                    fill=(255, 255, 220),
                    outline=(200, 200, 0),
                )
                draw.text((margin * 2, y_spec), spec_text, fill=(0, 0, 0), font=font_small)

            if anomalies:
                anomaly_text = "ANOMALIES: " + ", ".join(anomalies[:3])
                if len(anomalies) > 3:
                    anomaly_text += f" +{len(anomalies) - 3} more"

                text_bbox = draw.textbbox((0, 0), anomaly_text, font=font_small)
                text_height = text_bbox[3] - text_bbox[1]

                y_anom = height - (text_height * 3) - (margin * 4)
                draw.rectangle(
                    [(margin, y_anom - margin), (width - margin, y_anom + text_height + margin)],
                    fill=(255, 200, 200),
                    outline=(200, 0, 0),
                )
                draw.text((margin * 2, y_anom), anomaly_text, fill=(200, 0, 0), font=font_small)

            branding_text = self.BRAND_TEXT
            branding_bbox = draw.textbbox((0, 0), branding_text, font=font_large)
            branding_width = branding_bbox[2] - branding_bbox[0]
            branding_height = branding_bbox[3] - branding_bbox[1]
            branding_x = width - branding_width - (margin * 2)
            branding_y = height - branding_height - (margin * 2)
            draw.rectangle(
                [
                    (branding_x - margin, branding_y - margin),
                    (width - margin, height - margin),
                ],
                fill=(255, 255, 255),
                outline=(11, 61, 145),
            )
            draw.text((branding_x, branding_y), branding_text, fill=(11, 61, 145), font=font_large)

            optimized_path = image_path.parent / f"{image_path.stem}_optimized.png"
            img_annotated.save(optimized_path, quality=95, dpi=(150, 150))

            logger.info(f"Optimized image saved: {optimized_path} ({img_annotated.size})")
            return optimized_path

        except Exception as exc:
            logger.warning(f"Failed to optimize image for vision LLM: {exc}")
            logger.warning("Returning original image path")
            return image_path
