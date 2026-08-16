from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from spec2testbench.application.ports.llm_provider import (
    LLMAuthenticationError,
    LLMInsufficientBalanceError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMRequest,
)
from spec2testbench.infrastructure.llm.deepseek_provider import (
    LEGACY_DEEPSEEK_ALIASES,
    DeepSeekProvider,
    DeepSeekProviderConfig,
)


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
    request_id: str | None = None
    response: object | None = None


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
        data = [
            type("Model", (), {"id": item, "owned_by": "deepseek"})()
            for item in ["deepseek-chat", "deepseek-reasoner"]
        ]
        return type("Response", (), {"data": data, "request_id": "req_models"})()

    def _create(self, **kwargs):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def build_provider(responses, *, api_key: str = "secret-key", sleep_calls: list[float] | None = None):
    config = DeepSeekProviderConfig(api_key=api_key, model="deepseek-current-model", max_retries=3)
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


def test_deepseek_provider_discover_models_returns_metadata():
    provider = build_provider([FakeResponse([FakeChoice(FakeMessage("{}"))])])
    discovery = provider.discover_models()
    assert discovery["http_status"] == 200
    assert discovery["request_id"] == "req_models"
    assert discovery["models"][0]["owned_by"] == "deepseek"
    assert discovery["response_sha256"]


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


def test_deepseek_provider_generate_exposes_success_metadata():
    raw_response = type("RawResponse", (), {"status_code": 200, "headers": {"x-request-id": "req_chat", "content-type": "application/json"}})()
    provider = build_provider([FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))], request_id="req_chat", response=raw_response)])
    response = provider.generate(build_request())
    assert response.raw_metadata["http_status"] == 200
    assert response.raw_metadata["http_status_observation"] == 200
    assert response.raw_metadata["request_id"] == "req_chat"
    assert response.raw_metadata["response_headers"]["content-type"] == "application/json"


def test_deepseek_provider_generate_uses_http_status_sentinel_when_unavailable():
    provider = build_provider([FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))])])
    response = provider.generate(build_request())
    assert response.raw_metadata["http_status"] is None
    assert response.raw_metadata["http_status_observation"] == "HTTP_STATUS_NOT_EXPOSED_BY_CURRENT_CLIENT_PATH"


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


def test_deepseek_provider_config_requires_explicit_model():
    config = DeepSeekProviderConfig(api_key="secret-key", model="")
    with pytest.raises(ValueError, match="DEEPSEEK_MODEL"):
        config.validate_model_selection()


def test_deepseek_provider_rejects_legacy_alias_by_default():
    legacy_model = next(iter(LEGACY_DEEPSEEK_ALIASES))
    config = DeepSeekProviderConfig(api_key="secret-key", model=legacy_model)
    with pytest.raises(ValueError, match="Legacy DeepSeek alias"):
        config.validate_model_selection()


def test_deepseek_provider_can_allow_legacy_alias_for_noncanonical_usage():
    legacy_model = next(iter(LEGACY_DEEPSEEK_ALIASES))
    config = DeepSeekProviderConfig(api_key="secret-key", model=legacy_model)
    config.validate_model_selection(allow_legacy_alias=True)


def test_deepseek_provider_passes_top_p_to_client():
    captured = {}

    class CapturingClient(FakeClient):
        def _create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))])

    config = DeepSeekProviderConfig(api_key="secret-key", model="deepseek-current-model", max_retries=1)
    provider = DeepSeekProvider(
        config,
        client_factory=lambda cfg: CapturingClient([]),
        jitter_fn=lambda: 0.0,
    )
    request = replace(build_request(), top_p=0.73)
    provider.generate(request)
    assert captured["top_p"] == pytest.approx(0.73)
