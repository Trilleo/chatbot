"""LLM chat in private messages with friends.

Any private text from a friend that isn't a command goes to the model, with the
session's persona and recent context; the reply is sent in parts at a human pace.
"""

import asyncio
import time
from pathlib import Path
from typing import Annotated
from weakref import WeakValueDictionary

from nonebot import (
    get_driver,
    get_plugin_config,
    logger,
    on_command,
    on_message,
    require,
)
from nonebot.adapters.onebot.v11 import Event, Message, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

require("nonebot_plugin_orm")

from src.llm.context import Context, session_key  # noqa: E402
from src.llm.personas import Persona, load_personas  # noqa: E402
from src.llm.provider import (  # noqa: E402
    ChatMessage,
    ChatProvider,
    OpenAICompatibleProvider,
    ProviderError,
    ProviderSettings,
)
from src.llm.replies import NOT_TEXT_REPLY, TOO_LONG_REPLY, error_reply  # noqa: E402
from src.llm.sender import Pacing, send_paced  # noqa: E402
from src.llm.splitter import split_reply  # noqa: E402

from .config import Config  # noqa: E402
from .store import SqlContextStore, get_persona, set_persona  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="llm_chat",
    description="Chat with an LLM in private messages (friends only).",
    usage=(
        "私聊直接发消息即可聊天\n"
        "/清空 (/clear): 清空对话记忆\n"
        "/人设 [名称] (/persona): 查看或切换人设\n"
        "/设置 (/settings): 查看当前设置"
    ),
    config=Config,
)

config = get_plugin_config(Config)
PERSONA_DIR = Path(__file__).parent / "personas"
personas: dict[str, Persona] = load_personas(PERSONA_DIR)
if config.llm_default_persona not in personas:
    raise ValueError(
        f"LLM_DEFAULT_PERSONA={config.llm_default_persona!r} isn't a persona; "
        f"there are: {', '.join(personas)}"
    )

chat_provider: ChatProvider = OpenAICompatibleProvider(
    ProviderSettings(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key.get_secret_value(),
        model=config.llm_model,
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_tokens,
        timeout=config.llm_timeout,
        max_retries=config.llm_max_retries,
        extra_body=config.llm_extra_body,
    )
)
chat_context = Context(
    SqlContextStore(),
    max_messages=config.llm_context_max_messages,
    max_tokens=config.llm_context_max_tokens,
)
pacing = Pacing(
    first_min=config.llm_first_delay_min,
    first_max=config.llm_first_delay_max,
    part_min=config.llm_part_delay_min,
    part_max=config.llm_part_delay_max,
)

# One request at a time per session, so replies stay in order.
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _lock(session: str) -> asyncio.Lock:
    lock = _locks.get(session)
    if lock is None:
        lock = _locks[session] = asyncio.Lock()
    return lock


@get_driver().on_startup
async def _check_api_key() -> None:
    if not config.llm_api_key.get_secret_value():
        logger.warning("LLM_API_KEY is not set: chat replies will fail until it is.")


async def _is_friend_chat(event: Event) -> bool:
    return isinstance(event, PrivateMessageEvent) and event.sub_type == "friend"


async def _is_not_command(event: Event) -> bool:
    # Unknown commands shouldn't go to the model either.
    text = event.get_plaintext().lstrip()
    return not any(
        text.startswith(start) for start in get_driver().config.command_start if start
    )


friend_chat = Rule(_is_friend_chat)

clear_cmd = on_command(
    "clear", aliases={"清空"}, rule=friend_chat, priority=10, block=True
)
persona_cmd = on_command(
    "persona", aliases={"人设"}, rule=friend_chat, priority=10, block=True
)
settings_cmd = on_command(
    "settings", aliases={"设置"}, rule=friend_chat, priority=10, block=True
)
chat = on_message(rule=friend_chat & Rule(_is_not_command), priority=50, block=True)


async def current_persona(session: str) -> Persona:
    """The session's persona (the default if none chosen, or it no longer exists)."""
    name = await get_persona(session)
    return personas.get(name or "", personas[config.llm_default_persona])


@chat.handle()
async def handle_chat(event: PrivateMessageEvent) -> None:
    started_at = time.monotonic()
    session = session_key(event.user_id)
    text = event.get_plaintext().strip()
    if not text or len(text) > config.llm_max_input_chars:
        reply = NOT_TEXT_REPLY if not text else TOO_LONG_REPLY
        await send_paced(chat.send, [reply], pacing, started_at)
        return

    async with _lock(session):
        persona = await current_persona(session)
        question = ChatMessage("user", text)
        messages = [
            ChatMessage("system", persona.system_prompt),
            *await chat_context.window(session),
            question,
        ]
        try:
            result = await chat_provider.complete(messages)
        except ProviderError as e:
            logger.warning(f"LLM request failed for {session}: {type(e).__name__}: {e}")
            await send_paced(chat.send, [error_reply(e)], pacing, started_at)
            return

        await chat_context.add_exchange(
            session, question, ChatMessage("assistant", result.content)
        )
        parts = split_reply(
            result.content, config.llm_reply_max_chars, config.llm_reply_max_parts
        )
        logger.info(
            f"LLM reply for {session}: {len(result.content)} chars in {len(parts)} "
            f"part(s), tokens in={result.prompt_tokens} out={result.completion_tokens}"
        )
        await send_paced(chat.send, parts, pacing, started_at)


@clear_cmd.handle()
async def handle_clear(event: PrivateMessageEvent) -> None:
    await chat_context.clear(session_key(event.user_id))
    await clear_cmd.finish("对话记忆已清空。")


@persona_cmd.handle()
async def handle_persona(
    event: PrivateMessageEvent, args: Annotated[Message, CommandArg()]
) -> None:
    session = session_key(event.user_id)
    name = args.extract_plain_text().strip()
    current = await current_persona(session)
    if not name:
        lines = [
            f"{'▶' if p.name == current.name else '·'} {p.name}"
            + (f"：{p.description}" if p.description else "")
            for p in personas.values()
        ]
        await persona_cmd.finish(
            "可用人设（▶ 为当前）：\n" + "\n".join(lines) + "\n切换：/人设 <名称>"
        )
    if name not in personas:
        await persona_cmd.finish(f"没有叫「{name}」的人设。发送 /人设 查看全部。")
    await set_persona(session, name)
    await persona_cmd.finish(
        f"已切换到人设「{name}」。之前的对话记忆仍保留，可用 /清空 清除。"
    )


@settings_cmd.handle()
async def handle_settings(event: PrivateMessageEvent) -> None:
    session = session_key(event.user_id)
    persona = await current_persona(session)
    remembered = len(await chat_context.window(session))
    temperature = (
        "默认" if config.llm_temperature is None else f"{config.llm_temperature:g}"
    )
    await settings_cmd.finish(
        "当前设置：\n"
        f"模型：{config.llm_model}\n"
        f"人设：{persona.name}\n"
        f"温度：{temperature}\n"
        f"最大输出：{config.llm_max_tokens} tokens\n"
        f"对话记忆：{remembered} 条（最多 {config.llm_context_max_messages} 条，"
        f"约 {config.llm_context_max_tokens} tokens）"
    )
