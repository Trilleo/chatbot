"""Builders for OneBot v11 events in tests."""

import time

from nonebot.adapters.onebot.v11 import Message, PrivateMessageEvent
from nonebot.adapters.onebot.v11.event import Sender

BOT_ID = "10000"


def private_message(
    text: str, user_id: int = 20002, sub_type: str = "friend"
) -> PrivateMessageEvent:
    """A private message from `user_id` to the bot (`sub_type` "group": a temporary
    chat started from a group)."""
    return PrivateMessageEvent(
        time=int(time.time()),
        self_id=int(BOT_ID),
        post_type="message",
        sub_type=sub_type,
        user_id=user_id,
        message_type="private",
        message_id=1,
        message=Message(text),
        original_message=Message(text),
        raw_message=text,
        font=0,
        sender=Sender(user_id=user_id, nickname="tester"),
        to_me=True,
    )
