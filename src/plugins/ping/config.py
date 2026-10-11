from pydantic import BaseModel


class Config(BaseModel):
    """Settings for the ping plugin (keys are prefixed with `PING_`)."""

    ping_reply: str = "pong"
    """What `/ping` answers."""
