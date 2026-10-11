"""What users see when something goes wrong (details go to the server log)."""

from .provider import (
    ProviderConfigError,
    ProviderEmptyResponseError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

ERROR_REPLIES: dict[type[ProviderError], str] = {
    ProviderTimeoutError: "想得太久了，稍后再试试吧。",
    ProviderRateLimitError: "现在问的人有点多，请过一会儿再试。",
    ProviderConfigError: "机器人这边的配置出了点问题，请联系管理员。",
    ProviderEmptyResponseError: "这个问题我没想好怎么回答，换个说法试试？",
}
DEFAULT_ERROR_REPLY = "暂时没法回复，请稍后再试。"

NOT_TEXT_REPLY = "目前只能看懂文字消息哦。"
TOO_LONG_REPLY = "消息太长了，能精简一点再发吗？"


def error_reply(error: ProviderError) -> str:
    """The short message for users about `error`."""
    for kind, reply in ERROR_REPLIES.items():
        if isinstance(error, kind):
            return reply
    return DEFAULT_ERROR_REPLY
