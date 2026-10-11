from typing import Any

import pytest
from pydantic import ValidationError


@pytest.fixture
def config_class() -> Any:
    # Imported late: importing the plugin package needs NoneBot initialised.
    from src.plugins.llm_chat.config import Config

    return Config


def test_defaults_are_valid(config_class: Any) -> None:
    config = config_class()
    assert config.llm_model == "deepseek-flash"
    assert config.llm_temperature is None


def test_empty_temperature_means_default(config_class: Any) -> None:
    assert config_class(llm_temperature="").llm_temperature is None
    assert config_class(llm_temperature="0.7").llm_temperature == 0.7


def test_delay_ranges_must_be_ordered(config_class: Any) -> None:
    with pytest.raises(ValidationError):
        config_class(llm_first_delay_min=3, llm_first_delay_max=1)
    with pytest.raises(ValidationError):
        config_class(llm_part_delay_min=3, llm_part_delay_max=1)
