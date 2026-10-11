"""Per-session conversation context: a sliding window of earlier messages.

Sessions are keyed by `session_key()`: one per private chat now, one per user in a
group later. The store keeps a session's recent messages; `apply_window` picks what is
sent with the next request. Messages that fall out of the window are handed to a
`Summarizer` first, so summarization can be added later without changing callers.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .provider import ChatMessage

# DeepSeek's rule of thumb: about 0.6 tokens per Chinese character and 0.3 per
# English character. Close enough for a budget; real usage is logged per request.
_CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")
_MESSAGE_OVERHEAD = 4
"""Tokens for a message's role and separators."""


def estimate_tokens(text: str) -> int:
    """Rough token count of `text` (CJK-aware)."""
    cjk = len(_CJK.findall(text))
    return math.ceil(cjk * 0.6 + (len(text) - cjk) * 0.3)


def message_tokens(message: ChatMessage) -> int:
    """Rough token count of a message, overhead included."""
    return estimate_tokens(message.content) + _MESSAGE_OVERHEAD


@dataclass(frozen=True, slots=True)
class Window:
    """The messages to send, and the older ones that didn't fit."""

    kept: list[ChatMessage]
    dropped: list[ChatMessage]


def apply_window(
    history: Sequence[ChatMessage], max_messages: int, max_tokens: int
) -> Window:
    """Keep the newest messages within both limits.

    The kept part never starts with an assistant message: a reply without its
    question confuses models, so it's dropped along with the question.
    """
    kept: list[ChatMessage] = []
    budget = max_tokens
    for message in reversed(history):
        cost = message_tokens(message)
        if len(kept) >= max_messages or cost > budget:
            break
        kept.append(message)
        budget -= cost
    kept.reverse()
    while kept and kept[0].role == "assistant":
        kept.pop(0)
    return Window(kept=kept, dropped=list(history[: len(history) - len(kept)]))


def session_key(user_id: int, group_id: int | None = None) -> str:
    """The context key: per private chat, or per user within a group."""
    if group_id is None:
        return f"private:{user_id}"
    return f"group:{group_id}:{user_id}"


class Summarizer(Protocol):
    """Condenses messages leaving the window (for a future summary feature)."""

    async def summarize(
        self, session: str, dropped: list[ChatMessage]
    ) -> ChatMessage | None:
        """A message standing in for `dropped`, or None to forget them."""
        ...


class ForgetSummarizer:
    """The default: messages leaving the window are forgotten."""

    async def summarize(
        self, session: str, dropped: list[ChatMessage]
    ) -> ChatMessage | None:
        return None


class ContextStore(Protocol):
    """Where sessions' messages are kept."""

    async def history(self, session: str) -> list[ChatMessage]:
        """The session's stored messages, oldest first."""
        ...

    async def append(self, session: str, messages: Sequence[ChatMessage]) -> None:
        """Add messages to the end of the session."""
        ...

    async def replace(self, session: str, messages: Sequence[ChatMessage]) -> None:
        """Make `messages` the session's whole history."""
        ...

    async def clear(self, session: str) -> None:
        """Forget the session's messages."""
        ...


class MemoryContextStore:
    """A ContextStore in a dict, for tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[ChatMessage]] = {}

    async def history(self, session: str) -> list[ChatMessage]:
        return list(self._sessions.get(session, []))

    async def append(self, session: str, messages: Sequence[ChatMessage]) -> None:
        self._sessions.setdefault(session, []).extend(messages)

    async def replace(self, session: str, messages: Sequence[ChatMessage]) -> None:
        self._sessions[session] = list(messages)

    async def clear(self, session: str) -> None:
        self._sessions.pop(session, None)


class Context:
    """A ContextStore with the window applied: what the chat handler uses."""

    def __init__(
        self,
        store: ContextStore,
        max_messages: int,
        max_tokens: int,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.store = store
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.summarizer: Summarizer = summarizer or ForgetSummarizer()

    async def window(self, session: str) -> list[ChatMessage]:
        """The earlier messages to send with the next request."""
        history = await self.store.history(session)
        return apply_window(history, self.max_messages, self.max_tokens).kept

    async def add_exchange(
        self, session: str, question: ChatMessage, answer: ChatMessage
    ) -> None:
        """Record a question and its answer, then trim what fell out of the window.

        Trimming happens here, so the store never grows past the window.
        """
        await self.store.append(session, [question, answer])
        history = await self.store.history(session)
        window = apply_window(history, self.max_messages, self.max_tokens)
        if not window.dropped:
            return
        summary = await self.summarizer.summarize(session, window.dropped)
        kept = window.kept if summary is None else [summary, *window.kept]
        await self.store.replace(session, kept)

    async def clear(self, session: str) -> None:
        """Forget the session's context."""
        await self.store.clear(session)
