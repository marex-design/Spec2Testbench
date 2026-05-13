from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class WaveformType(Enum):
    SINUSOIDAL = "sinusoidal"
    SQUARE = "square"
    TRIANGULAR = "triangular"
    DAMPED = "damped"
    RINGING = "ringing"
    CLIPPED = "clipped"
    NOISY = "noisy"
    CONSTANT = "constant"
    UNKNOWN = "unknown"


class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NOT_APPLICABLE = "N/A"


@dataclass
class WaveformFeature:
    name: str
    value: float
    unit: str = ""
    confidence: float = 0.8
    description: str = ""


@dataclass
class WaveformAnalysis:
    waveform_type: WaveformType = WaveformType.UNKNOWN
    features: List[WaveformFeature] = field(default_factory=list)
    anomalies: List[str] = field(default_factory=list)
    diagnosis: str = ""
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.5
    raw_llm_response: str = ""


@dataclass
class MultimodalResult:
    verdict: Verdict
    waveform_image_path: str
    analysis: WaveformAnalysis = field(default_factory=WaveformAnalysis)
    extracted_metrics: Dict[str, float] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    circuit_name: str = ""
    test_name: str = ""
    processing_time_ms: float = 0.0
    llm_model: str = ""
    
    def __init__(self, verdict, waveform_image_path, analysis=None, extracted_metrics=None,
                 violations=None, reasoning="", timestamp=None, circuit_name="",
                 test_name="", processing_time_ms=0.0, llm_model="", **kwargs):
        self.verdict = verdict if isinstance(verdict, Verdict) else Verdict(verdict)
        self.waveform_image_path = waveform_image_path
        self.analysis = analysis or WaveformAnalysis()
        self.extracted_metrics = extracted_metrics or {}
        self.violations = violations or []
        self.reasoning = reasoning
        self.timestamp = timestamp or datetime.now().isoformat()
        self.circuit_name = circuit_name
        self.test_name = test_name
        self.processing_time_ms = processing_time_ms
        self.llm_model = llm_model
    
    @property
    def confidence_score(self) -> float:
        return self.analysis.confidence
    
    @property
    def anomalies(self) -> List[str]:
        return self.analysis.anomalies
    
    @property
    def recommendations(self) -> List[str]:
        return self.analysis.recommendations
    
    @property
    def diagnosis(self) -> str:
        return self.analysis.diagnosis
    
    @property
    def is_pass(self) -> bool:
        return self.verdict == Verdict.PASS
    
    @property
    def is_fail(self) -> bool:
        return self.verdict == Verdict.FAIL
    
    def to_dict(self):
        return {
            "verdict": self.verdict.value,
            "waveform_image_path": self.waveform_image_path,
            "extracted_metrics": self.extracted_metrics,
            "violations": self.violations,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "circuit_name": self.circuit_name,
            "test_name": self.test_name,
            "confidence": self.confidence_score
        }
    
    def to_markdown(self) -> str:
        return f"""## Analyse Multimodale: {self.test_name}
**Verdict:** {self.verdict.value}
**Confiance:** {self.confidence_score:.1%}
**Diagnostic:** {self.diagnosis}
"""
