from src.llm.context import (
    Context,
    MemoryContextStore,
    apply_window,
    estimate_tokens,
    message_tokens,
    session_key,
)
from src.llm.provider import ChatMessage


def user(text: str) -> ChatMessage:
    return ChatMessage("user", text)


def bot(text: str) -> ChatMessage:
    return ChatMessage("assistant", text)


def exchange(n: int) -> list[ChatMessage]:
    return [user(f"q{n}"), bot(f"a{n}")]


def test_estimate_tokens_weights_chinese_more_than_ascii() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界你好世界你好") == 6  # 10 x 0.6
    assert estimate_tokens("a" * 10) == 3  # 10 x 0.3
    assert estimate_tokens("你好ab") == 2  # 1.2 + 0.6, rounded up


def test_session_keys() -> None:
    assert session_key(123) == "private:123"
    assert session_key(123, group_id=456) == "group:456:123"


def test_window_keeps_everything_within_limits() -> None:
    history = exchange(1) + exchange(2)
    window = apply_window(history, max_messages=10, max_tokens=1000)
    assert window.kept == history
    assert window.dropped == []


def test_window_caps_message_count() -> None:
    history = exchange(1) + exchange(2) + exchange(3)
    window = apply_window(history, max_messages=4, max_tokens=1000)
    assert window.kept == exchange(2) + exchange(3)
    assert window.dropped == exchange(1)


def test_window_caps_tokens() -> None:
    history = [user("长" * 100), bot("好"), user("短"), bot("嗯")]
    budget = sum(message_tokens(m) for m in history[2:])
    window = apply_window(history, max_messages=10, max_tokens=budget)
    assert window.kept == history[2:]


def test_window_never_starts_with_a_reply() -> None:
    history = exchange(1) + exchange(2)
    window = apply_window(history, max_messages=3, max_tokens=1000)
    assert window.kept == exchange(2)
    assert window.dropped == exchange(1)


def test_window_of_nothing() -> None:
    window = apply_window([], max_messages=4, max_tokens=100)
    assert window.kept == []
    assert window.dropped == []


async def test_context_trims_the_store_to_the_window() -> None:
    store = MemoryContextStore()
    context = Context(store, max_messages=4, max_tokens=1000)
    for n in range(1, 4):
        await context.add_exchange("s", user(f"q{n}"), bot(f"a{n}"))
    assert await store.history("s") == exchange(2) + exchange(3)
    assert await context.window("s") == exchange(2) + exchange(3)


async def test_context_sessions_are_separate_and_clearable() -> None:
    context = Context(MemoryContextStore(), max_messages=10, max_tokens=1000)
    await context.add_exchange("a", user("q"), bot("a"))
    await context.add_exchange("b", user("x"), bot("y"))
    await context.clear("a")
    assert await context.window("a") == []
    assert await context.window("b") == [user("x"), bot("y")]


class RecordingSummarizer:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    async def summarize(
        self, session: str, dropped: list[ChatMessage]
    ) -> ChatMessage | None:
        self.calls.append(dropped)
        return ChatMessage("system", f"summary of {len(dropped)}")


async def test_context_hands_dropped_messages_to_the_summarizer() -> None:
    summarizer = RecordingSummarizer()
    store = MemoryContextStore()
    context = Context(store, max_messages=5, max_tokens=1000, summarizer=summarizer)
    for n in range(1, 4):
        await context.add_exchange("s", user(f"q{n}"), bot(f"a{n}"))
    assert summarizer.calls == [exchange(1)]
    assert await store.history("s") == [
        ChatMessage("system", "summary of 2"),
        *exchange(2),
        *exchange(3),
    ]
