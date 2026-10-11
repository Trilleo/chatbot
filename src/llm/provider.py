"""LLM providers: an interface and an OpenAI-compatible implementation.

Works with any server that speaks the chat completions API (DeepSeek, other cloud
providers, a local server) by changing LLM_BASE_URL / LLM_MODEL only.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx2
import openai
from nonebot import logger
from openai.types.chat import ChatCompletionMessageParam

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message of a conversation."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ChatResult:
    """A provider's reply and its token usage (None when not reported)."""

    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ProviderError(Exception):
    """A request failed; subclasses say why (each gets its own message for users)."""


class ProviderTimeoutError(ProviderError):
    """No reply in time."""


class ProviderRateLimitError(ProviderError):
    """Too many requests (HTTP 429)."""


class ProviderConfigError(ProviderError):
    """Missing or rejected credentials, or a model or URL that doesn't exist."""


class ProviderEmptyResponseError(ProviderError):
    """The reply had no text (e.g. max tokens spent on reasoning)."""


class ProviderUnavailableError(ProviderError):
    """Anything else: connection errors, server errors, rejected requests."""


class ChatProvider(Protocol):
    """Something that answers a conversation."""

    async def complete(self, messages: list[ChatMessage]) -> ChatResult:
        """The assistant's reply to `messages`; raises ProviderError on failure."""
        ...


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    base_url: str
    api_key: str
    model: str
    temperature: float | None
    max_tokens: int
    timeout: float
    max_retries: int
    extra_body: dict[str, Any]


class OpenAICompatibleProvider:
    """Chat completions over the OpenAI API format, without streaming."""

    def __init__(
        self, settings: ProviderSettings, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._client = openai.AsyncOpenAI(
            base_url=settings.base_url,
            # The SDK insists on a key; an empty one fails at request time instead,
            # which ProviderConfigError reports.
            api_key=settings.api_key or "missing",
            timeout=settings.timeout,
            max_retries=settings.max_retries,
            http_client=http_client,
        )

    async def complete(self, messages: list[ChatMessage]) -> ChatResult:
        if not self._settings.api_key:
            raise ProviderConfigError("LLM_API_KEY is not set")
        params = [_to_param(m) for m in messages]
        try:
            completion = await self._client.chat.completions.create(
                model=self._settings.model,
                messages=params,
                max_tokens=self._settings.max_tokens,
                temperature=(
                    self._settings.temperature
                    if self._settings.temperature is not None
                    else openai.omit
                ),
                extra_body=self._settings.extra_body or None,
            )
        except openai.APITimeoutError as e:
            raise ProviderTimeoutError(str(e)) from e
        except openai.RateLimitError as e:
            raise ProviderRateLimitError(_describe(e)) from e
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
        ) as e:
            raise ProviderConfigError(_describe(e)) from e
        except openai.APIError as e:
            raise ProviderUnavailableError(_describe(e)) from e

        choice = completion.choices[0] if completion.choices else None
        content = (choice.message.content or "").strip() if choice else ""
        if not content:
            reason = choice.finish_reason if choice else "no choices"
            raise ProviderEmptyResponseError(f"empty reply (finish_reason={reason})")
        usage = completion.usage
        if usage is not None:
            logger.debug(
                f"LLM usage: prompt={usage.prompt_tokens} "
                f"completion={usage.completion_tokens}"
            )
        return ChatResult(
            content=content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


def _to_param(message: ChatMessage) -> ChatCompletionMessageParam:
    match message.role:
        case "system":
            return {"role": "system", "content": message.content}
        case "user":
            return {"role": "user", "content": message.content}
        case "assistant":
            return {"role": "assistant", "content": message.content}


def _describe(error: openai.APIError) -> str:
    """Status and message of an API error, for the server log (never the key)."""
    status = getattr(error, "status_code", None)
    return f"HTTP {status}: {error.message}" if status else error.message
