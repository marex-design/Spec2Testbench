# spec2testbench/infrastructure/spec_checker/metric_extractor.py

"""
MetricExtractor - Extracts metrics from simulation results.
"""

import math
import logging
from typing import Dict, Any, Optional, List, Iterable

logger = logging.getLogger(__name__)


class MetricExtractor:
    """
    Extract specific metrics from simulation results.
    
    Supports:
    - Gain (dB and linear)
    - Bandwidth
    - Phase margin
    - Slew rate
    - Settling time
    - Power consumption
    - THD (Total Harmonic Distortion)
    """
    
    def extract(self, results: Dict[str, Any], metric_name: str) -> Optional[float]:
        """
        Extract a specific metric from simulation results.
        
        Args:
            results: Simulation results dictionary
            metric_name: Name of the metric to extract
            
        Returns:
            Metric value or None if not found
        """
        metric_lower = metric_name.lower()

        direct_value = self._lookup_metric_value(results, self._candidate_names(metric_lower, metric_name))
        if direct_value is not None:
            return direct_value
        
        # Map metric name to extraction method
        extractors = {
            "operating_point": self._extract_operating_point,
            "vout_dc": self._extract_operating_point,
            "quiescent_current": self._extract_current,
            "idd": self._extract_current,
            "dc_gain": self._extract_dc_gain,
            "gain": self._extract_dc_gain,
            "bandwidth": self._extract_bandwidth,
            "cutoff_frequency": self._extract_bandwidth,
            "gbw": self._extract_gbw,
            "ugbw": self._extract_gbw,
            "unity_gain_frequency": self._extract_gbw,
            "phase_margin": self._extract_phase_margin,
            "slew_rate": self._extract_slew_rate,
            "settling_time": self._extract_settling_time,
            "propagation_delay": self._extract_propagation_delay,
            "oscillator_frequency": self._extract_frequency,
            "frequency_hz": self._extract_frequency,
            "startup_amplitude": self._extract_startup_amplitude,
            "power": self._extract_power,
            "current": self._extract_current,
            "thd": self._extract_thd,
            "cmrr": self._extract_cmrr,
            "psrr": self._extract_psrr,
            "pvt": self._extract_pvt_metric,
        }
        
        # Find matching extractor
        for key, extractor in extractors.items():
            if key in metric_lower:
                return extractor(results)
        
        # Try direct lookup
        if metric_name in results:
            return results[metric_name]
        
        logger.warning(f"Metric '{metric_name}' not found in results")
        return None

    def _candidate_names(self, metric_lower: str, metric_name: str) -> List[str]:
        aliases = {
            "operating_point": ["vout_dc", "op_point", "op_voltage"],
            "vout_dc": ["operating_point", "op_point", "vout"],
            "quiescent_current": ["idd", "iq", "current"],
            "idd": ["quiescent_current", "iq", "current"],
            "power": ["power_w", "power_mw"],
            "dc_gain": ["dc_gain_db", "gain_db"],
            "bandwidth": ["cutoff_frequency", "cutoff_frequency_hz", "bw"],
            "unity_gain_frequency": ["ugbw", "gbw"],
            "gbw": ["ugbw", "unity_gain_frequency"],
            "phase_margin": ["phase_margin_deg"],
            "propagation_delay": ["comparator_delay", "delay", "propagation_delay_s"],
            "oscillator_frequency": ["frequency_hz", "fundamental_frequency"],
            "frequency_hz": ["oscillator_frequency", "fundamental_frequency"],
            "thd": ["thd_percent"],
            "pvt_vout_variation": ["vout_variation"],
            "pvt_dc_gain_variation": ["gain_variation"],
            "pvt_power_variation": ["power_variation"],
        }
        return [metric_name, metric_lower, *aliases.get(metric_lower, [])]

    def _lookup_metric_value(self, results: Dict[str, Any], names: Iterable[str]) -> Optional[float]:
        containers = [
            results.get("metrics", {}),
            results.get("dc", {}),
            results.get("ac", {}),
            results.get("fourier", {}),
            results.get("pvt", {}).get("summary", {}),
            results,
        ]

        for container in containers:
            if not isinstance(container, dict):
                continue
            for name in names:
                value = container.get(name)
                if isinstance(value, (int, float)):
                    return float(value)
        return None

    def _extract_operating_point(self, results: Dict[str, Any]) -> Optional[float]:
        dc_data = results.get("dc", {})
        for key in ("vout_dc", "vout", "out", "operating_point"):
            value = dc_data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        metrics = results.get("metrics", {})
        for key in ("vout_dc", "operating_point", "vout"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None
    
    def _extract_dc_gain(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract DC gain from AC analysis."""
        ac_data = results.get("ac", {})
        direct_gain = ac_data.get("dc_gain_db")
        if isinstance(direct_gain, (int, float)):
            return float(direct_gain)
        magnitude = ac_data.get("magnitude", [])
        
        if magnitude and len(magnitude) > 0:
            # DC gain is magnitude at lowest frequency
            dc_gain_linear = magnitude[0]
            return 20 * math.log10(dc_gain_linear) if dc_gain_linear > 0 else -float('inf')
        
        return None
    
    def _extract_bandwidth(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract -3dB bandwidth from AC analysis."""
        ac_data = results.get("ac", {})
        for key in ("bandwidth", "cutoff_frequency", "cutoff_frequency_hz"):
            value = ac_data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        magnitude = ac_data.get("magnitude", [])
        frequency = ac_data.get("frequency", [])
        
        if not magnitude or not frequency:
            return None
        
        # Find DC gain
        dc_gain_linear = magnitude[0]
        target_gain = dc_gain_linear / math.sqrt(2)  # -3dB point
        
        # Find frequency where magnitude drops below target
        for i, mag in enumerate(magnitude):
            if mag < target_gain:
                if i > 0:
                    # Interpolate
                    return self._interpolate_frequency(
                        frequency[i-1], frequency[i],
                        magnitude[i-1], magnitude[i],
                        target_gain
                    )
                return frequency[i]
        
        return frequency[-1] if frequency else None
    
    def _extract_gbw(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract Gain-Bandwidth Product."""
        ac_data = results.get("ac", {})
        for key in ("unity_gain_frequency", "ugbw", "gbw"):
            value = ac_data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        magnitude = ac_data.get("magnitude", [])
        frequency = ac_data.get("frequency", [])
        
        if not magnitude or not frequency:
            return None
        
        # Find unity gain frequency (0dB = gain = 1)
        target_gain = 1.0
        
        for i, mag in enumerate(magnitude):
            if mag < target_gain:
                if i > 0:
                    return self._interpolate_frequency(
                        frequency[i-1], frequency[i],
                        magnitude[i-1], magnitude[i],
                        target_gain
                    )
                return frequency[i]
        
        return frequency[-1] if frequency else None
    
    def _extract_phase_margin(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract phase margin at GBW."""
        ac_data = results.get("ac", {})
        phase_margin = ac_data.get("phase_margin")
        if isinstance(phase_margin, (int, float)):
            return float(phase_margin)
        phase = ac_data.get("phase", [])
        frequency = ac_data.get("frequency", [])
        magnitude = ac_data.get("magnitude", [])
        
        if not phase or not frequency or not magnitude:
            return None
        
        # Find GBW frequency
        gbw = self._extract_gbw(results)
        if gbw is None:
            return None
        
        # Find phase at GBW
        for i, freq in enumerate(frequency):
            if freq >= gbw:
                # Phase margin = 180 + phase (since phase is negative)
                phase_at_gbw = phase[i] if i < len(phase) else phase[-1]
                margin = 180 + phase_at_gbw
                return max(0, min(180, margin))
        
        return None
    
    def _extract_slew_rate(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract slew rate from transient analysis."""
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vout = self._get_waveform(tran_data, "out")
        
        if not time or not vout or len(time) < 2:
            return None
        
        # Compute max derivative
        max_sr = 0.0
        for i in range(1, len(time)):
            dt = time[i] - time[i-1]
            dv = vout[i] - vout[i-1]
            if dt > 0:
                sr = abs(dv / dt)
                if sr > max_sr:
                    max_sr = sr
        
        return max_sr
    
    def _extract_settling_time(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract settling time to 1%."""
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vout = self._get_waveform(tran_data, "out")
        
        if not time or not vout or len(time) < 2:
            return None
        
        # Find final value (last point)
        final_value = vout[-1]
        tolerance = 0.01 * abs(final_value)  # 1%
        
        # Find when output enters and stays within tolerance
        settled_time = None
        settled_count = 0
        required_samples = 5  # Need 5 consecutive samples within tolerance
        
        for i in range(len(time) - 1, -1, -1):
            if abs(vout[i] - final_value) <= tolerance:
                settled_count += 1
                if settled_count >= required_samples:
                    settled_time = time[i]
                    break
            else:
                settled_count = 0
        
        return settled_time

    def _extract_propagation_delay(self, results: Dict[str, Any]) -> Optional[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vin = self._get_waveform(tran_data, "in")
        vout = self._get_waveform(tran_data, "out")

        if not time or not vin or not vout:
            return None

        vin_threshold = (max(vin) + min(vin)) / 2
        vout_threshold = (max(vout) + min(vout)) / 2
        input_crossing = self._first_threshold_crossing(time, vin, vin_threshold)
        output_crossing = self._first_threshold_crossing(time, vout, vout_threshold)

        if input_crossing is None or output_crossing is None:
            return None
        return max(0.0, output_crossing - input_crossing)

    def _extract_frequency(self, results: Dict[str, Any]) -> Optional[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vout = self._get_waveform(tran_data, "out")

        if len(time) < 3 or len(vout) < 3:
            return None

        mean_value = sum(vout) / len(vout)
        crossings = []
        for index in range(1, len(vout)):
            if vout[index - 1] <= mean_value < vout[index]:
                crossings.append(time[index])

        if len(crossings) < 2:
            return None

        periods = [crossings[index] - crossings[index - 1] for index in range(1, len(crossings))]
        valid_periods = [period for period in periods if period > 0]
        if not valid_periods:
            return None
        average_period = sum(valid_periods) / len(valid_periods)
        return 1.0 / average_period if average_period > 0 else None

    def _extract_startup_amplitude(self, results: Dict[str, Any]) -> Optional[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran_data, "out")
        if len(vout) < 5:
            return None
        tail_start = max(0, int(len(vout) * 0.8))
        steady_state = vout[tail_start:]
        return (max(steady_state) - min(steady_state)) / 2
    
    def _extract_power(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract power consumption."""
        direct_power = self._lookup_metric_value(results, ("power", "power_w", "power_mw"))
        if direct_power is not None:
            return direct_power
        # Get current from VDD source
        currents = results.get("currents", {})
        idd = currents.get("vdd", currents.get("VDD", 0))
        
        # Get voltage
        vdd = results.get("vdd", 1.8)
        
        return vdd * abs(idd)
    
    def _extract_current(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract current consumption."""
        direct_current = self._lookup_metric_value(results, ("quiescent_current", "idd", "iq", "current"))
        if direct_current is not None:
            return direct_current
        currents = results.get("currents", {})
        return currents.get("vdd", currents.get("VDD", None))
    
    def _extract_thd(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract Total Harmonic Distortion."""
        direct_thd = self._lookup_metric_value(results, ("thd", "thd_percent"))
        if direct_thd is not None:
            return direct_thd
        fourier = results.get("fourier", {})
        harmonics = fourier.get("harmonics", [])
        
        if not harmonics or len(harmonics) < 2:
            return None
        
        fundamental = harmonics[0].get("magnitude", 0)
        if fundamental == 0:
            return None
        
        # THD = sqrt(sum(H2^2 + H3^2 + ...)) / H1
        sum_squares = sum(h.get("magnitude", 0)**2 for h in harmonics[1:])
        thd = math.sqrt(sum_squares) / fundamental
        
        return thd * 100  # Return as percentage

    def _extract_pvt_metric(self, results: Dict[str, Any]) -> Optional[float]:
        summary = results.get("pvt", {}).get("summary", {})
        if not isinstance(summary, dict):
            return None
        for value in summary.values():
            if isinstance(value, (int, float)):
                return float(value)
        return None
    
    def _extract_cmrr(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract Common Mode Rejection Ratio."""
        # CMRR = |Ad| / |Acm|
        ac_data = results.get("ac", {})
        
        # Differential gain (assumes in-phase inputs)
        ad = ac_data.get("differential_gain", [])
        # Common mode gain (same input on both)
        acm = ac_data.get("common_mode_gain", [])
        
        if ad and acm and len(ad) > 0 and len(acm) > 0:
            cmrr = ad[0] / acm[0] if acm[0] != 0 else float('inf')
            return 20 * math.log10(cmrr) if cmrr > 0 else -float('inf')
        
        return None
    
    def _extract_psrr(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract Power Supply Rejection Ratio."""
        # PSRR = |Vout| / |Vdd|
        ac_data = results.get("ac", {})
        vout = ac_data.get("magnitude", [])
        vdd = ac_data.get("vdd_magnitude", [])
        
        if vout and vdd and len(vout) > 0 and len(vdd) > 0:
            psrr = vout[0] / vdd[0] if vdd[0] != 0 else float('inf')
            return 20 * math.log10(1/psrr) if psrr > 0 else float('inf')
        
        return None
    
    def _interpolate_frequency(self, f1: float, f2: float, 
                               m1: float, m2: float, 
                               target: float) -> float:
        """Interpolate frequency at target magnitude."""
        if m1 == m2:
            return f1
        
        # Linear interpolation in log-log space
        log_f1 = math.log10(f1)
        log_f2 = math.log10(f2)
        log_m1 = math.log10(max(m1, 1e-30))
        log_m2 = math.log10(max(m2, 1e-30))
        log_target = math.log10(target)
        
        ratio = (log_target - log_m1) / (log_m2 - log_m1)
        log_f = log_f1 + ratio * (log_f2 - log_f1)
        
        return 10 ** log_f

    def _get_waveform(self, tran_data: Dict[str, Any], node: str) -> List[float]:
        voltage = tran_data.get("voltage", {})
        if isinstance(voltage, dict):
            for key in (node, f"v{node}", "vout" if node == "out" else "vin"):
                values = voltage.get(key)
                if isinstance(values, list):
                    return values

        for key in (node, f"v{node}", "vout" if node == "out" else "vin"):
            values = tran_data.get(key)
            if isinstance(values, list):
                return values

        return []

    def _first_threshold_crossing(self, time: List[float], values: List[float], threshold: float) -> Optional[float]:
        for index in range(1, min(len(time), len(values))):
            if values[index - 1] < threshold <= values[index]:
                return time[index]
        return None
