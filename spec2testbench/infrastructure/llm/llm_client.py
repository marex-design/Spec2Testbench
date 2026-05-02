# spec2testbench/infrastructure/llm/llm_client.py

"""
Unified LLM Client for multiple providers.
Supports: OpenAI, DeepSeek, Google Gemini, Anthropic Claude
"""

import json
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


class LLMClient:
    """
    Unified client for multiple LLM providers.
    
    Supports:
    - OpenAI (GPT-4, GPT-4V for vision)
    - DeepSeek (DeepSeek-V3, DeepSeek-Coder)
    - Google Gemini (Gemini 1.5 Pro, Gemini 1.5 Flash)
    - Anthropic (Claude 3 Opus, Sonnet, Haiku)
    """
    
    # API endpoints
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1"
    DEEPSEEK_VISION_URL = "https://api.deepseek.com/v1/chat/completions"
    
    def __init__(self, 
                 provider: str = "openai",
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 temperature: float = 0.7,
                 max_tokens: int = 4096):
        """
        Initialize LLM client.
        
        Args:
            provider: 'openai', 'deepseek', 'gemini', or 'anthropic'
            api_key: API key for the provider
            model: Model name (uses provider default if None)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
        """
        self.provider = LLMProvider(provider.lower())
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Set default models
        self.model = model or self._get_default_model()
        
        # Initialize client based on provider
        self._init_client(api_key)
    
    def _get_default_model(self) -> str:
        """Get default model for each provider."""
        defaults = {
            LLMProvider.OPENAI: "gpt-4-turbo-preview",
            LLMProvider.DEEPSEEK: "deepseek-chat",
            LLMProvider.GEMINI: "gemini-1.5-pro",
            LLMProvider.ANTHROPIC: "claude-3-sonnet-20240229",
        }
        return defaults.get(self.provider, "gpt-4-turbo-preview")
    
    def _init_client(self, api_key: Optional[str] = None):
        """Initialize the specific client."""
        if self.provider == LLMProvider.OPENAI:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        
        elif self.provider == LLMProvider.DEEPSEEK:
            from openai import OpenAI
            # DeepSeek uses OpenAI-compatible API
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.DEEPSEEK_API_URL
            )
        
        elif self.provider == LLMProvider.GEMINI:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(self.model)
        
        elif self.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def complete(self, 
                 prompt: str, 
                 response_format: Optional[str] = None,
                 system_prompt: Optional[str] = None) -> str:
        """
        Send a completion request to the LLM.
        
        Args:
            prompt: User prompt
            response_format: 'json' to request JSON output
            system_prompt: Optional system prompt
            
        Returns:
            LLM response as string
        """
        if self.provider == LLMProvider.OPENAI:
            return self._complete_openai(prompt, response_format, system_prompt)
        
        elif self.provider == LLMProvider.DEEPSEEK:
            return self._complete_deepseek(prompt, response_format, system_prompt)
        
        elif self.provider == LLMProvider.GEMINI:
            return self._complete_gemini(prompt, response_format, system_prompt)
        
        elif self.provider == LLMProvider.ANTHROPIC:
            return self._complete_anthropic(prompt, response_format, system_prompt)
        
        raise ValueError(f"Provider {self.provider} not supported for completion")
    
    def multimodal_complete(self,
                           prompt: str,
                           image_base64: str,
                           response_format: Optional[str] = None) -> str:
        """
        Send a multimodal request with image.
        
        Args:
            prompt: User prompt
            image_base64: Base64-encoded image
            response_format: 'json' to request JSON output
            
        Returns:
            LLM response as string
        """
        if self.provider == LLMProvider.OPENAI:
            return self._multimodal_openai(prompt, image_base64, response_format)
        
        elif self.provider == LLMProvider.DEEPSEEK:
            return self._multimodal_deepseek(prompt, image_base64, response_format)
        
        elif self.provider == LLMProvider.GEMINI:
            return self._multimodal_gemini(prompt, image_base64, response_format)
        
        elif self.provider == LLMProvider.ANTHROPIC:
            return self._multimodal_anthropic(prompt, image_base64, response_format)
        
        raise ValueError(f"Provider {self.provider} does not support multimodal")
    
    # =========================================================
    # OPENAI IMPLEMENTATION
    # =========================================================
    
    def _complete_openai(self, prompt: str, response_format: Optional[str], system_prompt: Optional[str]) -> str:
        """OpenAI completion."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def _multimodal_openai(self, prompt: str, image_base64: str, response_format: Optional[str]) -> str:
        """OpenAI multimodal (GPT-4V)."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                    }
                ]
            }
        ]
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    # =========================================================
    # DEEPSEEK IMPLEMENTATION
    # =========================================================
    
    def _complete_deepseek(self, prompt: str, response_format: Optional[str], system_prompt: Optional[str]) -> str:
        """DeepSeek completion (OpenAI-compatible)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        # DeepSeek supports JSON mode
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def _multimodal_deepseek(self, prompt: str, image_base64: str, response_format: Optional[str]) -> str:
        """
        DeepSeek multimodal (DeepSeek-VL).
        DeepSeek supports vision through OpenAI-compatible API.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                    }
                ]
            }
        ]
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    # =========================================================
    # GEMINI IMPLEMENTATION
    # =========================================================
    
    def _complete_gemini(self, prompt: str, response_format: Optional[str], system_prompt: Optional[str]) -> str:
        """Google Gemini completion."""
        generation_config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        
        if response_format == "json":
            generation_config["response_mime_type"] = "application/json"
        
        chat = self.client.start_chat()
        response = chat.send_message(prompt, generation_config=generation_config)
        return response.text
    
    def _multimodal_gemini(self, prompt: str, image_base64: str, response_format: Optional[str]) -> str:
        """Google Gemini multimodal."""
        import google.generativeai as genai
        from PIL import Image
        import io
        import base64
        
        # Decode base64 image
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))
        
        generation_config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        
        if response_format == "json":
            generation_config["response_mime_type"] = "application/json"
        
        response = self.client.generate_content(
            [prompt, image],
            generation_config=generation_config
        )
        return response.text
    
    # =========================================================
    # ANTHROPIC IMPLEMENTATION
    # =========================================================
    
    def _complete_anthropic(self, prompt: str, response_format: Optional[str], system_prompt: Optional[str]) -> str:
        """Anthropic Claude completion."""
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        
        if system_prompt:
            kwargs["system"] = system_prompt
        
        response = self.client.messages.create(**kwargs)
        return response.content[0].text
    
    def _multimodal_anthropic(self, prompt: str, image_base64: str, response_format: Optional[str]) -> str:
        """Anthropic Claude multimodal."""
        # Claude uses a specific format for images
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_base64,
                }
            },
            {"type": "text", "text": prompt}
        ]
        
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": content}],
        }
        
        response = self.client.messages.create(**kwargs)
        return response.content[0].text


# =========================================================
# FACTORY FUNCTION
# =========================================================

def create_llm_client(provider: str = "openai", **kwargs) -> LLMClient:
    """
    Create an LLM client with the specified provider.
    
    Args:
        provider: 'openai', 'deepseek', 'gemini', or 'anthropic'
        **kwargs: Additional arguments (api_key, model, temperature, max_tokens)
        
    Returns:
        LLMClient instance
    """
    return LLMClient(provider=provider, **kwargs)