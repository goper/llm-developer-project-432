"""Сборка контекста генерации из найденных фрагментов.

Каждый фрагмент опознаваем (chunk_id в тексте), контекст ограничен по размеру,
повторы убраны. Персональные данные маскируются здесь, до промпта и до лога.
"""

from dataclasses import dataclass, field

from app.agents.prompts import render_fragments
from app.guardrails.pii import mask_pii
from app.repositories.chunks import ChunkHit


@dataclass(frozen=True)
class ContextItem:
    chunk_id: str
    text: str
    page: int | None
    section: str | None
    document_id: str | None = None


@dataclass
class Context:
    items: list[ContextItem] = field(default_factory=list)
    report: dict[str, object] = field(default_factory=dict)

    @property
    def allowed_ids(self) -> frozenset[str]:
        return frozenset(i.chunk_id for i in self.items)

    def render(self) -> str:
        return render_fragments(
            [
                {"chunk_id": i.chunk_id, "text": i.text, "page": i.page, "section": i.section}
                for i in self.items
            ]
        )

    def total_chars(self) -> int:
        return sum(len(i.text) for i in self.items)


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def build_context(hits: list[ChunkHit], *, max_chars: int) -> Context:
    """Собирает контекст: маскирует, убирает повторы, держит предел размера."""
    seen: set[str] = set()
    items: list[ContextItem] = []
    masked_kinds: dict[str, int] = {}
    duplicates = 0
    skipped_by_limit = 0
    used = 0
    for hit in hits:
        masked = mask_pii(hit.text)
        for finding in masked.findings:
            masked_kinds[finding.kind] = masked_kinds.get(finding.kind, 0) + 1
        key = _norm(masked.text)
        if key in seen:
            duplicates += 1
            continue
        if used + len(masked.text) > max_chars:
            skipped_by_limit += 1
            continue
        seen.add(key)
        used += len(masked.text)
        items.append(
            ContextItem(
                chunk_id=hit.id,
                text=masked.text,
                page=hit.page,
                section=hit.section,
                document_id=hit.document_id,
            )
        )
    report = {
        "fragments": len(items),
        "duplicates_removed": duplicates,
        "skipped_by_limit": skipped_by_limit,
        "masked": masked_kinds,
    }
    return Context(items=items, report=report)
