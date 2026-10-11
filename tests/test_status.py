import httpx
import nonebot
from nonebug import App


async def test_health_reports_ok_and_version(app: App) -> None:
    # A plain ASGI client: nonebug's test server would start NoneBot's lifespan twice.
    transport = httpx.ASGITransport(app=nonebot.get_asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://bot") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "dev"}
