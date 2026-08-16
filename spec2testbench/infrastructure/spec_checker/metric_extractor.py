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
        oscillation_status = results.get("oscillation_validation", {}).get("status")
        if metric_lower in {"oscillator_frequency", "frequency_hz", "fundamental_frequency"} and oscillation_status not in {None, "VALID_OSCILLATION"}:
            return None
        native_extraction = results.get("native_extractions", {}).get(metric_lower, {})
        if metric_lower in {"propagation_delay", "propagation_delay_s"} and native_extraction and native_extraction.get("status") != "SUCCESS":
            return None

        direct_value = self._lookup_metric_value(results, self._candidate_names(metric_lower, metric_name))
        if direct_value is not None:
            return direct_value
        
        # Map metric name to extraction method
        extractors = {
            "operating_point": self._extract_operating_point,
            "vout_dc": self._extract_operating_point,
            "quiescent_current": self._extract_current,
            "idd": self._extract_current,
            "dc_transfer_curve": self._extract_dc_transfer_curve,
            "local_gain": self._extract_local_gain,
            "linear_range": self._extract_linear_range,
            "selected_bias": self._extract_selected_bias,
            "bias_objective_score": self._extract_bias_objective_score,
            "dc_gain": self._extract_dc_gain,
            "gain": self._extract_dc_gain,
            "bandwidth": self._extract_bandwidth,
            "cutoff_frequency": self._extract_bandwidth,
            "gbw": self._extract_gbw,
            "ugbw": self._extract_gbw,
            "unity_gain_frequency": self._extract_gbw,
            "phase_margin": self._extract_phase_margin,
            "gain_margin": self._extract_gain_margin,
            "slew_rate": self._extract_slew_rate,
            "settling_time": self._extract_settling_time,
            "overshoot": self._extract_overshoot,
            "sine_response_amplitude": self._extract_sine_response_amplitude,
            "sine_response_phase": self._extract_sine_response_phase,
            "rise_time": self._extract_rise_time,
            "fall_time": self._extract_fall_time,
            "ringing": self._extract_ringing,
            "propagation_delay": self._extract_propagation_delay,
            "v_t_plus": self._extract_v_t_plus,
            "v_t_minus": self._extract_v_t_minus,
            "hysteresis_width": self._extract_hysteresis_width,
            "oscillation_detected": self._extract_oscillation_detected,
            "oscillator_frequency": self._extract_frequency,
            "frequency_hz": self._extract_frequency,
            "fundamental_frequency": self._extract_fundamental_frequency,
            "startup_amplitude": self._extract_startup_amplitude,
            "integrator_ramp_slope": self._extract_integrator_ramp_slope,
            "integrator_linearity": self._extract_integrator_linearity,
            "differentiator_peak": self._extract_differentiator_peak,
            "differentiator_pulse_width": self._extract_differentiator_pulse_width,
            "power": self._extract_power,
            "current": self._extract_current,
            "thd": self._extract_thd,
            "sfdr": self._extract_sfdr,
            "conversion_gain": self._extract_conversion_gain,
            "spurious_components": self._extract_spurious_components,
            "cmrr": self._extract_cmrr,
            "psrr": self._extract_psrr,
            "input_impedance": self._extract_input_impedance,
            "output_impedance": self._extract_output_impedance,
            "input_common_mode_range": self._extract_input_common_mode_range,
            "differential_gain": self._extract_differential_gain,
            "differential_phase": self._extract_differential_phase,
            "current_mirror_matching_error": self._extract_current_mirror_matching_error,
            "inverter_low_input_output_v": self._extract_inverter_low_input_output_v,
            "inverter_high_input_output_v": self._extract_inverter_high_input_output_v,
            "comparator_output_separation_v": self._extract_comparator_output_separation_v,
            "comparator_monotonicity_percent": self._extract_comparator_monotonicity_percent,
            "current_stability_delta_a": self._extract_current_stability_delta_a,
            "lowpass_attenuation_db": self._extract_lowpass_attenuation_db,
            "lowpass_monotonicity_percent": self._extract_lowpass_monotonicity_percent,
            "highpass_attenuation_db": self._extract_highpass_attenuation_db,
            "highpass_monotonicity_percent": self._extract_highpass_monotonicity_percent,
            "bandpass_peak_separation_db": self._extract_bandpass_peak_separation_db,
            "bandstop_notch_depth_db": self._extract_bandstop_notch_depth_db,
            "output_swing_v": self._extract_output_swing_v,
            "oscillation_period_cv": self._extract_oscillation_period_cv,
            "oscillation_cycle_count": self._extract_oscillation_cycle_count,
            "pvt": self._extract_pvt_metric,
        }
        
        # Prefer an exact metric match. For aliases such as ``dc_gain_db`` or
        # ``cutoff_frequency_hz``, fall back to the longest contained key. The
        # old insertion-order substring lookup made ``current_stability_delta_a``
        # accidentally match the generic ``current`` extractor first.
        exact_extractor = extractors.get(metric_lower)
        if exact_extractor is not None:
            return exact_extractor(results)
        for key in sorted(extractors, key=len, reverse=True):
            if key in metric_lower:
                return extractors[key](results)
        
        # Try direct lookup
        if metric_name in results:
            return results[metric_name]
        
        logger.warning(f"Metric '{metric_name}' not found in results")
        return None

    def supports_metric(self, metric_name: str) -> bool:
        metric_lower = metric_name.lower()
        extractors = {
            "operating_point",
            "vout_dc",
            "quiescent_current",
            "idd",
            "dc_gain",
            "gain",
            "dc_transfer_curve",
            "local_gain",
            "linear_range",
            "selected_bias",
            "bias_objective_score",
            "bandwidth",
            "cutoff_frequency",
            "gbw",
            "ugbw",
            "unity_gain_frequency",
            "phase_margin",
            "gain_margin",
            "input_impedance",
            "output_impedance",
            "slew_rate",
            "settling_time",
            "overshoot",
            "sine_response_amplitude",
            "sine_response_phase",
            "rise_time",
            "fall_time",
            "ringing",
            "propagation_delay",
            "v_t_plus",
            "v_t_minus",
            "hysteresis_width",
            "oscillation_detected",
            "oscillator_frequency",
            "frequency_hz",
            "fundamental_frequency",
            "startup_amplitude",
            "integrator_ramp_slope",
            "integrator_linearity",
            "differentiator_peak",
            "differentiator_pulse_width",
            "power",
            "current",
            "thd",
            "sfdr",
            "conversion_gain",
            "spurious_components",
            "cmrr",
            "psrr",
            "input_common_mode_range",
            "differential_gain",
            "differential_phase",
            "current_mirror_matching_error",
            "inverter_low_input_output_v",
            "inverter_high_input_output_v",
            "comparator_output_separation_v",
            "comparator_monotonicity_percent",
            "current_stability_delta_a",
            "lowpass_attenuation_db",
            "lowpass_monotonicity_percent",
            "highpass_attenuation_db",
            "highpass_monotonicity_percent",
            "bandpass_peak_separation_db",
            "bandstop_notch_depth_db",
            "output_swing_v",
            "oscillation_period_cv",
            "oscillation_cycle_count",
            "pvt",
        }
        known_aliases = {
            alias.lower()
            for aliases in (
                self._candidate_names("operating_point", "operating_point"),
                self._candidate_names("quiescent_current", "quiescent_current"),
                self._candidate_names("dc_transfer_curve", "dc_transfer_curve"),
                self._candidate_names("local_gain", "local_gain"),
                self._candidate_names("linear_range", "linear_range"),
                self._candidate_names("selected_bias", "selected_bias"),
                self._candidate_names("bias_objective_score", "bias_objective_score"),
                self._candidate_names("dc_gain", "dc_gain"),
                self._candidate_names("bandwidth", "bandwidth"),
                self._candidate_names("unity_gain_frequency", "unity_gain_frequency"),
                self._candidate_names("phase_margin", "phase_margin"),
                self._candidate_names("gain_margin", "gain_margin"),
                self._candidate_names("input_impedance", "input_impedance"),
                self._candidate_names("output_impedance", "output_impedance"),
                self._candidate_names("overshoot", "overshoot"),
                self._candidate_names("sine_response_amplitude", "sine_response_amplitude"),
                self._candidate_names("sine_response_phase", "sine_response_phase"),
                self._candidate_names("rise_time", "rise_time"),
                self._candidate_names("fall_time", "fall_time"),
                self._candidate_names("ringing", "ringing"),
                self._candidate_names("propagation_delay", "propagation_delay"),
                self._candidate_names("v_t_plus", "v_t_plus"),
                self._candidate_names("v_t_minus", "v_t_minus"),
                self._candidate_names("hysteresis_width", "hysteresis_width"),
                self._candidate_names("oscillation_detected", "oscillation_detected"),
                self._candidate_names("oscillator_frequency", "oscillator_frequency"),
                self._candidate_names("fundamental_frequency", "fundamental_frequency"),
                self._candidate_names("integrator_ramp_slope", "integrator_ramp_slope"),
                self._candidate_names("integrator_linearity", "integrator_linearity"),
                self._candidate_names("differentiator_peak", "differentiator_peak"),
                self._candidate_names("differentiator_pulse_width", "differentiator_pulse_width"),
                self._candidate_names("thd", "thd"),
                self._candidate_names("sfdr", "sfdr"),
                self._candidate_names("conversion_gain", "conversion_gain"),
                self._candidate_names("spurious_components", "spurious_components"),
                self._candidate_names("cmrr", "cmrr"),
                self._candidate_names("psrr", "psrr"),
                self._candidate_names("input_common_mode_range", "input_common_mode_range"),
                self._candidate_names("differential_gain", "differential_gain"),
                self._candidate_names("differential_phase", "differential_phase"),
                self._candidate_names("current_mirror_matching_error", "current_mirror_matching_error"),
                self._candidate_names("pvt_vout_variation", "pvt_vout_variation"),
                self._candidate_names("pvt_dc_gain_variation", "pvt_dc_gain_variation"),
                self._candidate_names("pvt_power_variation", "pvt_power_variation"),
                self._candidate_names("pvt_frequency_variation", "pvt_frequency_variation"),
                self._candidate_names("pvt_delay_variation", "pvt_delay_variation"),
                self._candidate_names("pvt_thd_variation", "pvt_thd_variation"),
            )
            for alias in aliases
        }
        return any(key in metric_lower for key in extractors) or metric_lower in known_aliases

    def _candidate_names(self, metric_lower: str, metric_name: str) -> List[str]:
        aliases = {
            "operating_point": ["vout_dc", "op_point", "op_voltage"],
            "vout_dc": ["operating_point", "op_point", "vout"],
            "quiescent_current": ["idd", "iq", "current", "mean_current_a", "supply_current_a"],
            "idd": ["quiescent_current", "iq", "current", "mean_current_a", "supply_current_a"],
            "power": ["power_w", "power_mw", "quiescent_power_w"],
            "dc_transfer_curve": ["transfer_curve_span", "dc_transfer_span", "output_swing"],
            "local_gain": ["transfer_slope", "incremental_gain"],
            "linear_range": ["linear_input_range", "linear_span"],
            "selected_bias": ["optimal_bias", "best_bias", "bias_value"],
            "bias_objective_score": ["optimal_bias_score", "bias_score"],
            "dc_gain": ["dc_gain_db", "gain_db"],
            "bandwidth": ["cutoff_frequency", "cutoff_frequency_hz", "bw"],
            "unity_gain_frequency": ["ugbw", "gbw"],
            "gbw": ["ugbw", "unity_gain_frequency"],
            "phase_margin": ["phase_margin_deg"],
            "gain_margin": ["gain_margin_db"],
            "input_impedance": ["zin", "input_z", "zin_ohm"],
            "output_impedance": ["zout", "output_z", "zout_ohm"],
            "overshoot": ["percent_overshoot", "step_overshoot"],
            "sine_response_amplitude": ["output_amplitude", "steady_state_amplitude"],
            "sine_response_phase": ["phase_shift_deg", "steady_state_phase"],
            "rise_time": ["trise", "rise_time_s"],
            "fall_time": ["tfall", "fall_time_s"],
            "ringing": ["ringing_percent", "ringing_amplitude"],
            "propagation_delay": ["comparator_delay", "delay", "propagation_delay_s"],
            "v_t_plus": ["vt_plus", "threshold_rising", "upper_threshold"],
            "v_t_minus": ["vt_minus", "threshold_falling", "lower_threshold"],
            "hysteresis_width": ["hysteresis", "schmitt_hysteresis"],
            "oscillation_detected": ["oscillation_validated", "oscillation_present"],
            "oscillator_frequency": ["frequency_hz", "fundamental_frequency"],
            "frequency_hz": ["oscillator_frequency", "fundamental_frequency"],
            "fundamental_frequency": ["frequency_hz", "oscillator_frequency"],
            "integrator_ramp_slope": ["ramp_slope", "integrator_slope"],
            "integrator_linearity": ["ramp_linearity", "linearity_score"],
            "differentiator_peak": ["impulse_peak", "pulse_peak"],
            "differentiator_pulse_width": ["impulse_width", "pulse_width"],
            "thd": ["thd_percent"],
            "sfdr": ["sfdr_db"],
            "conversion_gain": ["mixer_conversion_gain", "conversion_gain_db"],
            "spurious_components": ["largest_spur_dbc", "spur_amplitude"],
            "input_common_mode_range": ["icmr", "common_mode_range"],
            "differential_gain": ["diff_gain", "differential_gain_db"],
            "differential_phase": ["diff_phase", "differential_phase_deg"],
            "current_mirror_matching_error": ["mirror_matching_error", "delta_i_over_i"],
            "pvt_vout_variation": ["vout_variation"],
            "pvt_dc_gain_variation": ["gain_variation"],
            "pvt_power_variation": ["power_variation"],
            "pvt_frequency_variation": ["frequency_variation"],
            "pvt_delay_variation": ["delay_variation"],
            "pvt_thd_variation": ["thd_variation"],
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

    def _extract_dc_transfer_curve(self, results: Dict[str, Any]) -> Optional[float]:
        vin, vout = self._dc_transfer_series(results)
        if len(vin) < 2 or len(vout) < 2:
            return None
        return max(vout) - min(vout)

    def _extract_local_gain(self, results: Dict[str, Any]) -> Optional[float]:
        vin, vout = self._dc_transfer_series(results)
        if len(vin) < 2 or len(vout) < 2:
            return None
        slopes = []
        for index in range(1, min(len(vin), len(vout))):
            dv = vout[index] - vout[index - 1]
            di = vin[index] - vin[index - 1]
            if di != 0:
                slopes.append(abs(dv / di))
        return max(slopes) if slopes else None

    def _extract_linear_range(self, results: Dict[str, Any]) -> Optional[float]:
        vin, vout = self._dc_transfer_series(results)
        if len(vin) < 3 or len(vout) < 3:
            return None
        slopes = []
        for index in range(1, min(len(vin), len(vout))):
            dv = vout[index] - vout[index - 1]
            di = vin[index] - vin[index - 1]
            if di != 0:
                slopes.append(dv / di)
        if not slopes:
            return None
        mean_slope = sum(slopes) / len(slopes)
        tolerance = max(abs(mean_slope) * 0.2, 1e-12)
        valid_points = [vin[0]]
        for index, slope in enumerate(slopes, start=1):
            if abs(slope - mean_slope) <= tolerance:
                valid_points.append(vin[index])
        if len(valid_points) < 2:
            return None
        return max(valid_points) - min(valid_points)

    def _extract_selected_bias(self, results: Dict[str, Any]) -> Optional[float]:
        direct = self._lookup_metric_value(results, ("selected_bias", "optimal_bias", "best_bias", "bias_value"))
        if direct is not None:
            return direct
        vin, vout = self._dc_transfer_series(results)
        if len(vin) != len(vout) or len(vin) < 2:
            return None
        vdd = self._lookup_metric_value(results, ("vdd", "supply_voltage", "nominal_supply")) or 1.8
        target = vdd / 2.0
        best_index = min(range(len(vout)), key=lambda idx: abs(vout[idx] - target))
        return vin[best_index]

    def _extract_bias_objective_score(self, results: Dict[str, Any]) -> Optional[float]:
        direct = self._lookup_metric_value(results, ("bias_objective_score", "optimal_bias_score", "bias_score"))
        if direct is not None:
            return direct
        vin, vout = self._dc_transfer_series(results)
        if len(vin) != len(vout) or len(vin) < 2:
            return None
        vdd = self._lookup_metric_value(results, ("vdd", "supply_voltage", "nominal_supply")) or 1.8
        target = vdd / 2.0
        best_error = min(abs(value - target) for value in vout)
        scale = max(vdd / 2.0, 1e-12)
        return max(0.0, 1.0 - (best_error / scale))
    
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

    def _extract_gain_margin(self, results: Dict[str, Any]) -> Optional[float]:
        direct_gain_margin = self._lookup_metric_value(results, ("gain_margin", "gain_margin_db"))
        if direct_gain_margin is not None:
            return direct_gain_margin
        ac_data = results.get("ac", {})
        phase = ac_data.get("phase", [])
        magnitude = ac_data.get("magnitude", [])
        if not phase or not magnitude:
            return None
        for index, phase_value in enumerate(phase):
            if phase_value <= -180.0 and index < len(magnitude):
                gain = abs(magnitude[index])
                if gain <= 0:
                    return None
                return -20.0 * math.log10(gain)
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

    def _extract_overshoot(self, results: Dict[str, Any]) -> Optional[float]:
        direct_overshoot = self._lookup_metric_value(results, ("overshoot", "percent_overshoot", "step_overshoot"))
        if direct_overshoot is not None:
            return direct_overshoot
        tran_data = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran_data, "out")
        if len(vout) < 4:
            return None
        initial = vout[0]
        final = vout[-1]
        step_amplitude = final - initial
        if abs(step_amplitude) <= 1e-15:
            return 0.0
        peak = max(vout) if step_amplitude > 0 else min(vout)
        overshoot = (peak - final) / step_amplitude if step_amplitude > 0 else (final - peak) / abs(step_amplitude)
        return max(0.0, overshoot * 100.0)

    def _extract_sine_response_amplitude(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("sine_response_amplitude", "output_amplitude", "steady_state_amplitude"))
        if direct_value is not None:
            return direct_value
        steady_state = self._steady_state_waveform(results, "out")
        if len(steady_state) < 4:
            return None
        return (max(steady_state) - min(steady_state)) / 2.0

    def _extract_sine_response_phase(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("sine_response_phase", "phase_shift_deg", "steady_state_phase"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vin = self._get_waveform(tran_data, "in")
        vout = self._get_waveform(tran_data, "out")
        if len(time) < 4 or len(vin) != len(vout):
            return None
        vin_cross = self._first_mean_crossing(time, vin)
        vout_cross = self._first_mean_crossing(time, vout)
        frequency = self._extract_fundamental_frequency(results)
        if vin_cross is None or vout_cross is None or frequency is None or frequency <= 0:
            return None
        period = 1.0 / frequency
        return ((vout_cross - vin_cross) / period) * 360.0

    def _extract_rise_time(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("rise_time", "trise", "rise_time_s"))
        if direct_value is not None:
            return direct_value
        return self._edge_time(results, rising=True)

    def _extract_fall_time(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("fall_time", "tfall", "fall_time_s"))
        if direct_value is not None:
            return direct_value
        return self._edge_time(results, rising=False)

    def _extract_ringing(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("ringing", "ringing_percent", "ringing_amplitude"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran_data, "out")
        if len(vout) < 8:
            return None
        initial = vout[0]
        final = vout[-1]
        step_amplitude = abs(final - initial)
        if step_amplitude <= 1e-15:
            return 0.0
        tail = vout[max(1, int(len(vout) * 0.7)):]
        peak_error = max(abs(value - final) for value in tail)
        return (peak_error / step_amplitude) * 100.0

    def _extract_propagation_delay(self, results: Dict[str, Any]) -> Optional[float]:
        direct_delay = self._lookup_metric_value(results, ("propagation_delay", "propagation_delay_s", "comparator_delay", "delay"))
        if direct_delay is not None:
            return direct_delay
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vin = self._get_waveform(tran_data, "in")
        vout = self._get_waveform(tran_data, "out")

        if not time or not vin or not vout:
            return None

        transitions = self._extract_transition_metrics(time, vin, vout)
        propagation_delay = transitions.get("propagation_delay")
        if propagation_delay is None:
            return None
        return float(propagation_delay)

    def _extract_v_t_plus(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("v_t_plus", "vt_plus", "threshold_rising", "upper_threshold"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        transitions = self._extract_transition_metrics(
            tran_data.get("time", []),
            self._get_waveform(tran_data, "in"),
            self._get_waveform(tran_data, "out"),
        )
        return transitions.get("v_t_plus")

    def _extract_v_t_minus(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("v_t_minus", "vt_minus", "threshold_falling", "lower_threshold"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        transitions = self._extract_transition_metrics(
            tran_data.get("time", []),
            self._get_waveform(tran_data, "in"),
            self._get_waveform(tran_data, "out"),
        )
        return transitions.get("v_t_minus")

    def _extract_hysteresis_width(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("hysteresis_width", "schmitt_hysteresis", "hysteresis"))
        if direct_value is not None:
            return direct_value
        v_t_plus = self._extract_v_t_plus(results)
        v_t_minus = self._extract_v_t_minus(results)
        if v_t_plus is None or v_t_minus is None:
            return None
        return abs(v_t_plus - v_t_minus)

    def _extract_frequency(self, results: Dict[str, Any]) -> Optional[float]:
        oscillation_status = results.get("oscillation_validation", {}).get("status")
        if oscillation_status not in {None, "VALID_OSCILLATION"}:
            return None
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

    def _extract_fundamental_frequency(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("fundamental_frequency", "frequency_hz", "oscillator_frequency"))
        if direct_value is not None:
            return direct_value
        fourier = results.get("fourier", {})
        fundamental = fourier.get("fundamental_frequency")
        if isinstance(fundamental, (int, float)):
            return float(fundamental)
        return self._extract_frequency(results)

    def _extract_oscillation_detected(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("oscillation_detected", "oscillation_validated", "oscillation_present"))
        if direct_value is not None:
            return 1.0 if float(direct_value) > 0 else 0.0
        status = results.get("oscillation_validation", {}).get("status")
        if status is None:
            frequency = self._extract_frequency(results)
            amplitude = self._extract_startup_amplitude(results)
            if frequency is None or amplitude is None:
                return None
            return 1.0 if amplitude > 0 else 0.0
        return 1.0 if status == "VALID_OSCILLATION" else 0.0

    def _extract_startup_amplitude(self, results: Dict[str, Any]) -> Optional[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran_data, "out")
        if len(vout) < 5:
            return None
        tail_start = max(0, int(len(vout) * 0.8))
        steady_state = vout[tail_start:]
        return (max(steady_state) - min(steady_state)) / 2

    def _extract_integrator_ramp_slope(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("integrator_ramp_slope", "ramp_slope", "integrator_slope"))
        if direct_value is not None:
            return direct_value
        fit = self._linear_fit_waveform(results)
        if fit is None:
            return None
        slope, _intercept, _r2 = fit
        return slope

    def _extract_integrator_linearity(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("integrator_linearity", "ramp_linearity", "linearity_score"))
        if direct_value is not None:
            return direct_value
        fit = self._linear_fit_waveform(results)
        if fit is None:
            return None
        _slope, _intercept, r2 = fit
        return r2

    def _extract_differentiator_peak(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("differentiator_peak", "impulse_peak", "pulse_peak"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran_data, "out")
        if not vout:
            return None
        mean = sum(vout) / len(vout)
        return max(abs(value - mean) for value in vout)

    def _extract_differentiator_pulse_width(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("differentiator_pulse_width", "impulse_width", "pulse_width"))
        if direct_value is not None:
            return direct_value
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        vout = self._get_waveform(tran_data, "out")
        if len(time) < 3 or len(vout) < 3:
            return None
        mean = sum(vout) / len(vout)
        centered = [abs(value - mean) for value in vout]
        peak = max(centered)
        if peak <= 0:
            return 0.0
        threshold = peak / 2.0
        active = [time[index] for index, value in enumerate(centered) if value >= threshold]
        if len(active) < 2:
            return None
        return active[-1] - active[0]
    
    def _extract_power(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract power consumption."""
        direct_power = self._lookup_metric_value(results, ("power", "power_w", "power_mw", "quiescent_power_w"))
        if direct_power is not None:
            return direct_power
        mean_current = self._lookup_metric_value(results, ("mean_current_a", "quiescent_current", "idd", "iq", "current"))
        if mean_current is not None:
            return results.get("vdd", 1.8) * abs(mean_current)
        # Get current from VDD source
        currents = results.get("currents", {})
        idd = currents.get("vdd", currents.get("VDD", 0))
        
        # Get voltage
        vdd = results.get("vdd", 1.8)
        
        return vdd * abs(idd)
    
    def _extract_current(self, results: Dict[str, Any]) -> Optional[float]:
        """Extract current consumption."""
        direct_current = self._lookup_metric_value(results, ("quiescent_current", "idd", "iq", "current", "mean_current_a", "supply_current_a"))
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

    def _extract_sfdr(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("sfdr", "sfdr_db"))
        if direct_value is not None:
            return direct_value
        harmonics = self._harmonic_magnitudes(results)
        if len(harmonics) < 2:
            return None
        fundamental = harmonics[0]
        largest_spur = max(harmonics[1:])
        if largest_spur <= 0 or fundamental <= 0:
            return None
        return 20.0 * math.log10(fundamental / largest_spur)

    def _extract_conversion_gain(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("conversion_gain", "mixer_conversion_gain", "conversion_gain_db"))
        if direct_value is not None:
            return direct_value
        harmonics = self._harmonic_magnitudes(results)
        if not harmonics:
            return None
        output_amplitude = harmonics[0]
        input_amplitude = self._lookup_metric_value(results, ("input_amplitude", "rf_input_amplitude", "reference_input_amplitude")) or 1.0
        if output_amplitude <= 0 or input_amplitude <= 0:
            return None
        return 20.0 * math.log10(output_amplitude / input_amplitude)

    def _extract_spurious_components(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("spurious_components", "largest_spur_dbc", "spur_amplitude"))
        if direct_value is not None:
            return direct_value
        harmonics = self._harmonic_magnitudes(results)
        if len(harmonics) < 2:
            return None
        fundamental = harmonics[0]
        largest_spur = max(harmonics[1:])
        if largest_spur <= 0 or fundamental <= 0:
            return None
        return 20.0 * math.log10(largest_spur / fundamental)

    def _extract_inverter_low_input_output_v(self, results: Dict[str, Any]) -> Optional[float]:
        _vin, vout = self._dc_transfer_series(results)
        return float(vout[0]) if vout else None

    def _extract_inverter_high_input_output_v(self, results: Dict[str, Any]) -> Optional[float]:
        _vin, vout = self._dc_transfer_series(results)
        return float(vout[-1]) if vout else None

    def _extract_comparator_output_separation_v(self, results: Dict[str, Any]) -> Optional[float]:
        vin, vout = self._dc_transfer_series(results)
        if len(vin) < 6 or len(vout) != len(vin):
            return None
        lo = min(vin); hi = max(vin); span = hi - lo
        if span <= 0:
            return None
        # ACP Comparator.py uses Vref ±0.5 V for a 0..5 V sweep, i.e. the
        # outer 40% regions when Vref=2.5 V. Generalize this geometry.
        lower_limit = lo + 0.4 * span
        upper_limit = lo + 0.6 * span
        low_values = [y for x, y in zip(vin, vout) if x <= lower_limit]
        high_values = [y for x, y in zip(vin, vout) if x >= upper_limit]
        if not low_values or not high_values:
            return None
        return float(abs(sum(high_values)/len(high_values) - sum(low_values)/len(low_values)))

    def _extract_comparator_monotonicity_percent(self, results: Dict[str, Any]) -> Optional[float]:
        _vin, vout = self._dc_transfer_series(results)
        if len(vout) < 3:
            return None
        deltas = [vout[i + 1] - vout[i] for i in range(len(vout) - 1)]
        # The upstream comparator checker accepts either monotonic direction,
        # with a 0.1 V numerical tolerance on local reversals.
        nondecreasing = sum(delta >= -0.1 for delta in deltas)
        nonincreasing = sum(delta <= 0.1 for delta in deltas)
        return 100.0 * max(nondecreasing, nonincreasing) / len(deltas)

    def _extract_current_stability_delta_a(self, results: Dict[str, Any]) -> Optional[float]:
        dc = results.get("dc", {}) or {}
        waveforms = dc.get("current_waveforms", {}) if isinstance(dc.get("current_waveforms", {}), dict) else {}
        candidates = []
        for key, values in waveforms.items():
            if isinstance(values, list) and len(values) >= 2:
                candidates.append([abs(float(x)) for x in values])
        if not candidates:
            return None
        # Prefer supply/reference current traces with a non-zero current.
        values = max(candidates, key=lambda arr: max(arr) if arr else 0.0)
        return float(max(values) - min(values))

    def _ac_frequency_magnitude(self, results: Dict[str, Any]):
        ac = results.get("ac", {}) or {}
        try:
            frequency = [float(x) for x in ac.get("frequency", [])]
            magnitude = [abs(float(x)) for x in ac.get("magnitude", [])]
        except (TypeError, ValueError):
            return [], []
        n = min(len(frequency), len(magnitude))
        return frequency[:n], magnitude[:n]

    @staticmethod
    def _db(value: float) -> float:
        return 20.0 * math.log10(max(abs(float(value)), 1e-30))

    def _extract_lowpass_attenuation_db(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 2:
            return None
        return self._db(magnitude[0]) - self._db(magnitude[-1])

    def _extract_lowpass_monotonicity_percent(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 3:
            return None
        db = [self._db(x) for x in magnitude]
        good = sum((db[i + 1] - db[i]) <= 0.5 for i in range(len(db) - 1))
        return 100.0 * good / (len(db) - 1)

    def _extract_highpass_attenuation_db(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 2:
            return None
        return self._db(magnitude[-1]) - self._db(magnitude[0])

    def _extract_highpass_monotonicity_percent(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 3:
            return None
        db = [self._db(x) for x in magnitude]
        good = sum((db[i + 1] - db[i]) >= -0.5 for i in range(len(db) - 1))
        return 100.0 * good / (len(db) - 1)

    def _extract_bandpass_peak_separation_db(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 5:
            return None
        db = [self._db(x) for x in magnitude]
        peak_i = max(range(len(db)), key=db.__getitem__)
        if peak_i == 0 or peak_i == len(db) - 1:
            return None
        peak = db[peak_i]
        left_avg = sum(db[:peak_i]) / peak_i
        right = db[peak_i + 1:]
        right_avg = sum(right) / len(right)
        return min(peak - left_avg, peak - right_avg)

    def _extract_bandstop_notch_depth_db(self, results: Dict[str, Any]) -> Optional[float]:
        _frequency, magnitude = self._ac_frequency_magnitude(results)
        if len(magnitude) < 5:
            return None
        db = [self._db(x) for x in magnitude]
        notch_i = min(range(len(db)), key=db.__getitem__)
        if notch_i == 0 or notch_i == len(db) - 1:
            return None
        notch = db[notch_i]
        left_avg = sum(db[:notch_i]) / notch_i
        right = db[notch_i + 1:]
        right_avg = sum(right) / len(right)
        return min(left_avg - notch, right_avg - notch)

    def _extract_output_swing_v(self, results: Dict[str, Any]) -> Optional[float]:
        tran = results.get("transient") or results.get("tran", {})
        vout = self._get_waveform(tran, "out")
        if len(vout) >= 2:
            return float(max(vout) - min(vout))
        dc = results.get("dc", {}) or {}
        values = dc.get("vout_values") or dc.get("vout_waveform")
        if isinstance(values, (list, tuple)) and len(values) >= 2:
            vals = [float(x) for x in values]
            return float(max(vals) - min(vals))
        return None

    def _oscillation_periods(self, results: Dict[str, Any]) -> List[float]:
        tran = results.get("transient") or results.get("tran", {})
        time = [float(x) for x in tran.get("time", [])]
        vout = self._get_waveform(tran, "out")
        if len(time) < 4 or len(time) != len(vout):
            return []
        start = max(0, len(vout) // 2)
        t = time[start:]
        y = vout[start:]
        if len(y) < 4:
            return []
        mean = sum(y) / len(y)
        crossings = []
        for i in range(1, len(y)):
            if y[i - 1] <= mean < y[i]:
                crossings.append(t[i])
        return [crossings[i] - crossings[i-1] for i in range(1, len(crossings)) if crossings[i] > crossings[i-1]]

    def _extract_oscillation_period_cv(self, results: Dict[str, Any]) -> Optional[float]:
        periods = self._oscillation_periods(results)
        if len(periods) < 2:
            return None
        mean = sum(periods) / len(periods)
        if mean <= 0:
            return None
        variance = sum((p - mean) ** 2 for p in periods) / len(periods)
        return math.sqrt(variance) / mean

    def _extract_oscillation_cycle_count(self, results: Dict[str, Any]) -> Optional[float]:
        periods = self._oscillation_periods(results)
        return float(len(periods) + 1) if periods else None

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

    def _extract_input_impedance(self, results: Dict[str, Any]) -> Optional[float]:
        return self._lookup_metric_value(results, ("input_impedance", "zin", "input_z", "zin_ohm"))

    def _extract_output_impedance(self, results: Dict[str, Any]) -> Optional[float]:
        return self._lookup_metric_value(results, ("output_impedance", "zout", "output_z", "zout_ohm"))

    def _extract_input_common_mode_range(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("input_common_mode_range", "icmr", "common_mode_range"))
        if direct_value is not None:
            return direct_value
        vin, vout = self._dc_transfer_series(results)
        if len(vin) < 2 or len(vout) < 2:
            return None
        valid_inputs = [vin_value for vin_value, vout_value in zip(vin, vout) if math.isfinite(vout_value)]
        if len(valid_inputs) < 2:
            return None
        return max(valid_inputs) - min(valid_inputs)

    def _extract_differential_gain(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("differential_gain", "diff_gain", "differential_gain_db"))
        if direct_value is not None:
            return direct_value
        ac_data = results.get("ac", {})
        gains = ac_data.get("differential_gain", [])
        if gains:
            return float(gains[0])
        return self._extract_dc_gain(results)

    def _extract_differential_phase(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("differential_phase", "diff_phase", "differential_phase_deg"))
        if direct_value is not None:
            return direct_value
        ac_data = results.get("ac", {})
        phases = ac_data.get("differential_phase", [])
        if phases:
            return float(phases[0])
        phase = ac_data.get("phase", [])
        if phase:
            return float(phase[0])
        return None

    def _extract_current_mirror_matching_error(self, results: Dict[str, Any]) -> Optional[float]:
        direct_value = self._lookup_metric_value(results, ("current_mirror_matching_error", "mirror_matching_error", "delta_i_over_i"))
        if direct_value is not None:
            return direct_value
        currents = results.get("currents", {})
        if not isinstance(currents, dict):
            return None
        numeric_currents = [float(value) for value in currents.values() if isinstance(value, (int, float)) and abs(float(value)) > 0]
        if len(numeric_currents) < 2:
            return None
        reference = abs(numeric_currents[0])
        mirrored = abs(numeric_currents[1])
        if reference <= 1e-15:
            return None
        return abs(mirrored - reference) / reference

    def _dc_transfer_series(self, results: Dict[str, Any]) -> tuple[List[float], List[float]]:
        dc_data = results.get("dc", {})
        if not isinstance(dc_data, dict):
            return [], []
        voltage = dc_data.get("voltage", {}) if isinstance(dc_data.get("voltage", {}), dict) else {}
        vin_candidates = [
            dc_data.get("vin"),
            dc_data.get("input"),
            dc_data.get("sweep"),
            dc_data.get("source_values"),
            voltage.get("vin"),
            voltage.get("in"),
        ]
        vout_candidates = [
            dc_data.get("vout"),
            dc_data.get("vout_values"),
            dc_data.get("vout_waveform"),
            dc_data.get("output"),
            voltage.get("vout"),
            voltage.get("out"),
        ]
        vin = next((self._coerce_float_list(values) for values in vin_candidates if self._coerce_float_list(values)), [])
        vout = next((self._coerce_float_list(values) for values in vout_candidates if self._coerce_float_list(values)), [])
        return vin, vout

    @staticmethod
    def _coerce_float_list(values: Any) -> List[float]:
        if not isinstance(values, list):
            return []
        coerced = []
        for value in values:
            if isinstance(value, (int, float)):
                coerced.append(float(value))
            else:
                return []
        return coerced

    def _steady_state_waveform(self, results: Dict[str, Any], node: str) -> List[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        values = self._get_waveform(tran_data, node)
        if len(values) < 5:
            return values
        start = max(0, int(len(values) * 0.7))
        return values[start:]

    @staticmethod
    def _first_mean_crossing(time: List[float], values: List[float]) -> Optional[float]:
        if len(time) < 2 or len(values) < 2:
            return None
        mean_value = sum(values) / len(values)
        for index in range(1, min(len(time), len(values))):
            if values[index - 1] <= mean_value < values[index]:
                return float(time[index])
        return None

    def _edge_time(self, results: Dict[str, Any], *, rising: bool) -> Optional[float]:
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        values = self._get_waveform(tran_data, "out")
        if len(time) < 3 or len(values) < 3:
            return None
        low = min(values)
        high = max(values)
        if abs(high - low) <= 1e-15:
            return 0.0
        lower = low + 0.1 * (high - low)
        upper = low + 0.9 * (high - low)
        first_time = None
        second_time = None
        for index in range(1, min(len(time), len(values))):
            previous = values[index - 1]
            current = values[index]
            if rising:
                if first_time is None and previous <= lower < current:
                    first_time = float(time[index])
                if previous <= upper < current:
                    second_time = float(time[index])
                    break
            else:
                if first_time is None and previous >= upper > current:
                    first_time = float(time[index])
                if previous >= lower > current:
                    second_time = float(time[index])
                    break
        if first_time is None or second_time is None:
            return None
        return max(0.0, second_time - first_time)

    def _linear_fit_waveform(self, results: Dict[str, Any]) -> Optional[tuple[float, float, float]]:
        tran_data = results.get("transient") or results.get("tran", {})
        time = tran_data.get("time", [])
        values = self._get_waveform(tran_data, "out")
        if len(time) < 4 or len(values) < 4 or len(time) != len(values):
            return None
        start = int(len(time) * 0.1)
        stop = max(start + 2, int(len(time) * 0.9))
        xs = [float(value) for value in time[start:stop]]
        ys = [float(value) for value in values[start:stop]]
        if len(xs) < 2:
            return None
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator <= 1e-30:
            return None
        slope = numerator / denominator
        intercept = mean_y - slope * mean_x
        ss_tot = sum((y - mean_y) ** 2 for y in ys)
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r2 = 1.0 if ss_tot <= 1e-30 else max(0.0, 1.0 - (ss_res / ss_tot))
        return slope, intercept, r2

    def _harmonic_magnitudes(self, results: Dict[str, Any]) -> List[float]:
        fourier = results.get("fourier", {})
        harmonics = fourier.get("harmonics", [])
        magnitudes: List[float] = []
        for harmonic in harmonics:
            if not isinstance(harmonic, dict):
                continue
            magnitude = harmonic.get("magnitude")
            if isinstance(magnitude, (int, float)) and magnitude > 0:
                magnitudes.append(float(magnitude))
        return magnitudes
    
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

    def _extract_transition_metrics(self, time: List[float], vin: List[float], vout: List[float]) -> Dict[str, float]:
        if len(time) < 2 or len(vin) < 2 or len(vout) < 2:
            return {}

        sample_count = min(len(time), len(vin), len(vout))
        time = time[:sample_count]
        vin = vin[:sample_count]
        vout = vout[:sample_count]
        vout_threshold = (max(vout) + min(vout)) / 2

        output_events = []
        for index in range(1, sample_count):
            previous = vout[index - 1]
            current = vout[index]
            if previous < vout_threshold <= current:
                output_events.append(("rising", index))
            elif previous > vout_threshold >= current:
                output_events.append(("falling", index))

        if not output_events:
            return {}

        transition_metrics: Dict[str, float] = {}
        input_slopes = [vin[index] - vin[index - 1] for index in range(1, sample_count)]

        for direction, index in output_events:
            vin_at_transition = float(vin[index])
            if direction == "rising" and "v_t_plus" not in transition_metrics:
                transition_metrics["v_t_plus"] = vin_at_transition
            if direction == "falling" and "v_t_minus" not in transition_metrics:
                transition_metrics["v_t_minus"] = vin_at_transition

            output_time = float(time[index])
            desired_sign = 1 if direction == "rising" else -1
            input_index = None
            for candidate in range(index, 0, -1):
                slope = input_slopes[candidate - 1]
                if desired_sign * slope > 0:
                    input_index = candidate
                    break
            if input_index is not None and "propagation_delay" not in transition_metrics:
                transition_metrics["propagation_delay"] = max(0.0, output_time - float(time[input_index]))

        v_t_plus = transition_metrics.get("v_t_plus")
        v_t_minus = transition_metrics.get("v_t_minus")
        if v_t_plus is not None and v_t_minus is not None:
            transition_metrics["hysteresis_width"] = abs(v_t_plus - v_t_minus)

        return transition_metrics
