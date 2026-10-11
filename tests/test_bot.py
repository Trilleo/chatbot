import os
import subprocess
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parent.parent / "bot.py"


def test_refuses_to_start_without_access_token(tmp_path: Path) -> None:
    # An empty directory has no .env, so (with the variable unset) no token.
    env = {k: v for k, v in os.environ.items() if k.upper() != "ONEBOT_ACCESS_TOKEN"}
    result = subprocess.run(
        [sys.executable, str(BOT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 1
    assert "ONEBOT_ACCESS_TOKEN must be set" in result.stderr
