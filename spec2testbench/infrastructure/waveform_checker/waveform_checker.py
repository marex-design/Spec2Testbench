# spec2testbench/infrastructure/waveform_checker/waveform_checker.py

"""
WaveformChecker - Implementation of IWaveformAnalyzer.
Uses multimodal LLM to analyze waveform images.
"""

import json
import base64
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from ...domain.value_objects.verdict import Verdict
from ...domain.value_objects.multimodal_result import (
    MultimodalResult, WaveformAnalysis, WaveformFeature, WaveformType
)
from ...domain.interfaces.iwaveform_analyzer import IWaveformAnalyzer
from ...domain.entities.specification import Specification
from .waveform_plotter import WaveformPlotter

logger = logging.getLogger(__name__)


class WaveformChecker(IWaveformAnalyzer):
    """
    Implementation of multimodal waveform analyzer.
    
    Uses MLLM (GPT-4V, Gemini, Claude) to:
    1. Identify waveform types (sinusoidal, square, damped, etc.)
    2. Extract features (amplitude, frequency, rise time)
    3. Detect anomalies (ringing, clipping, overshoot)
    4. Generate diagnostic recommendations
    """
    
    # Known waveform patterns and their typical causes
    PATTERN_DIAGNOSIS = {
        "damped_oscillation": {
            "cause": "Insufficient loop gain or improper feedback",
            "recommendation": "Increase gain or check feedback network",
            "circuit_types": ["oscillator", "amplifier", "opamp"]
        },
        "ringing": {
            "cause": "Excessive high-frequency gain or parasitic capacitance",
            "recommendation": "Add compensation capacitor or reduce bandwidth",
            "circuit_types": ["amplifier", "opamp", "buffer"]
        },
        "clipping": {
            "cause": "Output swing limited by supply voltage or bias",
            "recommendation": "Check supply voltages or adjust bias point",
            "circuit_types": ["amplifier", "comparator", "opamp"]
        },
        "slew_limited": {
            "cause": "Insufficient current in output stage",
            "recommendation": "Increase bias current in output transistors",
            "circuit_types": ["amplifier", "opamp", "buffer"]
        },
        "oscillation": {
            "cause": "Positive feedback or inadequate phase margin",
            "recommendation": "Add compensation capacitor or reduce feedback",
            "circuit_types": ["amplifier", "opamp", "buffer", "ldo"]
        },
        "nonlinear_distortion": {
            "cause": "Transistors operating in non-linear region",
            "recommendation": "Increase overdrive voltage or adjust biasing",
            "circuit_types": ["amplifier", "opamp"]
        },
        "offset_error": {
            "cause": "Mismatch in differential pair or input stage",
            "recommendation": "Check transistor matching or add offset calibration",
            "circuit_types": ["opamp", "comparator", "differential_amplifier"]
        },
        "noisy_signal": {
            "cause": "Thermal noise or supply coupling",
            "recommendation": "Add decoupling capacitors or reduce bandwidth",
            "circuit_types": ["amplifier", "power_supply", "ldo", "vref"]
        },
        "dc_drift": {
            "cause": "Temperature variation or aging",
            "recommendation": "Add temperature compensation or chopper stabilization",
            "circuit_types": ["opamp", "vref", "amplifier"]
        },
        "jitter": {
            "cause": "Phase noise or timing uncertainty",
            "recommendation": "Improve signal integrity or reduce noise",
            "circuit_types": ["oscillator", "pll", "clock_buffer"]
        },
        "cross_talk": {
            "cause": "Capacitive or inductive coupling between signals",
            "recommendation": "Increase isolation or add shielding",
            "circuit_types": ["mixer", "adc", "amplifier"]
        },
    }
    
    def __init__(self, llm_client=None, use_llm: bool = True):
        """
        Initialize the waveform checker.
        
        Args:
            llm_client: LLM client with multimodal capabilities
            use_llm: If False, use rule-based pattern matching only
        """
        self.llm_client = llm_client
        self.use_llm = use_llm
        self.plotter = WaveformPlotter()
    
    def analyze(self,
                image_path: Path,
                context: Optional[Dict[str, Any]] = None) -> WaveformAnalysis:
        """
        Analyze a waveform image.
        
        Args:
            image_path: Path to waveform PNG image
            context: Optional context (circuit type, expected values)
            
        Returns:
            WaveformAnalysis with structured analysis
        """
        logger.info(f"Analyzing waveform: {image_path}")
        
        if self.use_llm and self.llm_client:
            analysis = self._analyze_with_llm(image_path, context)
        else:
            analysis = self._analyze_with_rules(image_path, context)
        
        # Enhance with pattern matching if confidence is low
        if analysis.confidence < 0.6:
            analysis = self._enhance_with_pattern_matching(analysis, context)
        
        return analysis
    
    def check_specification(self,
                           image_path: Path,
                           metric_name: str,
                           expected_min: float,
                           expected_max: float,
                           unit: str) -> MultimodalResult:
        """
        Check if waveform meets a specific specification.
        
        Args:
            image_path: Path to waveform image
            metric_name: Name of the metric to check
            expected_min: Minimum expected value
            expected_max: Maximum expected value
            unit: Unit of measurement
            
        Returns:
            MultimodalResult with verdict and diagnostics
        """
        # Analyze waveform
        analysis = self.analyze(image_path)
        
        # Find matching feature
        feature = None
        for f in analysis.features:
            if metric_name.lower() in f.name.lower():
                feature = f
                break
        
        # Determine verdict
        violations = []
        if feature:
            measured = feature.value
            if measured < expected_min:
                violations.append(f"{metric_name}: {measured} {unit} < {expected_min} {unit}")
            elif measured > expected_max:
                violations.append(f"{metric_name}: {measured} {unit} > {expected_max} {unit}")
        
        verdict = Verdict.FAIL if violations else Verdict.PASS
        
        return MultimodalResult(
            verdict=verdict,
            waveform_image_path=str(image_path),
            analysis=analysis,
            extracted_metrics=self._features_to_metrics(analysis.features),
            violations=violations,
            test_name=f"check_{metric_name}",
            timestamp=datetime.now().isoformat(),
            llm_model=self._get_llm_model_name()
        )
    
    def diagnose_failure(self,
                        image_path: Path,
                        specification: Specification,
                        failed_metrics: List[str]) -> MultimodalResult:
        """
        Diagnose the cause of a test failure.
        
        Args:
            image_path: Path to waveform image
            specification: Circuit specifications
            failed_metrics: List of metrics that failed
            
        Returns:
            MultimodalResult with diagnosis and recommendations
        """
        # Analyze waveform
        analysis = self.analyze(image_path, context={
            "circuit_type": specification.circuit_type.display_name,
            "failed_metrics": failed_metrics
        })
        
        # Build recommendations based on analysis
        recommendations = []
        anomalies = analysis.anomalies.copy()
        
        for anomaly in analysis.anomalies:
            pattern = self.PATTERN_DIAGNOSIS.get(anomaly.lower().replace(" ", "_"))
            if pattern:
                recommendations.extend([pattern["recommendation"]])
        
        # Add generic recommendations if none specific
        if not recommendations and analysis.anomalies:
            recommendations.append("Review circuit design for the detected anomalies")
        
        # Extract metrics from features
        extracted_metrics = self._features_to_metrics(analysis.features)
        
        # Determine overall verdict
        verdict = Verdict.FAIL if analysis.anomalies else Verdict.WARNING
        
        return MultimodalResult(
            verdict=verdict,
            waveform_image_path=str(image_path),
            analysis=analysis,
            extracted_metrics=extracted_metrics,
            violations=[f"Failed: {m}" for m in failed_metrics],
            reasoning=analysis.diagnosis,
            recommendations=recommendations,
            anomalies=anomalies,
            test_name=",".join(failed_metrics[:2]),
            timestamp=datetime.now().isoformat(),
            llm_model=self._get_llm_model_name()
        )
    
    def extract_metrics_from_image(self,
                                   image_path: Path,
                                   metrics: List[str]) -> Dict[str, float]:
        """
        Extract specific metrics from a waveform image.
        
        Args:
            image_path: Path to waveform image
            metrics: List of metrics to extract (amplitude, frequency, etc.)
            
        Returns:
            Dictionary of {metric_name: value}
        """
        analysis = self.analyze(image_path)
        
        result = {}
        for metric in metrics:
            for feature in analysis.features:
                if metric.lower() in feature.name.lower():
                    result[metric] = feature.value
                    break
        
        return result
    
    def is_image_interpretable(self, image_path: Path) -> bool:
        """
        Check if the image is interpretable by the MLLM.
        
        Args:
            image_path: Path to image
            
        Returns:
            True if image can be analyzed
        """
        if not image_path.exists():
            return False
        
        # Check file size (minimum 1KB)
        if image_path.stat().st_size < 1024:
            return False
        
        # Check file extension
        if image_path.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.bmp']:
            return False
        
        return True
    
    def _analyze_with_llm(self, image_path: Path, context: Optional[Dict]) -> WaveformAnalysis:
        """Analyze waveform using multimodal LLM."""
        
        # Encode image
        image_base64 = self._encode_image(image_path)
        
        # Build prompt
        prompt = self._build_analysis_prompt(context)
        
        try:
            response = self.llm_client.multimodal_complete(
                prompt=prompt,
                image_base64=image_base64,
                response_format="json"
            )
            return self._parse_llm_response(response)
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}, falling back to rule-based")
            return self._analyze_with_rules(image_path, context)
    
    def _analyze_with_rules(self, image_path: Path, context: Optional[Dict]) -> WaveformAnalysis:
        """Analyze waveform using rule-based pattern detection (no LLM)."""
        
        # For now, return a basic analysis
        # In production, this could use image processing libraries
        return WaveformAnalysis(
            waveform_type=WaveformType.UNKNOWN,
            features=[],
            anomalies=["Rule-based analysis not fully implemented"],
            diagnosis="Unable to perform detailed analysis without LLM",
            recommendations=["Enable LLM for full waveform analysis"],
            confidence=0.3
        )
    
    def _enhance_with_pattern_matching(self, 
                                       analysis: WaveformAnalysis,
                                       context: Optional[Dict]) -> WaveformAnalysis:
        """Enhance low-confidence analysis with pattern matching."""
        
        # Try to match waveform type to known patterns
        waveform_str = analysis.waveform_type.value
        pattern = self.PATTERN_DIAGNOSIS.get(waveform_str)
        
        if pattern:
            circuit_type = context.get("circuit_type", "") if context else ""
            
            # Check if pattern applies to this circuit type
            if not circuit_type or circuit_type.lower() in [ct.lower() for ct in pattern["circuit_types"]]:
                if analysis.confidence < 0.5:
                    # Enhance diagnosis
                    enhanced_analysis = WaveformAnalysis(
                        waveform_type=analysis.waveform_type,
                        features=analysis.features,
                        anomalies=analysis.anomalies,
                        diagnosis=pattern["cause"],
                        recommendations=[pattern["recommendation"]],
                        confidence=0.55
                    )
                    return enhanced_analysis
        
        return analysis
    
    def _encode_image(self, image_path: Path) -> str:
        """Encode image as base64 for LLM."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _build_analysis_prompt(self, context: Optional[Dict]) -> str:
        """Build prompt for multimodal analysis."""
        
        context_str = ""
        if context:
            context_str = f"""
## CONTEXT
Circuit Type: {context.get('circuit_type', 'Unknown')}
Expected behavior: {context.get('expected', 'Not specified')}
Failed metrics: {context.get('failed_metrics', [])}
"""
        
        prompt = f"""
You are an expert analog circuit debugger. Analyze the attached waveform image.

{context_str}

## TASK
Analyze the waveform and provide structured diagnostic information.

## OUTPUT FORMAT
Return a JSON object with:

{{
  "waveform_type": "sinusoidal|square|triangular|damped_oscillation|ringing|clipped|slew_limited|noisy|constant|other",
  "features": [
    {{"name": "amplitude", "value": 1.5, "unit": "V", "confidence": 0.95, "description": "Peak-to-peak amplitude"}},
    {{"name": "frequency", "value": 1000000, "unit": "Hz", "confidence": 0.98, "description": "Fundamental frequency"}},
    {{"name": "dc_offset", "value": 2.5, "unit": "V", "confidence": 0.92, "description": "DC bias level"}},
    {{"name": "rise_time", "value": 1.2e-9, "unit": "s", "confidence": 0.85, "description": "10-90% rise time"}}
  ],
  "anomalies": ["List any unexpected behavior or artifacts"],
  "diagnosis": "Detailed analysis of what the waveform indicates about circuit operation",
  "recommendations": ["Actionable recommendations to fix identified issues"],
  "confidence": 0.85
}}

Analyze the attached waveform now. Return ONLY valid JSON.
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> WaveformAnalysis:
        """Parse LLM response into WaveformAnalysis."""
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise
        
        features = []
        for f in data.get("features", []):
            features.append(WaveformFeature(
                name=f.get("name", "unknown"),
                value=float(f.get("value", 0)),
                unit=f.get("unit", ""),
                confidence=float(f.get("confidence", 0.5)),
                description=f.get("description", "")
            ))
        
        waveform_type_str = data.get("waveform_type", "unknown")
        try:
            waveform_type = WaveformType(waveform_type_str)
        except ValueError:
            waveform_type = WaveformType.UNKNOWN
        
        return WaveformAnalysis(
            waveform_type=waveform_type,
            features=features,
            anomalies=data.get("anomalies", []),
            diagnosis=data.get("diagnosis", "No diagnosis provided"),
            recommendations=data.get("recommendations", []),
            confidence=float(data.get("confidence", 0.5)),
            raw_llm_response=response
        )
    
    def _features_to_metrics(self, features: List[WaveformFeature]) -> Dict[str, float]:
        """Convert features to metrics dictionary."""
        metrics = {}
        for feature in features:
            metrics[feature.name] = feature.value
        return metrics
    
    def _get_llm_model_name(self) -> str:
        """Get LLM model name."""
        if self.llm_client and hasattr(self.llm_client, 'model_name'):
            return self.llm_client.model_name
        return "rule-based"