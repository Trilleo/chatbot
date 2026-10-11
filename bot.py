"""NoneBot entrypoint.

python bot.py              apply database migrations, then run the bot
python bot.py orm <cmd>    database migrations: nonebot-plugin-orm's `nb orm`
                           commands, e.g. `orm revision -m "..."` (README.md)
"""

import subprocess
import sys
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter


def setup() -> None:
    """Initialise NoneBot, register the adapter and load every plugin."""
    nonebot.init()
    config = nonebot.get_driver().config
    # Without a token anyone who can reach the port could act as the QQ account.
    if not getattr(config, "onebot_access_token", None):
        sys.exit("ONEBOT_ACCESS_TOKEN must be set (see .env.example).")
    nonebot.get_driver().register_adapter(OneBotV11Adapter)
    nonebot.load_from_toml("pyproject.toml")
    # NoneBot logs a plugin that fails to import and carries on; a bot missing a
    # feature shouldn't pass a health check, so stop instead.
    local = {p.parent.name for p in Path("src/plugins").glob("*/__init__.py")}
    missing = local - {plugin.name for plugin in nonebot.get_loaded_plugins()}
    if missing:
        sys.exit(f"Plugins failed to load: {', '.join(sorted(missing))} (see above).")


def main() -> None:
    if sys.argv[1:2] == ["orm"]:
        setup()
        from nonebot_plugin_orm.__main__ import main as orm_main

        orm_main(args=sys.argv[2:], prog_name="bot.py orm")
        return
    # The ORM's startup check asks on stdin before migrating, which a container can't
    # answer, so migrations are applied first, in their own process (its database
    # engine and event loop are gone before the bot's start).
    upgrade = subprocess.run([sys.executable, __file__, "orm", "upgrade"], check=False)
    if upgrade.returncode != 0:
        sys.exit(upgrade.returncode)
    setup()
    nonebot.run()


if __name__ == "__main__":
    main()
