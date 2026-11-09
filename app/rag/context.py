"""Сборка контекста генерации из найденных фрагментов.

Каждый фрагмент опознаваем (chunk_id в тексте), контекст ограничен по размеру,
повторы убраны. Персональные данные маскируются здесь, до промпта и до лога.
"""

from dataclasses import dataclass
from typing import Any

from app.agents.prompts import render_fragments
from app.core.config import get_settings
from app.guardrails.pii import mask_pii


@dataclass(frozen=True)
class ContextItem:
    chunk_id: str
    text: str
    page: int | None
    section: str | None
    document_id: str | None = None
    filename: str | None = None


class Context(str):
    """Контекст генерации. Это готовый текст для промпта (str) и при этом объект:
    items — поданные фрагменты, report — что убрано и замаскировано.
    """

    items: list[ContextItem]
    report: dict[str, object]

    def __new__(cls, items: list[ContextItem] | None = None, report: dict[str, object] | None = None):
        items = list(items or [])
        obj = super().__new__(cls, _render(items))
        obj.items = items
        obj.report = dict(report or {})
        return obj

    @property
    def allowed_ids(self) -> frozenset[str]:
        return frozenset(i.chunk_id for i in self.items)

    def render(self) -> str:
        return str(self)

    def total_chars(self) -> int:
        return sum(len(i.text) for i in self.items)


def _render(items: list[ContextItem]) -> str:
    return render_fragments(
        [
            {
                "chunk_id": i.chunk_id,
                "text": i.text,
                "page": i.page,
                "section": i.section,
                "filename": i.filename,
            }
            for i in items
        ]
    )


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _field(hit: Any, name: str) -> Any:
    """Поле фрагмента: из атрибута, ключа словаря или его metadata."""
    if isinstance(hit, dict):
        if name in hit:
            return hit[name]
        return (hit.get("metadata") or {}).get(name)
    return getattr(hit, name, None)


def build_context(hits: list[Any], *, max_chars: int | None = None) -> Context:
    """Собирает контекст: маскирует, убирает повторы, держит предел размера.

    hits — результаты поиска (ChunkHit) или словари {"chunk_id", "text", "metadata", "filename"}.
    Каждый фрагмент идёт с заголовком [chunk_id=..., файл, стр., раздел], чтобы модель могла сослаться.
    """
    limit = get_settings().context_max_chars if max_chars is None else max_chars
    seen: set[str] = set()
    items: list[ContextItem] = []
    masked_kinds: dict[str, int] = {}
    duplicates = 0
    skipped_by_limit = 0
    used = 0
    for hit in hits:
        masked = mask_pii(str(_field(hit, "text") or ""))
        for finding in masked.findings:
            masked_kinds[finding.kind] = masked_kinds.get(finding.kind, 0) + 1
        key = _norm(masked.text)
        if key in seen:
            duplicates += 1
            continue
        if used + len(masked.text) > limit:
            skipped_by_limit += 1
            continue
        seen.add(key)
        used += len(masked.text)
        items.append(
            ContextItem(
                chunk_id=str(_field(hit, "chunk_id") or _field(hit, "id")),
                text=masked.text,
                page=_field(hit, "page"),
                section=_field(hit, "section"),
                document_id=_field(hit, "doc_id") or _field(hit, "document_id"),
                filename=_field(hit, "filename"),
            )
        )
    report = {
        "fragments": len(items),
        "duplicates_removed": duplicates,
        "skipped_by_limit": skipped_by_limit,
        "masked": masked_kinds,
    }
    return Context(items=items, report=report)


def context_chunk_ids(context: "Context | str") -> set[str]:
    """Идентификаторы фрагментов, поданных в контекст. Принимает Context или его текст."""
    if isinstance(context, Context):
        return set(context.allowed_ids)
    import re

    return set(re.findall(r"chunk_id=([^,\]\s]+)", context))
