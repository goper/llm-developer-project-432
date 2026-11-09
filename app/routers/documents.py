"""Загрузка документов: 202 и идентификатор, разбор идёт в процессе Temporal."""

import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.core.config import get_settings
from app.repositories import documents as documents_repo
from app.schemas.jobs import DocumentCreated, DocumentView
from app.services import documents as documents_service
from app.temporal.client import document_workflow_id, get_client
from app.temporal.workflows import ParseDocumentWorkflow

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", status_code=202, response_model=DocumentCreated)
async def upload(file: Annotated[UploadFile, File()]) -> JSONResponse:
    content = await file.read(get_settings().max_upload_bytes + 1)
    try:
        result = await asyncio.to_thread(documents_service.save_upload, file.filename or "document", content)
    except documents_service.UploadError as exc:
        status = 413 if "МБ" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    doc = result.document
    # Новый файл или документ, который разбор не довёл до конца (застрял в new/parsing/indexing),
    # запускаем разбор заново.
    if result.created or doc.status in ("new", "parsing", "indexing"):
        client = await get_client()
        with contextlib.suppress(WorkflowAlreadyStartedError):  # разбор уже идёт
            await client.start_workflow(
                ParseDocumentWorkflow.run,
                doc.id,
                id=document_workflow_id(doc.id),
                task_queue=get_settings().temporal_task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
            )

    body = DocumentCreated(document_id=doc.id, status=doc.status)
    return JSONResponse(body.model_dump(), status_code=202)


@router.get("/{document_id}", response_model=DocumentView)
def get_document(document_id: str) -> DocumentView:
    doc = documents_repo.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="документ не найден")
    return DocumentView(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        error=doc.error,
        chunks_count=doc.chunks_count,
    )
