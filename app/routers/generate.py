"""Асинхронная генерация: создаём задачу, отвечаем 202 и идентификатором, процесс идёт в Temporal.

Ключ идемпотентности (заголовок Idempotency-Key): повтор с тем же ключом возвращает первую задачу.
"""

import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import bind_job
from app.repositories import documents as documents_repo
from app.repositories import jobs as jobs_repo
from app.schemas.jobs import GenerateRequest, JobCreated
from app.services.rag_pipeline import default_query
from app.temporal.client import card_workflow_id, get_client
from app.temporal.payloads import GenerateInput
from app.temporal.workflows import GenerateCardWorkflow

router = APIRouter(tags=["generate"])
logger = logging.getLogger(__name__)


@router.post("/generate-card", status_code=202, response_model=JobCreated)
async def generate_card(
    body: GenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    docs = await asyncio.to_thread(documents_repo.get_many, body.document_ids)
    if len(docs) != len(set(body.document_ids)):
        raise HTTPException(status_code=404, detail="часть документов не найдена")
    not_ready = [d.id for d in docs if d.status != "indexed"]
    if not_ready:
        raise HTTPException(
            status_code=409, detail=f"документы ещё не проиндексированы: {', '.join(not_ready)}"
        )

    job, created = await asyncio.to_thread(
        jobs_repo.create_job,
        kind="generate_card",
        document_ids=body.document_ids,
        product_hint=body.product_hint,
        idempotency_key=idempotency_key,
    )
    if created:
        with bind_job(job.id):
            logger.info("задача создана: документы=%s", ",".join(body.document_ids))
            query = default_query(body.product_hint, [d.filename for d in docs])
            client = await get_client()
            await client.start_workflow(
                GenerateCardWorkflow.run,
                GenerateInput(
                    job_id=job.id,
                    document_ids=body.document_ids,
                    product_hint=query,
                    max_repair_rounds=get_settings().max_repair_rounds,
                ),
                id=card_workflow_id(job.id),
                task_queue=get_settings().temporal_task_queue,
            )
    return JSONResponse(JobCreated(job_id=job.id, status=job.status).model_dump(), status_code=202)
