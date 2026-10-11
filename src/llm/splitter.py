"""Splitting long replies into several QQ messages."""

import re

# Split points, from the most to the least natural, each with the text that joins
# its pieces back together. Sentence splits are zero-width and leave the following
# space on the next piece, so joining them restores the text exactly.
_SPLITS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\n\s*\n"), "\n\n"),
    (re.compile(r"\n"), "\n"),
    (re.compile(r"(?<=[。！？；…])|(?<=[.!?;,，、])(?=\s)"), ""),
)
TRUNCATED_NOTE = "（回复太长，后面的内容省略了）"


def split_reply(text: str, max_chars: int, max_parts: int) -> list[str]:
    """Split `text` into at most `max_parts` messages of up to `max_chars`.

    Prefers paragraph, then line, then sentence boundaries, and only cuts inside a
    sentence when one is longer than `max_chars`. Neighbouring pieces are joined
    again while they fit. Text beyond `max_parts` is dropped and the last part says so.
    """
    text = text.strip()
    if not text:
        return []
    parts = _merge(_pieces(text, max_chars, ""), max_chars)
    if len(parts) > max_parts:
        parts = parts[:max_parts]
        parts[-1] = f"{parts[-1]}\n{TRUNCATED_NOTE}"
    return parts


def _pieces(text: str, max_chars: int, joiner: str) -> list[tuple[str, str]]:
    """Break `text` into (joiner, piece) pairs, each piece at most `max_chars` long.

    A piece's joiner is what separated it from the previous piece.
    """
    if len(text) <= max_chars:
        return [(joiner, text)]
    for pattern, sep in _SPLITS:
        chunks = [c if not sep else c.strip() for c in pattern.split(text) if c.strip()]
        if len(chunks) > 1:
            result: list[tuple[str, str]] = []
            for i, chunk in enumerate(chunks):
                result.extend(_pieces(chunk, max_chars, joiner if i == 0 else sep))
            return result
    cuts = [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    return [(joiner if i == 0 else "", cut) for i, cut in enumerate(cuts)]


def _merge(pieces: list[tuple[str, str]], max_chars: int) -> list[str]:
    """Join neighbouring pieces with their joiners while they fit in `max_chars`."""
    merged: list[str] = []
    for joiner, piece in pieces:
        if merged and len(merged[-1]) + len(joiner) + len(piece) <= max_chars:
            merged[-1] = f"{merged[-1]}{joiner}{piece}"
        else:
            merged.append(piece)
    return [m.strip() for m in merged]
