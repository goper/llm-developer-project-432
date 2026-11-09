"""Сигналы и запросы к процессу: подтверждение, отказ, текущее состояние ручной проверки."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from temporalio.service import RPCError, RPCStatusCode

from app.temporal.client import card_workflow_id, get_client
from app.temporal.workflows import GenerateCardWorkflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def _with_process[T](job_id: str, action: Callable[[Any], Awaitable[T]]) -> T:
    """Выполняет действие над процессом; отсутствие процесса превращаем в 404."""
    client = await get_client()
    handle = client.get_workflow_handle_for(GenerateCardWorkflow, card_workflow_id(job_id))
    try:
        return await action(handle)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="процесс не найден") from exc
        raise


@router.post("/{job_id}/approve", status_code=202)
async def approve(job_id: str) -> dict[str, str]:
    await _with_process(job_id, lambda h: h.signal(GenerateCardWorkflow.approve))
    return {"job_id": job_id, "signal": "approve"}


@router.post("/{job_id}/reject", status_code=202)
async def reject(job_id: str) -> dict[str, str]:
    await _with_process(job_id, lambda h: h.signal(GenerateCardWorkflow.reject))
    return {"job_id": job_id, "signal": "reject"}


@router.get("/{job_id}/state")
async def state(job_id: str) -> dict[str, Any]:
    return await _with_process(job_id, lambda h: h.query(GenerateCardWorkflow.state))
