import csv
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np


@dataclass
class SimulationArtifacts:
    raw_file: Optional[Path]
    stdout_file: Optional[Path]
    stderr_file: Optional[Path]
    measures_file: Optional[Path]
    vectors_file: Optional[Path]
    vector_csv_file: Optional[Path]
    vector_metadata_file: Optional[Path]


@dataclass
class MetricExtraction:
    metric_name: str
    value: Optional[float]
    unit: str
    status: str
    error: Optional[str] = None
    backend: Optional[str] = None


class SimulationResultBackend(ABC):
    backend_name = "UNAVAILABLE"

    @abstractmethod
    def extract(self, simulation_artifacts: SimulationArtifacts, metric_requests: list[dict[str, Any]]) -> dict[str, MetricExtraction]:
        raise NotImplementedError


class NgspiceMeasureBackend(SimulationResultBackend):
    backend_name = "NGSPICE_MEASURE"

    MEASURE_RE = re.compile(r"(?im)^\s*(?P<name>[a-zA-Z_][\w]*)\s*=\s*(?P<value>.+?)\s*$")
    NUMERIC_PREFIX_RE = re.compile(r"^[\s]*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")

    def extract(self, simulation_artifacts: SimulationArtifacts, metric_requests: list[dict[str, Any]]) -> dict[str, MetricExtraction]:
        parsed = parse_measure_file(simulation_artifacts.measures_file)
        results: dict[str, MetricExtraction] = {}
        for request in metric_requests:
            metric_name = request["name"]
            entry = parsed.get(metric_name)
            if entry is None:
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", "NGSPICE_MEASURE_FAILED", self.backend_name)
                continue
            results[metric_name] = MetricExtraction(metric_name, entry["value"], request.get("unit", ""), entry["status"], entry.get("error"), self.backend_name)
        return results


class NgspiceWrdataBackend(SimulationResultBackend):
    backend_name = "NGSPICE_WRDATA"

    def extract(self, simulation_artifacts: SimulationArtifacts, metric_requests: list[dict[str, Any]]) -> dict[str, MetricExtraction]:
        results: dict[str, MetricExtraction] = {}
        try:
            parsed = parse_wrdata_file(simulation_artifacts.vectors_file)
        except ValueError as exc:
            for request in metric_requests:
                results[request["name"]] = MetricExtraction(
                    request["name"],
                    None,
                    request.get("unit", ""),
                    "NOT_EVALUATED",
                    str(exc),
                    self.backend_name,
                )
            return results
        for request in metric_requests:
            metric_name = request["name"]
            extractor = WRDATA_EXTRACTORS.get(metric_name)
            if extractor is None:
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", "WRDATA_UNSUPPORTED_METRIC", self.backend_name)
                continue
            try:
                value = extractor(parsed, request)
            except ValueError as exc:
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", str(exc), self.backend_name)
                continue
            results[metric_name] = MetricExtraction(metric_name, value, request.get("unit", ""), "SUCCESS", backend=self.backend_name)
        return results


class PySpiceResultBackend(SimulationResultBackend):
    backend_name = "PYSPICE"

    def __init__(self, parser_callable):
        self._parser_callable = parser_callable

    def extract(self, simulation_artifacts: SimulationArtifacts, metric_requests: list[dict[str, Any]]) -> dict[str, MetricExtraction]:
        parsed = self._parser_callable(simulation_artifacts.raw_file)
        results: dict[str, MetricExtraction] = {}
        for request in metric_requests:
            value = parsed.get(request["name"])
            results[request["name"]] = MetricExtraction(
                request["name"],
                float(value) if value is not None else None,
                request.get("unit", ""),
                "SUCCESS" if value is not None else "NOT_EVALUATED",
                None if value is not None else "PYSPICE_METRIC_UNAVAILABLE",
                self.backend_name,
            )
        return results


def parse_measure_file(path: Optional[Path]) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for match in NgspiceMeasureBackend.MEASURE_RE.finditer(text):
        name = match.group("name").strip()
        raw_value = match.group("value").strip()
        lowered = raw_value.lower()
        if lowered in {"failed", "not found"}:
            parsed[name] = {"value": None, "status": "NOT_EVALUATED", "error": "NGSPICE_MEASURE_FAILED"}
            continue
        try:
            numeric_match = NgspiceMeasureBackend.NUMERIC_PREFIX_RE.search(raw_value)
            numeric_text = numeric_match.group(1) if numeric_match else raw_value
            value = float(numeric_text)
            if math.isnan(value) or math.isinf(value):
                parsed[name] = {"value": None, "status": "NOT_EVALUATED", "error": "NON_FINITE_MEASURE"}
            else:
                parsed[name] = {"value": value, "status": "SUCCESS", "error": None}
        except ValueError:
            parsed[name] = {"value": None, "status": "NOT_EVALUATED", "error": "UNPARSABLE_MEASURE"}
    return parsed


def parse_wrdata_file(path: Optional[Path]) -> dict[str, np.ndarray]:
    if path is None or not path.exists():
        raise ValueError("WRDATA_FILE_MISSING")
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        raise ValueError("WRDATA_FILE_EMPTY")
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        try:
            row = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError("WRDATA_UNPARSABLE") from exc
        if any(math.isnan(value) or math.isinf(value) for value in row):
            raise ValueError("WRDATA_NON_FINITE")
        rows.append(row)
    if not rows:
        raise ValueError("WRDATA_FILE_EMPTY")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("WRDATA_COLUMN_MISMATCH")
    data = np.array(rows, dtype=float)
    return {"data": data}


def interpolate_crossing(x1: float, y1: float, x2: float, y2: float, target: float) -> float:
    if y2 == y1:
        raise ValueError("NO_INTERPOLATION_SLOPE")
    return x1 + ((target - y1) / (y2 - y1)) * (x2 - x1)


def interpolate_value_at_x(x1: float, y1: float, x2: float, y2: float, target_x: float) -> float:
    if x2 == x1:
        raise ValueError("NO_INTERPOLATION_SPAN")
    return y1 + ((target_x - x1) / (x2 - x1)) * (y2 - y1)


def compute_amplitude_pp(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    values = _column(parsed, request.get("value_column", -1))
    return float(np.max(values) - np.min(values))


def compute_dc_output_value(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    values = _column(parsed, request.get("value_column", -1))
    return float(values[-1])


def compute_dc_current_value(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    values = _column(parsed, request.get("current_column", 2))
    return float(abs(values[-1]))


def compute_dc_power_value(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    current = compute_dc_current_value(parsed, request)
    supply_voltage = float(request.get("supply_voltage") or 0.0)
    if not np.isfinite(supply_voltage) or supply_voltage <= 0:
        raise ValueError("SUPPLY_VOLTAGE_MISSING")
    return float(abs(supply_voltage * current))


def compute_startup_amplitude(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    return compute_amplitude_pp(parsed, request) / 2.0


def compute_frequency_hz(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    time = _column(parsed, request.get("time_column", 0))
    values = _column(parsed, request.get("value_column", 1))
    mean_value = float(np.mean(values))
    crossings = []
    for index in range(1, len(values)):
        if values[index - 1] <= mean_value < values[index]:
            crossings.append(interpolate_crossing(time[index - 1], values[index - 1], time[index], values[index], mean_value))
    if len(crossings) < 2:
        raise ValueError("NO_OUTPUT_TRANSITION")
    periods = np.diff(crossings)
    valid = periods[periods > 0]
    if len(valid) == 0:
        raise ValueError("NO_VALID_PERIOD")
    return float(1.0 / np.mean(valid))


def compute_switching_threshold_rising(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    return _compute_switching_threshold(parsed, request, direction="rising")


def compute_switching_threshold_falling(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    return _compute_switching_threshold(parsed, request, direction="falling")


def compute_hysteresis_width(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    rising = compute_switching_threshold_rising(parsed, request)
    falling = compute_switching_threshold_falling(parsed, request)
    return abs(rising - falling)


def compute_propagation_delay(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    time = _column(parsed, request.get("time_column", 0))
    vin = _column(parsed, request.get("vin_column", 1))
    vout = _column(parsed, request.get("vout_column", 2))
    threshold = request.get("output_threshold")
    if threshold is None:
        threshold = float(np.min(vout) + np.max(vout)) / 2.0
    input_crossing = _find_signal_crossing(time, vin, float(threshold), rising=True)
    output_crossing = _find_signal_crossing(time, vout, float(threshold), rising=True)
    if input_crossing is None or output_crossing is None:
        raise ValueError("NO_OUTPUT_TRANSITION")
    return float(max(0.0, output_crossing - input_crossing))


def compute_dc_gain_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    _, transfer, _, _ = _transfer_data_at_reference(parsed, request)
    magnitude = abs(transfer)
    if not np.isfinite(magnitude) or magnitude <= 0:
        raise ValueError("INVALID_GAIN_RATIO")
    return float(20.0 * np.log10(magnitude))


def compute_absolute_output_dbv(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    _, _, _, vout = _transfer_data_at_reference(parsed, request)
    magnitude = abs(vout)
    if not np.isfinite(magnitude) or magnitude <= 0:
        raise ValueError("INVALID_OUTPUT_MAGNITUDE")
    return float(20.0 * np.log10(magnitude))


def compute_absolute_input_dbv(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    _, _, vin, _ = _transfer_data_at_reference(parsed, request)
    magnitude = abs(vin)
    if not np.isfinite(magnitude) or magnitude <= 0:
        raise ValueError("INVALID_INPUT_MAGNITUDE")
    return float(20.0 * np.log10(magnitude))


def compute_transfer_magnitude_linear(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    _, transfer, _, _ = _transfer_data_at_reference(parsed, request)
    magnitude = abs(transfer)
    if not np.isfinite(magnitude) or magnitude <= 0:
        raise ValueError("INVALID_GAIN_RATIO")
    return float(magnitude)


def compute_transfer_phase_deg(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    _, transfer, _, _ = _transfer_data_at_reference(parsed, request)
    if not np.isfinite(transfer.real) or not np.isfinite(transfer.imag):
        raise ValueError("INVALID_GAIN_RATIO")
    return float(np.degrees(np.angle(transfer)))


def compute_cutoff_frequency(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    data = parsed["data"]
    freq = data[:, 0]
    transfer = _transfer_series(parsed, request)
    ratio = np.abs(transfer)
    finite_mask = np.isfinite(ratio)
    finite = ratio[finite_mask]
    if len(finite) == 0:
        raise ValueError("INVALID_GAIN_RATIO")
    peak_index = int(np.nanargmax(np.where(finite_mask, ratio, np.nan)))
    peak_gain = float(ratio[peak_index])
    if not np.isfinite(peak_gain) or peak_gain <= 0:
        raise ValueError("INVALID_GAIN_RATIO")
    target = peak_gain / math.sqrt(2.0)

    if peak_index == 0:
        cutoff = _find_crossing(freq, ratio, target, rising=False, start_index=1, stop_index=len(freq))
        if cutoff is None:
            raise ValueError("CUTOFF_NOT_FOUND")
        return cutoff
    if peak_index == len(freq) - 1:
        cutoff = _find_crossing(freq, ratio, target, rising=True, start_index=1, stop_index=len(freq))
        if cutoff is None:
            raise ValueError("CUTOFF_NOT_FOUND")
        return cutoff

    lower_cutoff = _find_crossing(freq[: peak_index + 1], ratio[: peak_index + 1], target, rising=True, start_index=1, stop_index=peak_index + 1)
    upper_cutoff = _find_crossing(freq, ratio, target, rising=False, start_index=peak_index + 1, stop_index=len(freq))
    if lower_cutoff is None or upper_cutoff is None or upper_cutoff <= lower_cutoff:
        raise ValueError("CUTOFF_NOT_FOUND")
    if str(request.get("name") or "").strip().lower() == "bandwidth":
        return float(upper_cutoff - lower_cutoff)
    return float(lower_cutoff)


def _transfer_db_series(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> np.ndarray:
    ratio = np.abs(_transfer_series(parsed, request))
    if ratio.size < 2 or not np.any(np.isfinite(ratio)):
        raise ValueError("INSUFFICIENT_AC_DATA")
    return 20.0 * np.log10(np.maximum(ratio, 1e-30))


def compute_lowpass_attenuation_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    return float(db[0] - db[-1])


def compute_lowpass_monotonicity_percent(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    if db.size < 3:
        raise ValueError("INSUFFICIENT_AC_DATA")
    return float(100.0 * np.mean(np.diff(db) <= 0.5))


def compute_highpass_attenuation_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    return float(db[-1] - db[0])


def compute_highpass_monotonicity_percent(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    if db.size < 3:
        raise ValueError("INSUFFICIENT_AC_DATA")
    return float(100.0 * np.mean(np.diff(db) >= -0.5))


def compute_bandpass_peak_separation_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    if db.size < 5:
        raise ValueError("INSUFFICIENT_AC_DATA")
    peak_index = int(np.nanargmax(db))
    if peak_index == 0 or peak_index == db.size - 1:
        raise ValueError("BANDPASS_PEAK_NOT_INTERIOR")
    left_avg = float(np.mean(db[:peak_index]))
    right_avg = float(np.mean(db[peak_index + 1:]))
    peak = float(db[peak_index])
    return float(min(peak - left_avg, peak - right_avg))


def compute_bandstop_notch_depth_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    db = _transfer_db_series(parsed, request)
    if db.size < 5:
        raise ValueError("INSUFFICIENT_AC_DATA")
    notch_index = int(np.nanargmin(db))
    if notch_index == 0 or notch_index == db.size - 1:
        raise ValueError("BANDSTOP_NOTCH_NOT_INTERIOR")
    left_avg = float(np.mean(db[:notch_index]))
    right_avg = float(np.mean(db[notch_index + 1:]))
    notch = float(db[notch_index])
    return float(min(left_avg - notch, right_avg - notch))


def compute_unity_gain_frequency(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    data = parsed["data"]
    freq = data[:, 0]
    ratio = np.abs(_transfer_series(parsed, request))
    cutoff = _find_crossing(freq, ratio, 1.0, rising=False, start_index=1, stop_index=len(freq))
    if cutoff is not None:
        return cutoff
    cutoff = _find_crossing(freq, ratio, 1.0, rising=True, start_index=1, stop_index=len(freq))
    if cutoff is not None:
        return cutoff
    raise ValueError("UNITY_GAIN_NOT_FOUND")


def compute_phase_margin(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    data = parsed["data"]
    freq = data[:, 0]
    transfer = _transfer_series(parsed, request)
    phase = np.degrees(np.angle(transfer))
    ugf = compute_unity_gain_frequency(parsed, request)

    if len(freq) < 2 or len(phase) < 2:
        raise ValueError("INSUFFICIENT_PHASE_DATA")

    phase_at_ugf = None
    for index in range(1, len(freq)):
        left = float(freq[index - 1])
        right = float(freq[index])
        if left <= ugf <= right or right <= ugf <= left:
            phase_at_ugf = float(interpolate_value_at_x(left, float(phase[index - 1]), right, float(phase[index]), ugf))
            break
    if phase_at_ugf is None:
        nearest = int(np.argmin(np.abs(freq - ugf)))
        phase_at_ugf = float(phase[nearest])
    return float(max(0.0, min(180.0, 180.0 + phase_at_ugf)))


def compute_fundamental_frequency(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    return compute_frequency_hz(parsed, request)


def compute_thd_percent(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    time = _column(parsed, request.get("time_column", 0))
    values = _column(parsed, request.get("value_column", 1))
    if len(time) < 8 or len(values) < 8:
        raise ValueError("INSUFFICIENT_TRANSIENT_DATA")
    dt = float(np.mean(np.diff(time)))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("INVALID_TIMEBASE")

    windowed = (values - np.mean(values)) * np.hanning(len(values))
    spectrum = np.fft.rfft(windowed)
    frequencies = np.fft.rfftfreq(len(values), dt)
    magnitudes = np.abs(spectrum)
    if len(magnitudes) < 2:
        raise ValueError("INSUFFICIENT_SPECTRAL_DATA")

    magnitudes[0] = 0.0
    fundamental_index = int(np.argmax(magnitudes))
    fundamental_magnitude = float(magnitudes[fundamental_index])
    if fundamental_index <= 0 or not np.isfinite(fundamental_magnitude) or fundamental_magnitude <= 0:
        raise ValueError("FUNDAMENTAL_NOT_FOUND")

    sum_squares = 0.0
    for harmonic_order in range(2, 6):
        target_frequency = harmonic_order * float(frequencies[fundamental_index])
        harmonic_index = int(np.argmin(np.abs(frequencies - target_frequency)))
        harmonic_magnitude = float(magnitudes[harmonic_index]) if harmonic_index < len(magnitudes) else 0.0
        sum_squares += harmonic_magnitude ** 2
    return float(100.0 * math.sqrt(sum_squares) / max(fundamental_magnitude, 1e-30))


def _compute_switching_threshold(parsed: dict[str, np.ndarray], request: dict[str, Any], direction: str) -> float:
    time = _column(parsed, request.get("time_column", 0))
    vin = _column(parsed, request.get("vin_column", 1))
    vout = _column(parsed, request.get("vout_column", 2))
    threshold = request.get("output_threshold")
    if threshold is None:
        threshold = float(np.min(vout) + np.max(vout)) / 2.0
    for index in range(1, len(vout)):
        previous = vout[index - 1]
        current = vout[index]
        rising = previous < threshold <= current
        falling = previous > threshold >= current
        if (direction == "rising" and rising) or (direction == "falling" and falling):
            t_cross = interpolate_crossing(time[index - 1], previous, time[index], current, threshold)
            return float(interpolate_value_at_x(time[index - 1], vin[index - 1], time[index], vin[index], t_cross))
    raise ValueError("NO_OUTPUT_TRANSITION")


def _transfer_series(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> np.ndarray:
    data = parsed["data"]
    in_real = data[:, request.get("in_real_column", 1)]
    in_imag = data[:, request.get("in_imag_column", 2)]
    out_real = data[:, request.get("out_real_column", 3)]
    out_imag = data[:, request.get("out_imag_column", 4)]
    vin = in_real + 1j * in_imag
    vout = out_real + 1j * out_imag
    vin_mag = np.abs(vin)
    return np.divide(vout, vin, out=np.full_like(vout, np.nan + 0j, dtype=np.complex128), where=vin_mag > 0)


def _transfer_data_at_reference(
    parsed: dict[str, np.ndarray],
    request: dict[str, Any],
) -> tuple[float, complex, complex, complex]:
    data = parsed["data"]
    freq = data[:, 0]
    index = int(np.argmin(freq))
    in_real = float(data[index, request.get("in_real_column", 1)])
    in_imag = float(data[index, request.get("in_imag_column", 2)])
    out_real = float(data[index, request.get("out_real_column", 3)])
    out_imag = float(data[index, request.get("out_imag_column", 4)])
    vin = complex(in_real, in_imag)
    vout = complex(out_real, out_imag)
    if not np.isfinite(vin.real) or not np.isfinite(vin.imag):
        raise ValueError("INPUT_VECTOR_MISSING")
    if not np.isfinite(vout.real) or not np.isfinite(vout.imag):
        raise ValueError("OUTPUT_VECTOR_MISSING")
    if abs(vin) <= 0:
        raise ValueError("INPUT_VECTOR_ZERO")
    transfer = vout / vin
    if not np.isfinite(transfer.real) or not np.isfinite(transfer.imag):
        raise ValueError("INVALID_GAIN_RATIO")
    return float(freq[index]), transfer, vin, vout


def _find_crossing(
    freq: np.ndarray,
    values: np.ndarray,
    target: float,
    *,
    rising: bool,
    start_index: int,
    stop_index: int,
) -> float | None:
    for index in range(start_index, stop_index):
        previous = float(values[index - 1])
        current = float(values[index])
        if not np.isfinite(previous) or not np.isfinite(current):
            continue
        if rising and previous <= target <= current:
            return float(interpolate_crossing(float(freq[index - 1]), previous, float(freq[index]), current, target))
        if not rising and previous >= target >= current:
            return float(interpolate_crossing(float(freq[index - 1]), previous, float(freq[index]), current, target))
    return None


def _find_signal_crossing(
    time: np.ndarray,
    values: np.ndarray,
    target: float,
    *,
    rising: bool,
) -> float | None:
    for index in range(1, len(values)):
        previous = float(values[index - 1])
        current = float(values[index])
        if not np.isfinite(previous) or not np.isfinite(current):
            continue
        if rising and previous <= target <= current:
            return float(interpolate_crossing(float(time[index - 1]), previous, float(time[index]), current, target))
        if not rising and previous >= target >= current:
            return float(interpolate_crossing(float(time[index - 1]), previous, float(time[index]), current, target))
    return None


def _column(parsed: dict[str, np.ndarray], index: int) -> np.ndarray:
    data = parsed["data"]
    if data.shape[1] <= index:
        raise ValueError("WRDATA_COLUMN_MISMATCH")
    return data[:, index]


WRDATA_EXTRACTORS = {
    "amplitude_pp": compute_amplitude_pp,
    "operating_point": compute_dc_output_value,
    "vout_dc": compute_dc_output_value,
    "quiescent_current": compute_dc_current_value,
    "idd": compute_dc_current_value,
    "power": compute_dc_power_value,
    "startup_amplitude": compute_startup_amplitude,
    "frequency_hz": compute_frequency_hz,
    "oscillator_frequency": compute_frequency_hz,
    "propagation_delay": compute_propagation_delay,
    "propagation_delay_s": compute_propagation_delay,
    "switching_threshold_rising_v": compute_switching_threshold_rising,
    "switching_threshold_falling_v": compute_switching_threshold_falling,
    "hysteresis_width_v": compute_hysteresis_width,
    "dc_gain_db": compute_dc_gain_db,
    "absolute_output_dbv": compute_absolute_output_dbv,
    "absolute_input_dbv": compute_absolute_input_dbv,
    "transfer_magnitude_linear": compute_transfer_magnitude_linear,
    "transfer_phase_deg": compute_transfer_phase_deg,
    "cutoff_frequency_hz": compute_cutoff_frequency,
    "bandwidth": compute_cutoff_frequency,
    "unity_gain_frequency": compute_unity_gain_frequency,
    "ugbw": compute_unity_gain_frequency,
    "phase_margin": compute_phase_margin,
    "lowpass_attenuation_db": compute_lowpass_attenuation_db,
    "lowpass_monotonicity_percent": compute_lowpass_monotonicity_percent,
    "highpass_attenuation_db": compute_highpass_attenuation_db,
    "highpass_monotonicity_percent": compute_highpass_monotonicity_percent,
    "bandpass_peak_separation_db": compute_bandpass_peak_separation_db,
    "bandstop_notch_depth_db": compute_bandstop_notch_depth_db,
    "fundamental_frequency": compute_fundamental_frequency,
    "thd": compute_thd_percent,
    "thd_percent": compute_thd_percent,
}
