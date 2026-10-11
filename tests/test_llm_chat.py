"""The llm_chat matchers end to end, with a fake provider and no delays."""

from typing import Any

import pytest
from nonebot.adapters.onebot.v11 import Adapter, Bot
from nonebug import App

from src.llm.provider import (
    ChatMessage,
    ChatResult,
    ProviderError,
    ProviderTimeoutError,
)
from src.llm.replies import ERROR_REPLIES, NOT_TEXT_REPLY
from src.llm.sender import Pacing
from tests.helpers import BOT_ID, private_message


class FakeProvider:
    def __init__(self, *replies: str | ProviderError) -> None:
        self.replies = list(replies)
        self.requests: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage]) -> ChatResult:
        self.requests.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, ProviderError):
            raise reply
        return ChatResult(content=reply, prompt_tokens=1, completion_tokens=1)


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    import src.plugins.llm_chat as llm_chat

    provider = FakeProvider()
    monkeypatch.setattr(llm_chat, "chat_provider", provider)
    monkeypatch.setattr(llm_chat, "pacing", Pacing(0, 0, 0, 0))
    return provider


def make_bot(ctx: Any) -> Bot:  # Any: nonebug has no type information
    adapter = ctx.create_adapter(base=Adapter)
    bot: Bot = ctx.create_bot(base=Bot, adapter=adapter, self_id=BOT_ID)
    return bot


async def test_replies_with_context_and_persona(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat

    fake_provider.replies = ["你好呀", "我记得你说过你好"]
    for text, reply in [("你好", "你好呀"), ("我刚才说了什么？", "我记得你说过你好")]:
        async with app.test_matcher(chat) as ctx:
            bot = make_bot(ctx)
            event = private_message(text, user_id=30001)
            ctx.receive_event(bot, event)
            ctx.should_call_send(event, reply, result=None)

    first, second = fake_provider.requests
    assert first[0].role == "system"
    assert first[1:] == [ChatMessage("user", "你好")]
    assert second[1:] == [
        ChatMessage("user", "你好"),
        ChatMessage("assistant", "你好呀"),
        ChatMessage("user", "我刚才说了什么？"),
    ]


async def test_long_replies_are_sent_in_parts(
    app: App, fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.plugins.llm_chat as llm_chat
    from src.plugins.llm_chat import chat

    monkeypatch.setattr(llm_chat.config, "llm_reply_max_chars", 50)
    paragraph = "这是一段比较长的回复内容。" * 3  # 39 characters
    fake_provider.replies = [f"{paragraph}\n\n{paragraph}"]
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("讲个长故事", user_id=30002)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, paragraph, result=None)
        ctx.should_call_send(event, paragraph, result=None)


async def test_errors_get_a_short_reply_and_are_not_remembered(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat

    fake_provider.replies = [ProviderTimeoutError("slow"), "好的"]
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("在吗", user_id=30003)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, ERROR_REPLIES[ProviderTimeoutError], result=None)
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("在吗", user_id=30003)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "好的", result=None)
    assert fake_provider.requests[1][1:] == [ChatMessage("user", "在吗")]


async def test_non_text_messages_are_not_sent_to_the_model(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat

    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("", user_id=30004)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, NOT_TEXT_REPLY, result=None)
    assert fake_provider.requests == []


async def test_ignores_temporary_chats_from_groups(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat

    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        ctx.receive_event(bot, private_message("你好", user_id=30005, sub_type="group"))
        ctx.should_not_pass_rule(chat)
    assert fake_provider.requests == []


async def test_unknown_commands_are_not_sent_to_the_model(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat

    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        ctx.receive_event(bot, private_message("/nosuchcommand", user_id=30006))
        ctx.should_not_pass_rule(chat)


async def test_clear_forgets_the_context(app: App, fake_provider: FakeProvider) -> None:
    from src.plugins.llm_chat import chat, clear_cmd

    fake_provider.replies = ["一", "二"]
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("第一句", user_id=30007)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "一", result=None)
    async with app.test_matcher(clear_cmd) as ctx:
        bot = make_bot(ctx)
        event = private_message("/清空", user_id=30007)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "对话记忆已清空。", result=None)
        ctx.should_finished(clear_cmd)
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("第二句", user_id=30007)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "二", result=None)
    assert fake_provider.requests[1][1:] == [ChatMessage("user", "第二句")]


async def test_persona_lists_and_switches(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import chat, persona_cmd, personas

    async with app.test_matcher(persona_cmd) as ctx:
        bot = make_bot(ctx)
        event = private_message("/人设", user_id=30008)
        ctx.receive_event(bot, event)
        listing = (
            "可用人设（▶ 为当前）：\n"
            "· brief：简洁直接，回答尽量短\n"
            "▶ default：友好、耐心的聊天助手（默认）\n"
            "切换：/人设 <名称>"
        )
        ctx.should_call_send(event, listing, result=None)
    async with app.test_matcher(persona_cmd) as ctx:
        bot = make_bot(ctx)
        event = private_message("/人设 nope", user_id=30008)
        ctx.receive_event(bot, event)
        ctx.should_call_send(
            event, "没有叫「nope」的人设。发送 /人设 查看全部。", result=None
        )
    async with app.test_matcher(persona_cmd) as ctx:
        bot = make_bot(ctx)
        event = private_message("/persona brief", user_id=30008)
        ctx.receive_event(bot, event)
        ctx.should_call_send(
            event,
            "已切换到人设「brief」。之前的对话记忆仍保留，可用 /清空 清除。",
            result=None,
        )

    fake_provider.replies = ["嗯"]
    async with app.test_matcher(chat) as ctx:
        bot = make_bot(ctx)
        event = private_message("你好", user_id=30008)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "嗯", result=None)
    assert fake_provider.requests[0][0].content == personas["brief"].system_prompt


async def test_settings_shows_the_session(
    app: App, fake_provider: FakeProvider
) -> None:
    from src.plugins.llm_chat import config, settings_cmd

    async with app.test_matcher(settings_cmd) as ctx:
        bot = make_bot(ctx)
        event = private_message("/设置", user_id=30009)
        ctx.receive_event(bot, event)
        ctx.should_call_send(
            event,
            "当前设置：\n"
            f"模型：{config.llm_model}\n"
            "人设：default\n"
            "温度：默认\n"
            f"最大输出：{config.llm_max_tokens} tokens\n"
            f"对话记忆：0 条（最多 {config.llm_context_max_messages} 条，"
            f"约 {config.llm_context_max_tokens} tokens）",
            result=None,
        )
