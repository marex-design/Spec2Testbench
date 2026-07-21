from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from spec2testbench.application.ports.llm_provider import (
    LLMAuthenticationError,
    LLMInsufficientBalanceError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMRequest,
)
from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig


@dataclass
class FakeMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str = "stop"


@dataclass
class FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5
    total_tokens: int = 15


@dataclass
class FakeResponse:
    choices: list[FakeChoice]
    usage: FakeUsage = field(default_factory=FakeUsage)
    id: str = "resp_fake"
    created: int = 0


class FakeError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.models = type("Models", (), {"list": self._list_models})()
        self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self._create})()})()

    def _list_models(self):
        data = [type("Model", (), {"id": item})() for item in ["deepseek-chat", "deepseek-reasoner"]]
        return type("Response", (), {"data": data})()

    def _create(self, **kwargs):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def build_provider(responses, *, api_key: str = "secret-key", sleep_calls: list[float] | None = None):
    config = DeepSeekProviderConfig(api_key=api_key, max_retries=3)
    return DeepSeekProvider(
        config,
        client_factory=lambda cfg: FakeClient(responses),
        sleep_fn=(lambda seconds: sleep_calls.append(seconds)) if sleep_calls is not None else None,
        jitter_fn=lambda: 0.0,
    )


def build_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="system",
        user_payload={"task": "Generate JSON"},
        response_format={"type": "json_object"},
        model="deepseek-chat",
        temperature=0.1,
        max_tokens=256,
        timeout_seconds=30.0,
        metadata={},
    )


def test_deepseek_provider_requires_api_key():
    provider = build_provider([], api_key="")
    with pytest.raises(LLMAuthenticationError):
        provider.list_models()


def test_deepseek_provider_list_models_returns_ids():
    provider = build_provider([FakeResponse([FakeChoice(FakeMessage("{}"))])])
    assert provider.list_models() == ["deepseek-chat", "deepseek-reasoner"]


def test_deepseek_provider_generate_retries_429_then_succeeds():
    sleep_calls: list[float] = []
    provider = build_provider(
        [
            FakeError("rate limited", status_code=429),
            FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))]),
        ],
        sleep_calls=sleep_calls,
    )
    response = provider.generate(build_request())
    assert response.content == '{"ok": true}'
    assert sleep_calls == [1.0]
    assert response.raw_metadata["attempts"][-1]["final_status"] == "SUCCESS"


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, LLMAuthenticationError),
        (402, LLMInsufficientBalanceError),
        (422, LLMInvalidRequestError),
    ],
)
def test_deepseek_provider_does_not_retry_non_retryable_errors(status_code, expected_exception):
    sleep_calls: list[float] = []
    provider = build_provider([FakeError("provider failed", status_code=status_code)], sleep_calls=sleep_calls)
    with pytest.raises(expected_exception):
        provider.generate(build_request())
    assert sleep_calls == []


@pytest.mark.parametrize("status_code", [500, 503])
def test_deepseek_provider_retries_provider_unavailable(status_code):
    sleep_calls: list[float] = []
    provider = build_provider(
        [
            FakeError("temporary failure", status_code=status_code),
            FakeError("temporary failure", status_code=status_code),
            FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))]),
        ],
        sleep_calls=sleep_calls,
    )
    response = provider.generate(build_request())
    assert response.content == '{"ok": true}'
    assert sleep_calls == [1.0, 2.0]


def test_deepseek_provider_masks_secret_in_errors():
    provider = build_provider([FakeError("Authorization failed for secret-key", status_code=401)])
    with pytest.raises(LLMAuthenticationError) as exc_info:
        provider.generate(build_request())
    assert "secret-key" not in str(exc_info.value)
