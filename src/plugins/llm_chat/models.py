"""Database tables (nonebot-plugin-orm). Changing them needs a migration:
`uv run python bot.py orm revision -m "..."` (README.md)."""

from datetime import UTC, datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class StoredMessage(Model):
    """One message of a session's context, in order of `id`."""

    __tablename__ = "llm_chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionSettings(Model):
    """A session's choices (the persona); a missing row means the defaults."""

    __tablename__ = "llm_chat_session"

    session: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
