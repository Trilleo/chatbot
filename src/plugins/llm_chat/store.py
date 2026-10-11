"""Database-backed storage for contexts and session settings."""

from collections.abc import Sequence
from typing import cast

from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from src.llm.provider import ChatMessage, Role

from .models import SessionSettings, StoredMessage


class SqlContextStore:
    """A ContextStore in the bot's database (survives restarts and deploys)."""

    async def history(self, session: str) -> list[ChatMessage]:
        async with get_session() as db:
            rows = await db.scalars(
                select(StoredMessage)
                .where(StoredMessage.session == session)
                .order_by(StoredMessage.id)
            )
            return [ChatMessage(cast(Role, r.role), r.content) for r in rows]

    async def append(self, session: str, messages: Sequence[ChatMessage]) -> None:
        async with get_session() as db:
            db.add_all(_rows(session, messages))
            await db.commit()

    async def replace(self, session: str, messages: Sequence[ChatMessage]) -> None:
        async with get_session() as db:
            await db.execute(
                delete(StoredMessage).where(StoredMessage.session == session)
            )
            db.add_all(_rows(session, messages))
            await db.commit()

    async def clear(self, session: str) -> None:
        async with get_session() as db:
            await db.execute(
                delete(StoredMessage).where(StoredMessage.session == session)
            )
            await db.commit()


def _rows(session: str, messages: Sequence[ChatMessage]) -> list[StoredMessage]:
    return [
        StoredMessage(session=session, role=m.role, content=m.content) for m in messages
    ]


async def get_persona(session: str) -> str | None:
    """The session's chosen persona, or None for the default."""
    async with get_session() as db:
        settings = await db.get(SessionSettings, session)
        return settings.persona if settings else None


async def set_persona(session: str, persona: str) -> None:
    """Remember the session's persona."""
    async with get_session() as db:
        settings = await db.get(SessionSettings, session)
        if settings is None:
            db.add(SessionSettings(session=session, persona=persona))
        else:
            settings.persona = persona
        await db.commit()
