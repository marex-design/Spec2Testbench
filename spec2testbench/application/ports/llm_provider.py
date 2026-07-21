from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMProviderError(Exception):
    """Base class for provider failures with sanitized attempt metadata."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status_code: int | None = None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.attempts = attempts or []


class LLMAuthenticationError(LLMProviderError):
    pass


class LLMInsufficientBalanceError(LLMProviderError):
    pass


class LLMInvalidRequestError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMProviderUnavailableError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMEmptyResponseError(LLMProviderError):
    pass


class LLMTruncatedResponseError(LLMProviderError):
    pass


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_payload: dict[str, Any]
    response_format: dict[str, Any]
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_seconds: float
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    def list_models(self) -> list[str]:
        ...

    def generate(self, request: LLMRequest) -> LLMResponse:
        ...

