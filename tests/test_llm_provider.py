import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx2
import pytest

from src.llm.provider import (
    ChatMessage,
    OpenAICompatibleProvider,
    ProviderConfigError,
    ProviderEmptyResponseError,
    ProviderError,
    ProviderRateLimitError,
    ProviderSettings,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

SETTINGS = ProviderSettings(
    base_url="https://llm.test/v1",
    api_key="test-key",
    model="test-model",
    temperature=None,
    max_tokens=100,
    timeout=5.0,
    max_retries=0,
    extra_body={"thinking": {"type": "enabled"}},
)
MESSAGES = [ChatMessage("system", "be nice"), ChatMessage("user", "hi")]


def completion(content: str | None, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


def provider_with(
    handler: Callable[[httpx2.Request], httpx2.Response],
    settings: ProviderSettings = SETTINGS,
) -> OpenAICompatibleProvider:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenAICompatibleProvider(settings, http_client=client)


async def test_returns_the_reply_and_usage() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=completion("  hello  "))

    result = await provider_with(handler).complete(MESSAGES)

    assert result.content == "hello"
    assert (result.prompt_tokens, result.completion_tokens) == (12, 5)
    (request,) = requests
    assert str(request.url) == "https://llm.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 100
    assert body["thinking"] == {"type": "enabled"}
    assert "temperature" not in body
    assert body["messages"] == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]


async def test_sends_temperature_when_set() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=completion("ok"))

    await provider_with(handler, replace(SETTINGS, temperature=0.3)).complete(MESSAGES)
    assert bodies[0]["temperature"] == 0.3


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, ProviderRateLimitError),
        (401, ProviderConfigError),
        (403, ProviderConfigError),
        (404, ProviderConfigError),
        (400, ProviderUnavailableError),
        (402, ProviderUnavailableError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
    ],
)
async def test_maps_http_errors(status: int, error: type[ProviderError]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(error):
        await provider_with(handler).complete(MESSAGES)


async def test_maps_timeouts() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeoutError):
        await provider_with(handler).complete(MESSAGES)


async def test_maps_connection_errors() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(ProviderUnavailableError):
        await provider_with(handler).complete(MESSAGES)


@pytest.mark.parametrize("content", [None, "", "   "])
async def test_empty_replies_are_errors(content: str | None) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=completion(content, finish_reason="length"))

    with pytest.raises(ProviderEmptyResponseError, match="finish_reason=length"):
        await provider_with(handler).complete(MESSAGES)


async def test_missing_api_key_fails_without_a_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    with pytest.raises(ProviderConfigError):
        await provider_with(handler, replace(SETTINGS, api_key="")).complete(MESSAGES)
