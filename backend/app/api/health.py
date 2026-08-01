from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def read_health() -> dict[str, str]:
    return {"status": "ok"}
