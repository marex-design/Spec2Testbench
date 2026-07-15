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
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", "NGSPICE_MEASURE_FAILED")
                continue
            results[metric_name] = MetricExtraction(metric_name, entry["value"], request.get("unit", ""), entry["status"], entry.get("error"))
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
                )
            return results
        for request in metric_requests:
            metric_name = request["name"]
            extractor = WRDATA_EXTRACTORS.get(metric_name)
            if extractor is None:
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", "WRDATA_UNSUPPORTED_METRIC")
                continue
            try:
                value = extractor(parsed, request)
            except ValueError as exc:
                results[metric_name] = MetricExtraction(metric_name, None, request.get("unit", ""), "NOT_EVALUATED", str(exc))
                continue
            results[metric_name] = MetricExtraction(metric_name, value, request.get("unit", ""), "SUCCESS")
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


def compute_dc_gain_db(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    data = parsed["data"]
    freq = data[:, 0]
    out_real = data[:, request.get("out_real_column", 1)]
    out_imag = data[:, request.get("out_imag_column", 2)]
    in_real = data[:, request.get("in_real_column", 3)]
    in_imag = data[:, request.get("in_imag_column", 4)]
    out_mag = np.sqrt(out_real ** 2 + out_imag ** 2)
    in_mag = np.sqrt(in_real ** 2 + in_imag ** 2)
    ratio = np.divide(out_mag, in_mag, out=np.full_like(out_mag, np.nan), where=in_mag > 0)
    index = int(np.argmin(freq))
    value = ratio[index]
    if not np.isfinite(value) or value <= 0:
        raise ValueError("INVALID_GAIN_RATIO")
    return float(20.0 * np.log10(value))


def compute_cutoff_frequency(parsed: dict[str, np.ndarray], request: dict[str, Any]) -> float:
    data = parsed["data"]
    freq = data[:, 0]
    out_real = data[:, request.get("out_real_column", 1)]
    out_imag = data[:, request.get("out_imag_column", 2)]
    in_real = data[:, request.get("in_real_column", 3)]
    in_imag = data[:, request.get("in_imag_column", 4)]
    out_mag = np.sqrt(out_real ** 2 + out_imag ** 2)
    in_mag = np.sqrt(in_real ** 2 + in_imag ** 2)
    ratio = np.divide(out_mag, in_mag, out=np.full_like(out_mag, np.nan), where=in_mag > 0)
    finite = ratio[np.isfinite(ratio)]
    if len(finite) == 0:
        raise ValueError("INVALID_GAIN_RATIO")
    dc_gain = finite[0]
    target = dc_gain / math.sqrt(2.0)
    for index in range(1, len(freq)):
        if ratio[index] <= target < ratio[index - 1]:
            return float(interpolate_crossing(freq[index - 1], ratio[index - 1], freq[index], ratio[index], target))
    raise ValueError("CUTOFF_NOT_FOUND")


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


def _column(parsed: dict[str, np.ndarray], index: int) -> np.ndarray:
    data = parsed["data"]
    if data.shape[1] <= index:
        raise ValueError("WRDATA_COLUMN_MISMATCH")
    return data[:, index]


WRDATA_EXTRACTORS = {
    "amplitude_pp": compute_amplitude_pp,
    "startup_amplitude": compute_startup_amplitude,
    "frequency_hz": compute_frequency_hz,
    "oscillator_frequency": compute_frequency_hz,
    "switching_threshold_rising_v": compute_switching_threshold_rising,
    "switching_threshold_falling_v": compute_switching_threshold_falling,
    "hysteresis_width_v": compute_hysteresis_width,
    "dc_gain_db": compute_dc_gain_db,
    "cutoff_frequency_hz": compute_cutoff_frequency,
    "bandwidth": compute_cutoff_frequency,
}
