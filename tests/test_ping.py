from nonebot.adapters.onebot.v11 import Adapter, Bot, Message
from nonebug import App

from tests.conftest import SUPERUSER_ID
from tests.helpers import BOT_ID, private_message


async def test_ping_answers_pong(app: App) -> None:
    from src.plugins.ping import ping

    async with app.test_matcher(ping) as ctx:
        adapter = ctx.create_adapter(base=Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter, self_id=BOT_ID)
        event = private_message("/ping")
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, "pong", result=None)
        ctx.should_finished(ping)


async def test_echo_repeats_for_superusers(app: App) -> None:
    from src.plugins.ping import echo

    async with app.test_matcher(echo) as ctx:
        adapter = ctx.create_adapter(base=Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter, self_id=BOT_ID)
        event = private_message("/echo hello there", user_id=SUPERUSER_ID)
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, Message("hello there"), result=None)
        ctx.should_finished(echo)


async def test_echo_ignores_other_users(app: App) -> None:
    from src.plugins.ping import echo

    async with app.test_matcher(echo) as ctx:
        adapter = ctx.create_adapter(base=Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter, self_id=BOT_ID)
        ctx.receive_event(bot, private_message("/echo hello"))
        ctx.should_not_pass_permission(echo)
