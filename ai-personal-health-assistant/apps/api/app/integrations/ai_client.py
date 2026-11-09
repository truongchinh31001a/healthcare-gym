import httpx
from app.core.config import settings
async def get_ai_service_health() -> dict:
    async with httpx.AsyncClient(base_url=settings.ai_service_url, timeout=10) as client:
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()
