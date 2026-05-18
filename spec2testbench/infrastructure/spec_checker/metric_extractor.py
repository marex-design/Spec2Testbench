# spec2testbench/infrastructure/spec_checker/metric_extractor.py

"""
MetricExtractor - Extracts metrics from simulation results.
"""

import re
import math
import logging
from typing import Dict, Any, Optional, List

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
        
        # Map metric name to extraction method
        extractors = {
            "dc_gain": self._extract_dc_gain,
            "gain": self._extract_dc_gain,
            "bandwidth": self._extract_bandwidth,
            "gbw": self._extract_gbw,
            "phase_margin": self._extract_phase_margin,
            "slew_rate": self._extract_slew_rate,
            "settling_time": self._extract_settling_time,
            "power": self._extract_power,
            "current": self._extract_current,
            "thd": self._extract_thd,
            "cmrr": self._extract_cmrr,
            "psrr": self._extract_psrr,
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
    
    def _extract_dc_gain(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract DC gain from AC analysis."""
        ac_data = results.get("ac", {})
        magnitude = ac_data.get("magnitude", [])
        
        if magnitude and len(magnitude) > 0:
            # DC gain is magnitude at lowest frequency
            dc_gain_linear = magnitude[0]
            return 20 * math.log10(dc_gain_linear) if dc_gain_linear > 0 else -float('inf')
        
        return None
    
    def _extract_bandwidth(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract -3dB bandwidth from AC analysis."""
        ac_data = results.get("ac", {})
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
        tran_data = results.get("transient", {})
        time = tran_data.get("time", [])
        voltage = tran_data.get("voltage", {})
        
        # Usually look at output node
        vout = voltage.get("out", voltage.get("vout", []))
        
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
        tran_data = results.get("transient", {})
        time = tran_data.get("time", [])
        voltage = tran_data.get("voltage", {})
        
        vout = voltage.get("out", voltage.get("vout", []))
        
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
    
    def _extract_power(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract power consumption."""
        # Get current from VDD source
        currents = results.get("currents", {})
        idd = currents.get("vdd", currents.get("VDD", 0))
        
        # Get voltage
        vdd = results.get("vdd", 1.8)
        
        return vdd * abs(idd)
    
    def _extract_current(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract current consumption."""
        currents = results.get("currents", {})
        return currents.get("vdd", currents.get("VDD", None))
    
    def _extract_thd(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract Total Harmonic Distortion."""
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