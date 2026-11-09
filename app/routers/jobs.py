"""Чтение статуса задачи: состояние из базы, а не из истории движка."""

import asyncio

from fastapi import APIRouter, HTTPException

from app.repositories import jobs as jobs_repo
from app.repositories.llm_calls import cost_by_job
from app.schemas.jobs import JobView

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobView)
async def get_job(job_id: str) -> JobView:
    job = await asyncio.to_thread(jobs_repo.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="задача не найдена")
    cost = await asyncio.to_thread(cost_by_job, job_id)
    return JobView(
        job_id=job.id,
        kind=job.kind,
        status=job.status,
        document_ids=job.document_ids,
        result=job.result,
        error=job.error,
        cost=cost,
    )
