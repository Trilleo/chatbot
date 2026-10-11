"""HTTP health endpoint for Docker's healthcheck and the deploy script.

Served by the FastAPI driver on the bot's port, which is only reachable inside the
Docker network.
"""

from fastapi import FastAPI
from nonebot import get_app, get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="status",
    description="GET /health for container health checks.",
    usage="GET /health",
    config=Config,
)

config = get_plugin_config(Config)
app: FastAPI = get_app()


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up and serving HTTP."""
    return {"status": "ok", "version": config.status_version}
