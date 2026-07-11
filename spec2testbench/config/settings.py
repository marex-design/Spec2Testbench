import os
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class LLMSettings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    google_model: str = field(default_factory=lambda: os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"))
    default_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))
    
    def get_api_key(self, provider: str = None) -> str:
        p = provider or self.default_provider
        keys = {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "groq": self.groq_api_key,
            "google": self.google_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return keys.get(p, "")
    
    def get_model(self, provider: str = None, vision: bool = False) -> str:
        p = provider or self.default_provider
        models = {
            "openai": self.openai_model,
            "deepseek": self.deepseek_model,
            "groq": self.groq_model,
            "google": self.google_model,
            "anthropic": self.anthropic_model,
        }
        return models.get(p, "gpt-4-turbo-preview")
    
    @property
    def is_configured(self) -> bool:
        return bool(self.get_api_key())

@dataclass
class SimulatorSettings:
    simulator_type: str = field(default_factory=lambda: os.getenv("SIMULATOR_TYPE", "wsl"))
    ngspice_path: str = field(default_factory=lambda: os.getenv("NGSPICE_PATH", "ngspice"))
    timeout_seconds: int = int(os.getenv("SIMULATOR_TIMEOUT", "30"))
    allow_mock: bool = field(default_factory=lambda: os.getenv("ALLOW_MOCK_SIMULATION", "false").lower() == "true")
    allow_recovery: bool = field(default_factory=lambda: os.getenv("ALLOW_SIMULATION_RECOVERY", "true").lower() == "true")

@dataclass
class OutputSettings:
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "./output"))
    waveform_dir: Path = Path(os.getenv("WAVEFORM_DIR", "./waveforms"))
    report_dir: Path = Path(os.getenv("REPORT_DIR", "./reports"))
    
    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.waveform_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

@dataclass
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    simulator: SimulatorSettings = field(default_factory=SimulatorSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    use_llm: bool = os.getenv("USE_LLM", "true").lower() == "true"
    warning_margin: float = float(os.getenv("WARNING_MARGIN", "0.05"))
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "3"))

settings = Settings()
