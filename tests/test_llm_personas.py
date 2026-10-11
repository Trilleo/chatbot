from pathlib import Path

from src.llm.personas import QQ_STYLE, load_personas, parse_persona

PERSONA_DIR = Path(__file__).parent.parent / "src" / "plugins" / "llm_chat" / "personas"


def test_parses_description_and_prompt() -> None:
    persona = parse_persona("x", "> 简介\n\n提示词第一行\n第二行\n")
    assert persona.description == "简介"
    assert persona.prompt == "提示词第一行\n第二行"
    assert persona.system_prompt.endswith(QQ_STYLE)


def test_description_is_optional() -> None:
    persona = parse_persona("x", "只有提示词")
    assert persona.description == ""
    assert persona.prompt == "只有提示词"


def test_shipped_personas_are_complete() -> None:
    personas = load_personas(PERSONA_DIR)
    assert "default" in personas
    for persona in personas.values():
        assert persona.description, persona.name
        assert persona.prompt, persona.name
