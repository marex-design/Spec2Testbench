# spec2testbench/infrastructure/spec_checker/spec_checker.py

"""
SpecChecker - Implementation of ISpecChecker.
Verifies simulation results against specifications.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from ...domain.entities.specification import Specification
from ...domain.value_objects.verdict import Verdict, CheckResult
from ...domain.interfaces.ispec_checker import ISpecChecker
from .metric_extractor import MetricExtractor

logger = logging.getLogger(__name__)


class SpecChecker(ISpecChecker):
    """
    Implementation of specification checker.
    
    This checker:
    1. Extracts metrics from simulation results
    2. Compares against specification targets
    3. Generates PASS/FAIL/WARNING verdicts
    4. Produces detailed diagnostic messages
    """
    
    # Default unit conversion factors
    UNIT_CONVERSION = {
        # Frequency
        "hz": 1, "khz": 1e3, "mhz": 1e6, "ghz": 1e9,
        # Voltage
        "v": 1, "mv": 1e-3, "uv": 1e-6,
        # Current
        "a": 1, "ma": 1e-3, "ua": 1e-6, "na": 1e-9,
        # Power
        "w": 1, "mw": 1e-3, "uw": 1e-6,
        # Time
        "s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12,
        # Resistance
        "ohm": 1, "kohm": 1e3, "mohm": 1e6,
        # Capacitance
        "f": 1, "pf": 1e-12, "nf": 1e-9, "uf": 1e-6,
    }
    
    # Warning margin (percentage close to limit that triggers WARNING)
    WARNING_MARGIN = 0.05  # 5%
    ABSOLUTE_TOLERANCE = 1e-12
    
    def __init__(self, warning_margin: float = 0.05):
        """
        Initialize the spec checker.
        
        Args:
            warning_margin: Margin (0-1) for triggering WARNING instead of PASS
                           Example: 0.05 means values within 5% of limit are WARNING
        """
        self.warning_margin = warning_margin
        self.metric_extractor = MetricExtractor()
    
    def verify(self, 
               simulation_results: Dict[str, Any],
               specification: Specification) -> List[CheckResult]:
        """
        Verify simulation results against specifications.
        
        Args:
            simulation_results: Raw simulation results
            specification: Expected specifications
            
        Returns:
            List of CheckResult for each metric
        """
        logger.info(f"Verifying {len(specification.performance_targets)} metrics")
        
        # Extract metrics from simulation results
        extracted = self.extract_metrics(simulation_results, specification)
        
        # Verify each metric
        results = []
        for metric_name, expected in specification.performance_targets.items():
            measured = extracted.get(metric_name)
            result = self.verify_single_metric(
                metric_name, measured, specification
            )
            results.append(result)
        
        # Log summary
        pass_count = sum(1 for r in results if r.verdict == Verdict.PASS)
        fail_count = sum(1 for r in results if r.verdict == Verdict.FAIL)
        warning_count = sum(1 for r in results if r.verdict == Verdict.WARNING)
        
        logger.info(f"Verification complete: {pass_count} pass, {warning_count} warning, {fail_count} fail")
        
        return results
    
    def verify_single_metric(self,
                             metric_name: str,
                             measured_value: Optional[float],
                             specification: Specification) -> CheckResult:
        """
        Verify a single metric against specification.
        
        Args:
            metric_name: Name of the metric
            measured_value: Value from simulation (None if not found)
            specification: Specifications containing expected values
            
        Returns:
            CheckResult with verdict
        """
        # Get expected values
        target = specification.get_metric(metric_name)
        
        if target is None:
            return CheckResult(
                test_name=metric_name,
                verdict=Verdict.NOT_APPLICABLE,
                measured_value=measured_value,
                message=f"Metric '{metric_name}' not in specification",
                category=self._get_metric_category(metric_name)
            )
        
        # Extract min, max, unit
        expected_min = target.get("min") if isinstance(target, dict) else target
        expected_max = target.get("max") if isinstance(target, dict) else None
        unit = target.get("unit", "") if isinstance(target, dict) else ""
        
        # Handle missing measured value
        if measured_value is None:
            return CheckResult(
                test_name=metric_name,
                verdict=Verdict.ERROR,
                measured_value=None,
                expected_min=expected_min,
                expected_max=expected_max,
                unit=unit,
                message=f"Metric '{metric_name}' could not be extracted from simulation",
                category=self._get_metric_category(metric_name)
            )
        
        # Convert units to SI for comparison
        measured_si = self._to_si(measured_value, unit)
        expected_min_si = self._to_si(expected_min, unit) if expected_min is not None else None
        expected_max_si = self._to_si(expected_max, unit) if expected_max is not None else None
        
        # Determine verdict
        verdict, message = self._compute_verdict(
            metric_name, measured_si, expected_min_si, expected_max_si, unit
        )
        
        return CheckResult(
            test_name=metric_name,
            verdict=verdict,
            measured_value=measured_si,
            expected_min=expected_min_si,
            expected_max=expected_max_si,
            unit=unit,
            message=message,
            category=self._get_metric_category(metric_name)
        )
    
    def extract_metrics(self, 
                        simulation_results: Dict[str, Any],
                        specification: Specification) -> Dict[str, float]:
        """
        Extract metrics from simulation results.
        
        Args:
            simulation_results: Raw simulation results
            specification: Specifications to know which metrics to extract
            
        Returns:
            Dictionary of metric_name -> value
        """
        metrics = {}
        
        for metric_name in specification.performance_targets.keys():
            value = self.metric_extractor.extract(
                simulation_results, metric_name
            )
            if value is not None:
                metrics[metric_name] = value
        
        return metrics
    
    def generate_assertions(self, specification: Specification) -> str:
        """
        Generate executable assertion code from specifications.
        
        Args:
            specification: Specifications
            
        Returns:
            Python code with assertion functions
        """
        code_lines = [
            "# Auto-generated by SpecChecker",
            "# DO NOT EDIT MANUALLY",
            "",
            "from typing import Dict, Any, Tuple",
            "",
            "",
        ]
        
        for metric_name, target in specification.performance_targets.items():
            expected_min = target.get("min") if isinstance(target, dict) else target
            expected_max = target.get("max") if isinstance(target, dict) else None
            unit = target.get("unit", "") if isinstance(target, dict) else ""
            
            code_lines.append(f"def check_{metric_name}(measured: float) -> Tuple[bool, str]:")
            code_lines.append(f'    """Check {metric_name} specification."""')
            
            if expected_min is not None:
                code_lines.append(f"    if measured < {expected_min}:")
                code_lines.append(f"        return False, f'{metric_name} measured={{measured}} < {expected_min} {unit}'")
            
            if expected_max is not None:
                code_lines.append(f"    if measured > {expected_max}:")
                code_lines.append(f"        return False, f'{metric_name} measured={{measured}} > {expected_max} {unit}'")
            
            code_lines.append(f"    return True, f'{metric_name} measured={{measured}} {unit}'")
            code_lines.append("")
        
        # Main verification function
        code_lines.append("")
        code_lines.append("def verify_all(metrics: Dict[str, float]) -> Dict[str, Any]:")
        code_lines.append('    """Verify all metrics against specifications."""')
        code_lines.append("    results = {}")
        code_lines.append("    all_pass = True")
        code_lines.append("")
        
        for metric_name in specification.performance_targets.keys():
            code_lines.append(f"    if '{metric_name}' in metrics:")
            code_lines.append(f"        passed, msg = check_{metric_name}(metrics['{metric_name}'])")
            code_lines.append(f"        results['{metric_name}'] = {{'passed': passed, 'message': msg}}")
            code_lines.append("        all_pass = all_pass and passed")
            code_lines.append("")
        
        code_lines.append("    return {'all_pass': all_pass, 'results': results}")
        
        return "\n".join(code_lines)
    
    def get_failed_metrics(self, 
                           check_results: List[CheckResult]) -> List[CheckResult]:
        """Return only failed metrics (FAIL and WARNING)."""
        return [r for r in check_results if r.verdict in [Verdict.FAIL, Verdict.WARNING]]
    
    def summary(self, check_results: List[CheckResult]) -> dict:
        """Generate summary of verification results."""
        pass_count = sum(1 for r in check_results if r.verdict == Verdict.PASS)
        fail_count = sum(1 for r in check_results if r.verdict == Verdict.FAIL)
        warning_count = sum(1 for r in check_results if r.verdict == Verdict.WARNING)
        error_count = sum(1 for r in check_results if r.verdict == Verdict.ERROR)
        na_count = sum(1 for r in check_results if r.verdict == Verdict.NOT_APPLICABLE)
        
        return {
            "total": len(check_results),
            "pass": pass_count,
            "fail": fail_count,
            "warning": warning_count,
            "error": error_count,
            "not_applicable": na_count,
            "success_rate": (pass_count + warning_count) / len(check_results) if check_results else 0,
            "overall_verdict": Verdict.FAIL if fail_count > 0 else Verdict.PASS,
        }
    
    def _compute_verdict(self, 
                         metric_name: str,
                         measured: float,
                         expected_min: Optional[float],
                         expected_max: Optional[float],
                         unit: str) -> Tuple[Verdict, str]:
        """Compute verdict based on measured value and expectations."""
        
        # Check against minimum
        if expected_min is not None:
            if self._within_numeric_tolerance(measured, expected_min):
                measured = expected_min
            if measured < expected_min:
                margin = self._relative_margin(expected_min - measured, expected_min)
                if margin < self.warning_margin:
                    return Verdict.WARNING, f"{metric_name} = {measured:.4g} {unit} (close to min {expected_min} {unit})"
                return Verdict.FAIL, f"{metric_name} = {measured:.4g} {unit} < {expected_min} {unit}"
        
        # Check against maximum
        if expected_max is not None:
            if self._within_numeric_tolerance(measured, expected_max):
                measured = expected_max
            if measured > expected_max:
                margin = self._relative_margin(measured - expected_max, expected_max)
                if margin < self.warning_margin:
                    return Verdict.WARNING, f"{metric_name} = {measured:.4g} {unit} (close to max {expected_max} {unit})"
                return Verdict.FAIL, f"{metric_name} = {measured:.4g} {unit} > {expected_max} {unit}"
        
        # Within range
        return Verdict.PASS, f"{metric_name} = {measured:.4g} {unit}"
    
    def _to_si(self, value: Optional[float], unit: str) -> Optional[float]:
        """Convert value with unit to SI base unit."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                return None
        
        unit_lower = unit.lower().strip()
        
        # Find conversion factor
        for prefix, factor in self.UNIT_CONVERSION.items():
            if unit_lower.endswith(prefix):
                return value * factor
        
        return value

    @staticmethod
    def _relative_margin(delta: float, reference: float) -> float:
        denominator = abs(reference)
        if denominator <= 1e-30:
            return float("inf") if abs(delta) > 0 else 0.0
        return abs(delta) / denominator

    @classmethod
    def _within_numeric_tolerance(cls, measured: float, expected: float) -> bool:
        scale = max(abs(measured), abs(expected), 1.0)
        return abs(measured - expected) <= cls.ABSOLUTE_TOLERANCE * scale
    
    def _get_metric_category(self, metric_name: str) -> str:
        """Determine category from metric name."""
        metric_lower = metric_name.lower()
        
        if any(x in metric_lower for x in ["dc", "op", "bias", "power", "current"]):
            return "dc"
        elif any(x in metric_lower for x in ["gain", "bandwidth", "gbw", "cmrr", "psrr", "phase"]):
            return "ac"
        elif any(x in metric_lower for x in ["slew", "settling", "overshoot", "transient"]):
            return "transient"
        elif any(x in metric_lower for x in ["thd", "fft", "sfdr", "spectral", "noise"]):
            return "spectral"
        elif any(x in metric_lower for x in ["pvt", "corner", "temperature", "supply"]):
            return "pvt"
        else:
            return "other"
