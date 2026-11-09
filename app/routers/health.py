"""Проверки состояния. Живость — про процесс; готовность — про зависимости (база и расширение vector)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.db import connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    # Не трогает базу: процесс жив, даже если база остановлена.
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
    except Exception as exc:  # база недоступна или расширение не включено
        return JSONResponse({"status": "unavailable", "reason": type(exc).__name__}, status_code=503)
    if row is None:
        return JSONResponse(
            {"status": "unavailable", "reason": "расширение vector не включено"}, status_code=503
        )
    return JSONResponse({"status": "ok", "vector": row[0]})
