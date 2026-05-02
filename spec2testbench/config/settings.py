# spec2testbench/config/settings.py (ajouts)

@dataclass
class LLMSettings:
    """LLM configuration settings."""
    
    # OpenAI
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"))
    
    # DeepSeek
    deepseek_api_key: Optional[str] = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    deepseek_vision_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-vl"))
    
    # Anthropic
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"))
    
    # Google
    google_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    google_model: str = field(default_factory=lambda: os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"))
    
    # Default provider (openai, deepseek, gemini, anthropic)
    default_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))
    
    @property
    def is_configured(self) -> bool:
        """Check if at least one LLM provider is configured."""
        providers = {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "gemini": self.google_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return bool(providers.get(self.default_provider))
    
    def get_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        """Get API key for a specific provider."""
        provider = provider or self.default_provider
        keys = {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "gemini": self.google_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return keys.get(provider)
    
    def get_model(self, provider: Optional[str] = None, vision: bool = False) -> str:
        """Get model for a specific provider."""
        provider = provider or self.default_provider
        
        models = {
            "openai": self.openai_model,
            "deepseek": self.deepseek_vision_model if vision else self.deepseek_model,
            "gemini": self.google_model,
            "anthropic": self.anthropic_model,
        }
        return models.get(provider, "gpt-4-turbo-preview")