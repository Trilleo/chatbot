"""Personas: system prompts in <name>.md files (src/plugins/llm_chat/personas/),
chosen per session.

A file's first line may be `> description`, shown by /persona; the rest is the prompt.
Every prompt gets QQ_STYLE appended, so replies suit QQ whatever the persona.
"""

from dataclasses import dataclass
from pathlib import Path

QQ_STYLE = (
    "回复规则：这是 QQ 聊天，消息按纯文本显示。"
    "不要使用 Markdown（不要用 #、**、表格、代码块标记），"
    "需要分点时用简单的数字或换行。"
    "回答尽量简短，除非用户要求详细说明。用用户使用的语言回复。"
)


@dataclass(frozen=True, slots=True)
class Persona:
    name: str
    description: str
    prompt: str

    @property
    def system_prompt(self) -> str:
        """The persona's prompt with the QQ reply rules."""
        return f"{self.prompt}\n\n{QQ_STYLE}"


def parse_persona(name: str, text: str) -> Persona:
    """Read a persona file's text."""
    lines = text.strip().splitlines()
    description = ""
    if lines and lines[0].startswith(">"):
        description = lines.pop(0).lstrip("> ").strip()
    return Persona(name=name, description=description, prompt="\n".join(lines).strip())


def load_personas(directory: Path) -> dict[str, Persona]:
    """Every persona in `directory`, by name (the file name without .md)."""
    return {
        path.stem: parse_persona(path.stem, path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.md"))
    }
