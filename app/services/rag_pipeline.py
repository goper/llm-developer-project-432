"""Ветка поиска сквозного сценария: поиск -> защита -> контекст.

Порядок важен: маскирование персональных данных раньше любого вызова модели,
детектор инъекций раньше сборки контекста, сборка контекста — единственное место,
где фрагменты попадают в промпт.
"""

import logging
from dataclasses import replace
from typing import Any

from app.core.config import get_settings
from app.guardrails.injection import InjectionDetector
from app.guardrails.pii import mask_pii
from app.rag import retrieval
from app.rag.context import Context, build_context
from app.repositories.chunks import ChunkHit
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
