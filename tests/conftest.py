import tempfile
from pathlib import Path

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebug import NONEBOT_INIT_KWARGS

SUPERUSER_ID = 10001
ACCESS_TOKEN = "test-token"


def pytest_configure(config: pytest.Config) -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="chatbot-tests-"))
    config.stash[NONEBOT_INIT_KWARGS] = {
        # .env.example, not the developer's .env: tests see the shipped defaults.
        "_env_file": (".env.example",),
        "onebot_access_token": ACCESS_TOKEN,
        "superusers": {str(SUPERUSER_ID)},
        "localstore_data_dir": data_dir / "data",
        "localstore_config_dir": data_dir / "config",
        "localstore_cache_dir": data_dir / "cache",
        # Create tables straight from the models: the startup check would ask on stdin
        # before migrating. CI checks the migrations themselves (bot.py orm check).
        "alembic_startup_check": False,
    }


@pytest.fixture(scope="session", autouse=True)
async def after_nonebot_init(after_nonebot_init: None) -> None:
    nonebot.get_driver().register_adapter(OneBotV11Adapter)
    nonebot.load_from_toml("pyproject.toml")
