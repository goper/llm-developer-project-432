"""Ветка поиска сквозного сценария: поиск -> защита -> контекст.

Порядок важен: маскирование персональных данных раньше любого вызова модели,
детектор инъекций раньше сборки контекста, сборка контекста — единственное место,
где фрагменты попадают в промпт.
"""

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import Any

from app.agents.roles import critic_agent, generate_agent
from app.core.config import get_settings
from app.guardrails import guard_context, guard_output
from app.guardrails.injection import InjectionDetector
from app.guardrails.pii import mask_pii
from app.llm.client import run_agent
from app.rag import retrieval
from app.rag.context import Context, build_context, context_chunk_ids
from app.repositories import chunks as chunks_repo
from app.repositories.chunks import ChunkHit
from app.schemas.cards import Card, CritiqueReport
from app.services import structured
from app.services.json_utils import parse_json_reply
from app.services.structured import ChatLike

logger = logging.getLogger(__name__)


class DocumentRejectedError(Exception):
    """Слишком много подозрительных фрагментов: документ уходит человеку с причиной."""


def default_query(product_hint: str | None, document_names: list[str]) -> str:
    """Запрос для поиска: подсказка товара, иначе имя первого документа без расширения."""
    if product_hint and product_hint.strip():
        return product_hint.strip()
    if document_names:
        return document_names[0].rsplit(".", 1)[0].replace("_", " ")
    return "товар"


def search_step(
    query: str,
    document_ids: list[str] | None,
    *,
    top_k: int | None = None,
) -> list[ChunkHit]:
    """Гибридный поиск по выбранным документам."""
    return retrieval.search(query, mode="hybrid", document_ids=document_ids, top_k=top_k)


def assemble_context(hits: list[ChunkHit], llm: ChatLike, *, job_id: str | None) -> Context:
    """Маскирование -> проверка инъекций -> сборка контекста с отчётом о том, что исключено."""
    settings = get_settings()
    masked_hits = [replace(h, text=mask_pii(h.text).text) for h in hits]

    detector = InjectionDetector(llm)
    verdicts = detector.screen([(h.id, h.text) for h in masked_hits])
    suspicious = {v.fragment_id for v in verdicts if v.suspicious}
    excluded: list[dict[str, Any]] = [
        {"chunk_id": v.fragment_id, "via": v.via, "rules": list(v.rule_hits)}
        for v in verdicts
        if v.suspicious
    ]
    if len(suspicious) > settings.injection_suspicious_limit:
        raise DocumentRejectedError(
            f"подозрительных фрагментов {len(suspicious)}, это больше порога "
            f"{settings.injection_suspicious_limit}: документ передан человеку"
        )
    clean = [h for h in masked_hits if h.id not in suspicious]
    context = build_context(clean, max_chars=settings.context_max_chars)
    context.report["excluded_as_suspicious"] = excluded
    logger.info("контекст собран: фрагментов=%d исключено=%d", len(context.items), len(excluded))
    return context


def text_context(text: str, *, chunk_id: str = "text-1") -> Context:
    """Контекст из одного текста (синхронный обработчик POST /cards). Маскирование то же."""
    settings = get_settings()
    hit = ChunkHit(
        id=chunk_id, document_id="", text=text, page=None, section=None, sku=None, brand=None, score=1.0
    )
    hit = replace(hit, text=mask_pii(text).text)
    return build_context([hit], max_chars=settings.context_max_chars)


# --- Асинхронный сквозной путь: документы -> защита -> контекст -> генерация -> проверка -> порог. ---


@dataclass
class RagResult:
    """Итог по документам. Распаковывается как `card, attempts, verdict, status`."""

    card: Card | None
    attempts: int
    verdict: str  # approved | rejected
    status: str  # done | needs_review | rejected
    output_issues: list[str] = field(default_factory=list)
    context_ids: set[str] = field(default_factory=set)

    def __iter__(self):
        yield from (self.card, self.attempts, self.verdict, self.status)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def source_problems(card: Card, allowed: set[str]) -> list[str]:
    """Ссылки карточки — только на фрагменты, которые были в контексте. Иначе это выдумывание."""
    cited = {s.chunk_id for s in card.sources} | set(card.characteristic_sources.values())
    bad = sorted(cited - allowed)
    if bad:
        return [f"ссылка на фрагмент, которого не было в контексте: {', '.join(bad)}"]
    if card.characteristics and not card.sources and not card.characteristic_sources:
        return ["у характеристик нет ссылок на фрагменты (sources)"]
    return []


def _as_chunk(hit: ChunkHit) -> dict[str, Any]:
    return {"chunk_id": hit.id, "text": hit.text, "metadata": hit.metadata(), "filename": hit.filename}


async def retrieve_context_async(query: str | None, doc_ids: list[str] | str | None = None) -> Context:
    """Поиск -> маскирование ПДн -> детектор инъекций -> контекст с шапками фрагментов.

    Без query берутся все фрагменты документов по порядку, с query — гибридный поиск по ним.
    Подозрительных фрагментов больше порога — DocumentRejectedError: документ уходит человеку.
    """
    ids = [doc_ids] if isinstance(doc_ids, str) else (list(doc_ids) if doc_ids else None)
    if query:
        hits = await asyncio.to_thread(search_step, query, ids)
    elif ids:
        hits = await asyncio.to_thread(chunks_repo.list_for_documents, ids)
    else:
        raise ValueError("нужен запрос или список документов")

    safe, guard = await guard_context([_as_chunk(h) for h in hits])
    if guard.needs_review:
        raise DocumentRejectedError(
            f"подозрительных фрагментов {len(guard.suspicious_chunks)}, это больше порога "
            f"{get_settings().injection_suspicious_limit}: документ передан человеку"
        )
    context = build_context(safe)
    context.report["guard"] = guard.to_dict()
    return context


async def run_rag_pipeline(
    query: str | None = None,
    doc_ids: list[str] | str | None = None,
    *,
    max_attempts: int | None = None,
) -> RagResult:
    """Карточка по документам поставщика: контекст -> генерация -> проверка -> порог уверенности.

    Ссылка на фрагмент вне контекста — ошибка генерации: ответ уходит модели на исправление,
    после всех попыток — CardValidationError. Низкая уверенность или находка фильтра выхода — needs_review.
    """
    context = await retrieve_context_async(query, doc_ids)
    allowed = context_chunk_ids(context)
    prompt = f"ФРАГМЕНТЫ:\n{context}"
    if query:
        prompt = f"Товар: {query}\n\n{prompt}"

    attempts = max_attempts or get_settings().max_repair_rounds
    issues: list[str] = []
    used = 0
    for attempt in range(1, attempts + 1):
        used = attempt
        full = prompt + ("\n\nЗАМЕЧАНИЯ ПРОВЕРКИ:\n" + "\n".join(f"- {i}" for i in issues) if issues else "")
        card = await structured.validate_or_retry(
            full,
            generate_agent(),
            Card,
            check=lambda c: source_problems(c, allowed),
            runner=run_agent,
        )
        raw = await run_agent(critic_agent(), f"ЧЕРНОВИК:\n{card.model_dump_json()}\n\n{prompt}")
        report = CritiqueReport.model_validate(parse_json_reply(raw))
        if report.verdict == "approve":
            break
        issues = list(report.issues)
    else:
        return RagResult(card, attempts, "rejected", "rejected", context_ids=allowed)

    card, output_issues = guard_output(card)
    status = structured.confidence_gate(card)
    if output_issues:
        status = "needs_review"
    return RagResult(card, used, "approved", status, output_issues=output_issues, context_ids=allowed)
