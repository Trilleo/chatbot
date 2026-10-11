"""Checks the whole chain: `/ping` answers; `/echo <text>` repeats (superusers)."""

from typing import Annotated

from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="ping",
    description="Checks that QQ → NapCat → NoneBot → QQ works.",
    usage="/ping\n/echo <text> (superusers only)",
    config=Config,
)

config = get_plugin_config(Config)

ping = on_command("ping", priority=10, block=True)
# Superusers only: echoing arbitrary text for anyone is an easy abuse vector.
echo = on_command("echo", permission=SUPERUSER, priority=10, block=True)


@ping.handle()
async def handle_ping() -> None:
    await ping.finish(config.ping_reply)


@echo.handle()
async def handle_echo(args: Annotated[Message, CommandArg()]) -> None:
    if not args.extract_plain_text().strip():
        await echo.finish("Usage: /echo <text>")
    await echo.finish(args)
