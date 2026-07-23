from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from ...application.ports.llm_provider import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMInsufficientBalanceError,
    LLMInvalidRequestError,
    LLMProvider,
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)


def _mask_secret(text: str, secret: str | None) -> str:
    if not text or not secret:
        return text
    return text.replace(secret, "***")


LEGACY_DEEPSEEK_ALIASES = {"deepseek-chat", "deepseek-reasoner"}


@dataclass(frozen=True)
class DeepSeekProviderConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout_seconds: float = 90.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "DeepSeekProviderConfig":
        config = cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com",
            model=os.getenv("DEEPSEEK_MODEL", "").strip(),
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90")),
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
        )
        config.validate_model_selection(
            allow_empty=True,
            allow_legacy_alias=os.getenv("ALLOW_LEGACY_DEEPSEEK_ALIAS", "").strip() == "1",
        )
        return config

    def validate_model_selection(
        self,
        *,
        allow_empty: bool = False,
        allow_legacy_alias: bool = False,
    ) -> None:
        if not self.model:
            if allow_empty:
                return
            raise ValueError("DEEPSEEK_MODEL must be configured explicitly.")
        if self.model in LEGACY_DEEPSEEK_ALIASES and not allow_legacy_alias:
            raise ValueError(
                f"Legacy DeepSeek alias '{self.model}' is blocked. "
                "Set ALLOW_LEGACY_DEEPSEEK_ALIAS=1 only for non-canonical exploratory usage."
            )


class DeepSeekProvider(LLMProvider):
    def __init__(
        self,
        config: DeepSeekProviderConfig | None = None,
        *,
        client_factory: Callable[[DeepSeekProviderConfig], Any] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        time_fn: Callable[[], float] | None = None,
        jitter_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or DeepSeekProviderConfig.from_env()
        self._client_factory = client_factory or self._default_client_factory
        self._sleep_fn = sleep_fn or time.sleep
        self._time_fn = time_fn or time.perf_counter
        self._jitter_fn = jitter_fn or (lambda: random.uniform(0.0, 0.2))
        self._client = None

    @property
    def config(self) -> DeepSeekProviderConfig:
        return self._config

    def list_models(self) -> list[str]:
        discovery = self.discover_models()
        return [item["id"] for item in discovery["models"]]

    def discover_models(self) -> dict[str, Any]:
        self._ensure_api_key()
        client = self._client_or_create()
        response = client.models.list()
        models = []
        for item in getattr(response, "data", []):
            model_id = getattr(item, "id", None)
            if model_id:
                models.append(
                    {
                        "id": model_id,
                        "owned_by": getattr(item, "owned_by", None),
                    }
                )
        payload = {
            "models": sorted(models, key=lambda entry: str(entry["id"])),
            "http_status": self._extract_status_code(response) or 200,
            "request_id": self._extract_request_id(response),
        }
        payload["response_sha256"] = hashlib.sha256(
            json.dumps(payload["models"], sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return payload

    def generate(self, request: LLMRequest) -> LLMResponse:
        self._ensure_api_key()
        self._config.validate_model_selection(allow_empty=False)
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None
        for attempt_number in range(1, max(self._config.max_retries, 1) + 1):
            started = self._time_fn()
            try:
                client = self._client_or_create()
                response = client.chat.completions.create(
                    model=request.model,
                    messages=[
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": json.dumps(request.user_payload, ensure_ascii=True)},
                    ],
                    response_format=request.response_format,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    timeout=request.timeout_seconds,
                )
                latency = self._time_fn() - started
                choice = response.choices[0]
                content = (choice.message.content or "").strip()
                usage = getattr(response, "usage", None)
                finish_reason = getattr(choice, "finish_reason", None)
                attempts.append(
                    {
                        "attempt_number": attempt_number,
                        "http_status": 200,
                        "error_type": None,
                        "retryable": False,
                        "delay_before_retry": 0.0,
                        "final_status": "SUCCESS",
                    }
                )
                if not content:
                    raise LLMEmptyResponseError(
                        "DeepSeek returned an empty response",
                        provider="deepseek",
                        attempts=attempts,
                    )
                return LLMResponse(
                    content=content,
                    provider="deepseek",
                    model=request.model,
                    finish_reason=finish_reason,
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    latency_seconds=latency,
                    raw_metadata={
                        "id": getattr(response, "id", None),
                        "created": getattr(response, "created", None),
                        "attempts": attempts,
                    },
                )
            except Exception as exc:
                last_error = exc
                error = self._classify_error(exc, attempts=attempts)
                retryable = isinstance(error, (LLMRateLimitError, LLMProviderUnavailableError, LLMTimeoutError))
                status_code = getattr(error, "status_code", None)
                backoff = self._bounded_backoff_seconds(attempt_number) if retryable else 0.0
                attempts.append(
                    {
                        "attempt_number": attempt_number,
                        "http_status": status_code,
                        "error_type": type(error).__name__,
                        "retryable": retryable,
                        "delay_before_retry": backoff,
                        "final_status": "RETRY" if retryable and attempt_number < self._config.max_retries else "FAILED",
                    }
                )
                if retryable and attempt_number < self._config.max_retries:
                    self._sleep_fn(backoff)
                    continue
                if isinstance(error, LLMProviderError):
                    raise type(error)(
                        str(error),
                        provider="deepseek",
                        status_code=status_code,
                        attempts=attempts,
                    ) from exc
                raise
        raise LLMProviderUnavailableError(
            _mask_secret(str(last_error), self._config.api_key),
            provider="deepseek",
            attempts=attempts,
        )

    def _client_or_create(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(self._config)
        return self._client

    @staticmethod
    def _default_client_factory(config: DeepSeekProviderConfig) -> Any:
        from openai import OpenAI

        base_url = config.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return OpenAI(api_key=config.api_key, base_url=base_url)

    def _ensure_api_key(self) -> None:
        if not self._config.api_key:
            raise LLMAuthenticationError("DEEPSEEK_API_KEY is not configured", provider="deepseek")

    def _classify_error(self, exc: Exception, *, attempts: list[dict[str, Any]]) -> LLMProviderError:
        if isinstance(exc, LLMProviderError):
            return exc
        lowered = _mask_secret(str(exc), self._config.api_key).lower()
        status_code = self._extract_status_code(exc)
        if "timed out" in lowered or "timeout" in lowered:
            return LLMTimeoutError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if status_code == 400 or status_code == 422:
            return LLMInvalidRequestError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if status_code == 401:
            return LLMAuthenticationError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if status_code == 402:
            return LLMInsufficientBalanceError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if status_code == 429:
            return LLMRateLimitError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if status_code in {500, 503}:
            return LLMProviderUnavailableError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if "rate limit" in lowered:
            return LLMRateLimitError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        if "authentication" in lowered or "unauthorized" in lowered:
            return LLMAuthenticationError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)
        return LLMProviderUnavailableError(lowered, provider="deepseek", attempts=attempts, status_code=status_code)

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        for attribute in ("status_code", "http_status"):
            value = getattr(exc, attribute, None)
            if isinstance(value, int):
                return value
        response = getattr(exc, "response", None)
        if response is not None:
            value = getattr(response, "status_code", None)
            if isinstance(value, int):
                return value
        return None

    @staticmethod
    def _extract_request_id(response: Any) -> str | None:
        for attribute in ("request_id", "id"):
            value = getattr(response, attribute, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raw_response = getattr(response, "response", None)
        headers = getattr(raw_response, "headers", None)
        if headers is None:
            return None
        for key in ("x-request-id", "request-id"):
            value = headers.get(key) if hasattr(headers, "get") else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _bounded_backoff_seconds(self, attempt_number: int) -> float:
        base = [1.0, 2.0, 4.0][min(attempt_number - 1, 2)]
        return base + self._jitter_fn()

