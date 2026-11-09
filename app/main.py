"""Точка входа HTTP API. Запуск: make dev (uvicorn app.main:app)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.core.db import close_pool, init_pool
from app.core.logging import request_id_var, setup_logging
from app.routers import cards, documents, generate, health, jobs, workflows


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_pool()  # пул создаётся один раз на старте приложения
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="ИИ-генератор карточки товара", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # request_id рождается на входе в приложение и попадает во все логи запроса.
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


app.include_router(health.router)
app.include_router(cards.router)
app.include_router(documents.router)
app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(workflows.router)
