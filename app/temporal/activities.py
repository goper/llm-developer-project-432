"""Шаги процесса генерации и разбора документа.

Каждая активность — один шаг: её повтор делает движок, вызов модели внутри повторяет клиент.
Записи статуса в базу — отдельные короткие активности, а не действия внутри пайплайна.
"""

import logging
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.core.config import get_settings
from app.core.logging import bind_job
from app.llm.client import LLMClient
from app.rag.context import Context, ContextItem
from app.repositories import jobs as jobs_repo
from app.repositories import llm_calls as calls_repo
from app.repositories.chunks import ChunkHit
from app.schemas.cards import Card, Facts, Issue, Verdict
from app.services import documents as documents_service
from app.services import pipeline, rag_pipeline
from app.services.rag_pipeline import DocumentRejectedError
from app.services.structured import repair_fields
from app.temporal.payloads import (
    AssembleInput,
    CheckInput,
    DecisionInput,
    ExtractInput,
    FinishInput,
    GenerateCardInput,
    RepairInput,
    SearchInput,
    SetStatusInput,
)

logger = logging.getLogger(__name__)


@lru_cache
def llm() -> LLMClient:
    return LLMClient()


def _context_from(data: dict[str, Any]) -> Context:
    items = [ContextItem(**i) for i in data["items"]]
    return Context(items=items, report=data.get("report", {}))


def _context_to(ctx: Context) -> dict[str, Any]:
    return {"items": [asdict(i) for i in ctx.items], "report": ctx.report}


@activity.defn
def parse_document_activity(document_id: str) -> str:
    with bind_job(document_id):
        return documents_service.parse_document(document_id)


@activity.defn
def set_job_status_activity(data: SetStatusInput) -> None:
    with bind_job(data.job_id):
        jobs_repo.set_status(data.job_id, data.status, data.error)


@activity.defn
def search_activity(data: SearchInput) -> list[dict[str, Any]]:
    with bind_job(data.job_id):
        hits = rag_pipeline.search_step(data.query, data.document_ids or None)
        return [
            {
                "id": h.id,
                "document_id": h.document_id,
                "text": h.text,
                "page": h.page,
                "section": h.section,
                "sku": h.sku,
                "brand": h.brand,
                "score": h.score,
            }
            for h in hits
        ]


@activity.defn
def assemble_activity(data: AssembleInput) -> dict[str, Any]:
    with bind_job(data.job_id):
        hits = [ChunkHit(**h) for h in data.hits]
        try:
            ctx = rag_pipeline.assemble_context(hits, llm(), job_id=data.job_id)
        except DocumentRejectedError as exc:
            raise ApplicationError(str(exc), type="DocumentRejectedError", non_retryable=True) from exc
        return _context_to(ctx)


@activity.defn
def extract_activity(data: ExtractInput) -> dict[str, Any]:
    with bind_job(data.job_id):
        facts = pipeline.extract_facts(
            llm(), _context_from(data.context), data.product_hint, job_id=data.job_id
        )
        return facts.model_dump()


@activity.defn
def generate_activity(data: GenerateCardInput) -> dict[str, Any]:
    with bind_job(data.job_id):
        card = pipeline.generate_card(
            llm(),
            _context_from(data.context),
            Facts.model_validate(data.facts),
            data.product_hint,
            job_id=data.job_id,
            feedback=data.feedback,
        )
        return card.model_dump()


@activity.defn
def check_activity(data: CheckInput) -> list[dict[str, str]]:
    """Возвращает проблемы: ссылки, проверенные кодом, и замечания проверяющей роли."""
    with bind_job(data.job_id):
        ctx = _context_from(data.context)
        card = Card.model_validate(data.card)
        problems: list[Issue] = pipeline.link_problems(card, ctx)
        verdict: Verdict = pipeline.check_card(llm(), ctx, card, job_id=data.job_id)
        if not verdict.ok:
            problems += verdict.issues
        return [p.model_dump() for p in problems]


@activity.defn
def repair_activity(data: RepairInput) -> dict[str, Any]:
    with bind_job(data.job_id):
        ctx = _context_from(data.context)
        draft = repair_fields(
            llm(), data.card, data.problems, Card, job_id=data.job_id, fragments_text=ctx.render()
        )
        return Card.model_validate(draft).model_dump()


@activity.defn
def finish_activity(data: FinishInput) -> str:
    """Решает статус по уверенности и проблемам, сохраняет результат. Порог читает этот шаг, не сценарий."""
    with bind_job(data.job_id):
        card = Card.model_validate(data.card)
        problems = [Issue.model_validate(p) for p in data.problems]
        status = pipeline.decide_status(card, problems, get_settings().confidence_threshold)
        result = {
            "card": card.model_dump(),
            "rounds": data.rounds,
            "problems": data.problems,
            "protection": data.context_report,
            "cost": calls_repo.cost_by_job(data.job_id),
        }
        jobs_repo.save_result(data.job_id, result, status)
        return status


@activity.defn
def decision_activity(data: DecisionInput) -> None:
    with bind_job(data.job_id):
        jobs_repo.set_status(data.job_id, data.decision)


ACTIVITIES = [
    parse_document_activity,
    set_job_status_activity,
    search_activity,
    assemble_activity,
    extract_activity,
    generate_activity,
    check_activity,
    repair_activity,
    finish_activity,
    decision_activity,
]

NON_RETRYABLE = ["DocumentRejectedError", "StructuredError", "LLMRequestError"]
