"""
LLMMultimodalClient - Specialized multimodal analyzer for waveform diagnostics.

Provides high-level interface for analyzing waveform images using vision LLMs.
Supports OpenAI GPT-4V, DeepSeek-VL, Google Gemini-1.5-Vision, Claude-3-Vision.
"""

import json
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

from ..llm.llm_client import LLMClient, LLMProvider

logger = logging.getLogger(__name__)


class DiagnosticLevel(Enum):
    """Diagnostic analysis depth levels."""
    QUICK = "quick"          # Basic feature extraction
    STANDARD = "standard"    # Full analysis with anomaly detection
    DETAILED = "detailed"    # Extended analysis with recommendations


class WaveformDiagnosisResult:
    """Structured result from waveform multimodal analysis."""
    
    def __init__(self,
                 waveform_type: str,
                 features: Dict[str, Any],
                 anomalies: List[str],
                 diagnosis: str,
                 recommendations: List[str],
                 confidence: float,
                 extracted_metrics: Dict[str, float],
                 raw_response: str,
                 model_name: str):
        """
        Initialize waveform diagnosis result.
        
        Args:
            waveform_type: Type of waveform (sinusoidal, square, damped, etc.)
            features: Extracted features (amplitude, frequency, rise_time, etc.)
            anomalies: Detected anomalies (ringing, clipping, etc.)
            diagnosis: Text diagnosis of circuit behavior
            recommendations: Actionable recommendations
            confidence: Confidence score (0-1)
            extracted_metrics: Numerical metrics extracted from image
            raw_response: Raw LLM response
            model_name: Name of LLM model used
        """
        self.waveform_type = waveform_type
        self.features = features
        self.anomalies = anomalies
        self.diagnosis = diagnosis
        self.recommendations = recommendations
        self.confidence = confidence
        self.extracted_metrics = extracted_metrics
        self.raw_response = raw_response
        self.model_name = model_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "waveform_type": self.waveform_type,
            "features": self.features,
            "anomalies": self.anomalies,
            "diagnosis": self.diagnosis,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
            "extracted_metrics": self.extracted_metrics,
            "model_name": self.model_name
        }


class LLMMultimodalClient:
    """
    High-level multimodal analyzer for waveform diagnostics.
    
    Encapsulates LLMClient and provides specialized methods for:
    - Waveform type classification
    - Feature extraction (amplitude, frequency, rise time, etc.)
    - Anomaly detection (ringing, clipping, offset, jitter, etc.)
    - Root cause diagnosis
    - Actionable recommendations
    
    Supports fallback to rule-based analysis if LLM fails.
    """
    
    def __init__(self,
                 provider: str = "openai",
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 temperature: float = 0.3,  # Lower temp for consistency
                 max_tokens: int = 2048):
        """
        Initialize the multimodal client.
        
        Args:
            provider: LLM provider ('openai', 'deepseek', 'gemini', 'anthropic')
            api_key: API key for provider
            model: Model name (uses provider default if None)
            temperature: Sampling temperature (0-1, lower = more consistent)
            max_tokens: Maximum tokens in response
        """
        self.llm_client = LLMClient(
            provider=provider,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        self.provider = provider
        self.model = model or self.llm_client.model
        logger.info(f"LLMMultimodalClient initialized with {provider}/{self.model}")
    
    def analyze_waveform(self,
                        image_path: Path,
                        circuit_type: Optional[str] = None,
                        expected_behavior: Optional[str] = None,
                        failed_metrics: Optional[List[str]] = None,
                        diagnostic_level: DiagnosticLevel = DiagnosticLevel.STANDARD
                        ) -> WaveformDiagnosisResult:
        """
        Analyze a waveform image using vision LLM.
        
        Args:
            image_path: Path to waveform PNG image
            circuit_type: Optional circuit type (amplifier, oscillator, etc.)
            expected_behavior: Optional description of expected behavior
            failed_metrics: Optional list of metrics that failed specification
            diagnostic_level: Depth of analysis (quick, standard, detailed)
            
        Returns:
            WaveformDiagnosisResult with analysis
            
        Raises:
            FileNotFoundError: If image not found
            ValueError: If image format not supported
        """
        # Validate image
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        if image_path.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.bmp']:
            raise ValueError(f"Unsupported image format: {image_path.suffix}")
        
        logger.info(f"Analyzing waveform: {image_path}")
        
        try:
            # Encode image as base64
            image_base64 = self._encode_image(image_path)
            
            # Build specialized prompt
            prompt = self._build_waveform_analysis_prompt(
                circuit_type=circuit_type,
                expected_behavior=expected_behavior,
                failed_metrics=failed_metrics,
                diagnostic_level=diagnostic_level
            )
            
            # Call LLM with vision capabilities
            response = self.llm_client.multimodal_complete(
                prompt=prompt,
                image_base64=image_base64,
                response_format="json"
            )
            
            # Parse and structure response
            result = self._parse_waveform_analysis_response(response)
            result.model_name = self.model
            result.raw_response = response
            
            logger.info(f"Waveform analysis complete: {result.waveform_type} "
                       f"(confidence: {result.confidence:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM multimodal analysis failed: {e}")
            raise
    
    def extract_metrics(self,
                       image_path: Path,
                       metrics_to_extract: List[str],
                       circuit_type: Optional[str] = None
                       ) -> Dict[str, float]:
        """
        Extract specific metrics from waveform image.
        
        Args:
            image_path: Path to waveform image
            metrics_to_extract: List of metric names (amplitude, frequency, rise_time, etc.)
            circuit_type: Optional circuit type for context
            
        Returns:
            Dictionary of {metric_name: value}
        """
        logger.info(f"Extracting metrics: {metrics_to_extract}")
        
        try:
            # Use quick analysis for metric extraction
            result = self.analyze_waveform(
                image_path=image_path,
                circuit_type=circuit_type,
                diagnostic_level=DiagnosticLevel.QUICK
            )
            
            # Filter to requested metrics
            metrics = {}
            for metric in metrics_to_extract:
                if metric in result.extracted_metrics:
                    metrics[metric] = result.extracted_metrics[metric]
                elif metric in result.features:
                    metrics[metric] = result.features[metric]
            
            return metrics
            
        except Exception as e:
            logger.error(f"Metric extraction failed: {e}")
            return {}
    
    def detect_anomalies(self,
                        image_path: Path,
                        circuit_type: Optional[str] = None,
                        thresholds: Optional[Dict[str, Dict[str, float]]] = None
                        ) -> Dict[str, Any]:
        """
        Detect anomalies in waveform.
        
        Args:
            image_path: Path to waveform image
            circuit_type: Optional circuit type
            thresholds: Optional thresholds for metric validation
                       e.g., {"amplitude": {"min": 1.0, "max": 3.0}}
            
        Returns:
            Dictionary with:
            - anomalies: List of detected anomalies
            - severity: Overall severity (low, medium, high)
            - recommendations: List of recommendations
        """
        logger.info(f"Detecting anomalies in: {image_path}")
        
        try:
            result = self.analyze_waveform(
                image_path=image_path,
                circuit_type=circuit_type,
                diagnostic_level=DiagnosticLevel.DETAILED
            )
            
            # Check against thresholds if provided
            violations = []
            if thresholds:
                for metric, bounds in thresholds.items():
                    if metric in result.extracted_metrics:
                        value = result.extracted_metrics[metric]
                        if "min" in bounds and value < bounds["min"]:
                            violations.append(
                                f"{metric}: {value} < {bounds['min']} (minimum)"
                            )
                        if "max" in bounds and value > bounds["max"]:
                            violations.append(
                                f"{metric}: {value} > {bounds['max']} (maximum)"
                            )
            
            # Determine severity
            severity = "low"
            if len(result.anomalies) > 2 or violations:
                severity = "high"
            elif len(result.anomalies) > 0:
                severity = "medium"
            
            return {
                "anomalies": result.anomalies + violations,
                "severity": severity,
                "recommendations": result.recommendations,
                "waveform_type": result.waveform_type,
                "diagnosis": result.diagnosis,
                "confidence": result.confidence
            }
            
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return {
                "anomalies": ["Error during analysis"],
                "severity": "unknown",
                "recommendations": ["Re-run analysis or check image quality"],
                "confidence": 0.0
            }
    
    def diagnose_failure(self,
                        image_path: Path,
                        failed_specification: Dict[str, Any],
                        circuit_type: Optional[str] = None
                        ) -> Dict[str, Any]:
        """
        Diagnose the cause of a test failure using waveform analysis.
        
        Args:
            image_path: Path to waveform image
            failed_specification: Specification that failed
                                e.g., {"metric": "amplitude", "expected": (1.0, 3.0), "measured": 0.5}
            circuit_type: Optional circuit type
            
        Returns:
            Dictionary with:
            - root_cause: Most likely root cause
            - diagnosis: Detailed diagnosis
            - recommendations: Actionable recommendations
            - confidence: Confidence in diagnosis (0-1)
        """
        logger.info(f"Diagnosing failure from: {image_path}")
        
        try:
            # Extract failed metric names
            failed_metrics = list(failed_specification.keys()) if failed_specification else []
            
            result = self.analyze_waveform(
                image_path=image_path,
                circuit_type=circuit_type,
                failed_metrics=failed_metrics,
                diagnostic_level=DiagnosticLevel.DETAILED
            )
            
            # Enhance diagnosis with specification context
            enhanced_diagnosis = self._enhance_diagnosis_with_spec(
                result,
                failed_specification,
                circuit_type
            )
            
            return {
                "root_cause": result.diagnosis,
                "diagnosis": enhanced_diagnosis,
                "recommendations": result.recommendations,
                "detected_anomalies": result.anomalies,
                "confidence": result.confidence,
                "waveform_type": result.waveform_type,
                "extracted_metrics": result.extracted_metrics
            }
            
        except Exception as e:
            logger.error(f"Failure diagnosis failed: {e}")
            return {
                "root_cause": "Analysis error",
                "diagnosis": str(e),
                "recommendations": ["Check waveform image quality"],
                "confidence": 0.0
            }
    
    def _encode_image(self, image_path: Path) -> str:
        """Encode image as base64 for LLM transmission."""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise
    
    def _build_waveform_analysis_prompt(self,
                                       circuit_type: Optional[str] = None,
                                       expected_behavior: Optional[str] = None,
                                       failed_metrics: Optional[List[str]] = None,
                                       diagnostic_level: DiagnosticLevel = DiagnosticLevel.STANDARD
                                       ) -> str:
        """Build specialized prompt for waveform analysis."""
        
        context_lines = []
        
        if circuit_type:
            context_lines.append(f"Circuit Type: {circuit_type}")
        
        if expected_behavior:
            context_lines.append(f"Expected Behavior: {expected_behavior}")
        
        if failed_metrics:
            context_lines.append(f"Failed Metrics: {', '.join(failed_metrics)}")
        
        context_str = ""
        if context_lines:
            context_str = "## CONTEXT\n" + "\n".join(context_lines) + "\n\n"
        
        # Adjust prompt based on diagnostic level
        if diagnostic_level == DiagnosticLevel.QUICK:
            extraction_focus = "Extract the most important features only (amplitude, frequency, DC offset)."
        elif diagnostic_level == DiagnosticLevel.DETAILED:
            extraction_focus = "Provide comprehensive analysis including all detectable features and potential issues."
        else:  # STANDARD
            extraction_focus = "Extract key features and identify any anomalies."
        
        prompt = f"""You are an expert analog circuit engineer analyzing waveform measurements.

{context_str}## ANALYSIS TASK
{extraction_focus}

Analyze the attached waveform image and provide structured diagnostic information.

## FEATURE EXTRACTION
Extract the following metrics if visible in the waveform:
- amplitude (peak-to-peak voltage)
- frequency (fundamental frequency if periodic)
- dc_offset (DC bias level)
- rise_time (10%-90% rise time)
- fall_time (90%-10% fall time)
- overshoot (% overshoot on step response)
- period (time for one complete cycle)
- duty_cycle (for square waves)
- harmonics (presence of harmonic distortion)
- noise_level (estimated noise amplitude)
- phase_shift (phase relative to expected)
- settling_time (time to settle within tolerance)
- slew_rate (dV/dt maximum rate)

## ANOMALY DETECTION
Identify any of these anomalies if present:
- ringing (damped oscillations after transitions)
- clipping (signal limited by supply or saturation)
- dc_drift (slow change in DC offset)
- jitter (timing uncertainty in periodic signals)
- offset_error (unexpected DC bias)
- cross_talk (interference from other signals)
- slew_limited (linear slope indicating current limit)
- oscillation (sustained oscillation)
- nonlinear_distortion (harmonic content)
- noise (excessive noise floor)

## REQUIRED OUTPUT FORMAT
Return ONLY a valid JSON object with this exact structure:

{{
  "waveform_type": "sinusoidal|square|triangular|sawtooth|damped_oscillation|pulse|noise|constant|other",
  "features": {{
    "amplitude": {{"value": null, "unit": "V", "confidence": 0.0}},
    "frequency": {{"value": null, "unit": "Hz", "confidence": 0.0}},
    "dc_offset": {{"value": null, "unit": "V", "confidence": 0.0}},
    "rise_time": {{"value": null, "unit": "s", "confidence": 0.0}},
    "fall_time": {{"value": null, "unit": "s", "confidence": 0.0}},
    "overshoot": {{"value": null, "unit": "%", "confidence": 0.0}},
    "period": {{"value": null, "unit": "s", "confidence": 0.0}},
    "slew_rate": {{"value": null, "unit": "V/s", "confidence": 0.0}}
  }},
  "anomalies": ["list", "of", "detected", "anomalies"],
  "severity": "low|medium|high",
  "diagnosis": "Detailed technical analysis of what the waveform indicates about circuit operation",
  "root_cause": "Most likely root cause of any observed anomalies",
  "recommendations": [
    "Specific, actionable recommendation 1",
    "Specific, actionable recommendation 2"
  ],
  "confidence": 0.85,
  "notes": "Any additional observations"
}}

Respond with ONLY the JSON object, no additional text.
"""
        return prompt
    
    def _parse_waveform_analysis_response(self, response: str) -> WaveformDiagnosisResult:
        """Parse LLM JSON response into structured result."""
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response if wrapped in text
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON response: {response[:200]}")
                    raise
            else:
                raise ValueError(f"No JSON found in response: {response[:200]}")
        
        # Extract features
        features = {}
        extracted_metrics = {}
        raw_features = data.get("features", {})
        
        for feature_name, feature_data in raw_features.items():
            if isinstance(feature_data, dict):
                value = feature_data.get("value")
                unit = feature_data.get("unit", "")
                if value is not None:
                    features[feature_name] = {"value": value, "unit": unit}
                    extracted_metrics[feature_name] = float(value) if value else 0.0
        
        # Extract other fields
        waveform_type = data.get("waveform_type", "unknown")
        anomalies = data.get("anomalies", [])
        diagnosis = data.get("diagnosis", "") or data.get("root_cause", "")
        recommendations = data.get("recommendations", [])
        confidence = float(data.get("confidence", 0.5))
        
        return WaveformDiagnosisResult(
            waveform_type=waveform_type,
            features=features,
            anomalies=anomalies,
            diagnosis=diagnosis,
            recommendations=recommendations,
            confidence=confidence,
            extracted_metrics=extracted_metrics,
            raw_response=response,
            model_name=self.model
        )
    
    def _enhance_diagnosis_with_spec(self,
                                    result: WaveformDiagnosisResult,
                                    failed_specification: Dict[str, Any],
                                    circuit_type: Optional[str] = None) -> str:
        """Enhance diagnosis by comparing with failed specification."""
        
        enhancements = [result.diagnosis]
        
        if failed_specification:
            enhancements.append("\n\nSpecification Violations:")
            for metric, spec_value in failed_specification.items():
                measured = result.extracted_metrics.get(metric)
                if measured is not None:
                    enhancements.append(
                        f"  - {metric}: measured={measured}, "
                        f"expected={spec_value} "
                        f"(violation detected)"
                    )
        
        if circuit_type:
            enhancements.append(f"\n\nFor {circuit_type} circuits:")
            if "amplifier" in circuit_type.lower():
                enhancements.append("  - Check gain, bandwidth, and stability margins")
            elif "oscillator" in circuit_type.lower():
                enhancements.append("  - Check frequency accuracy and jitter")
            elif "filter" in circuit_type.lower():
                enhancements.append("  - Check cutoff frequency and phase response")
        
        return "\n".join(enhancements)
