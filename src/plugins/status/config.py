from pydantic import BaseModel


class Config(BaseModel):
    """Settings for the status plugin (keys are prefixed with `STATUS_`)."""

    status_version: str = "dev"
    """The running release (the git SHA, set by the Docker image)."""
