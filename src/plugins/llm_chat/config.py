from typing import Any, Self

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class Config(BaseModel):
    """Settings for LLM chat (keys are prefixed with `LLM_`)."""

    # Provider: any OpenAI-compatible chat completions API.
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "deepseek-flash"
    llm_temperature: float | None = None
    """None: the provider's default (DeepSeek ignores it in thinking mode)."""
    llm_max_tokens: int = Field(default=8192, gt=0)
    """Output cap per reply; with thinking on it includes the reasoning."""
    llm_timeout: float = Field(default=120.0, gt=0)
    """Seconds per request attempt; thinking replies can take a while."""
    llm_max_retries: int = Field(default=1, ge=0)
    """Retries on timeouts, rate limits and server errors (the SDK backs off)."""
    llm_extra_body: dict[str, Any] = {}
    """Extra JSON fields for each request, e.g. DeepSeek's
    {"thinking": {"type": "disabled"}} or {"reasoning_effort": "low"}."""

    # Context: the sliding window of earlier messages sent with each request.
    llm_context_max_messages: int = Field(default=20, ge=2)
    llm_context_max_tokens: int = Field(default=6000, gt=0)
    """Estimated tokens of earlier messages (the persona and new message excluded)."""

    llm_max_input_chars: int = Field(default=2000, gt=0)
    """Longer messages are refused instead of sent to the model."""

    # Personas: files in src/plugins/llm_chat/personas/<name>.md.
    llm_default_persona: str = "default"

    # Sending, paced like a person typing (account safety).
    llm_reply_max_chars: int = Field(default=300, ge=50)
    """Longer replies are split into several messages of about this size."""
    llm_reply_max_parts: int = Field(default=5, ge=1)
    """At most this many messages per reply; the rest is cut off."""
    llm_first_delay_min: float = Field(default=1.0, ge=0)
    llm_first_delay_max: float = Field(default=3.0, ge=0)
    """Seconds before the first message, counted from when the message arrived."""
    llm_part_delay_min: float = Field(default=1.0, ge=0)
    llm_part_delay_max: float = Field(default=3.0, ge=0)
    """Seconds between the messages of a split reply."""

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _empty_is_default(cls, value: object) -> object:
        # `LLM_TEMPERATURE=` in .env means "not set".
        return None if value == "" else value

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        if self.llm_first_delay_min > self.llm_first_delay_max:
            raise ValueError("LLM_FIRST_DELAY_MIN must not exceed LLM_FIRST_DELAY_MAX")
        if self.llm_part_delay_min > self.llm_part_delay_max:
            raise ValueError("LLM_PART_DELAY_MIN must not exceed LLM_PART_DELAY_MAX")
        return self
