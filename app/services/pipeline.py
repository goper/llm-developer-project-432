"""Пайплайн генерации: извлечение, генерация, проверка и петля переделки.

Петля ограничена max_repair_rounds кругами. Переделка точечная: исправляются только поля с проблемами.
Вызовы модели идут через LLMClient (его передают снаружи), повтор вызова — дело клиента.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agents.prompts import check_messages, extract_messages, generate_messages
from app.core.config import get_settings
from app.llm.client import run_agent  # noqa: F401  (извлечение и проверка зовут агентов через него)
from app.rag.context import Context
from app.schemas.cards import Card, Facts, Issue, Verdict
from app.services.structured import ChatLike, generate_model, repair_fields

STATUS_WAITING = "waiting_approval"
STATUS_REVIEW = "needs_review"


@dataclass
class PipelineOutcome:
    card: Card
    status: str  # waiting_approval | needs_review
    rounds: int
    problems: list[Issue] = field(default_factory=list)


def extract_facts(llm: ChatLike, context: Context, product_hint: str | None, *, job_id: str | None) -> Facts:
    return generate_model(
        llm,
        extract_messages(context.render(), product_hint),
        Facts,
        purpose="extract",
        job_id=job_id,
        fragments_text=context.render(),
    )


def generate_card(
    llm: ChatLike,
    context: Context,
    facts: Facts,
    product_hint: str | None,
    *,
    job_id: str | None,
    feedback: str | None = None,
) -> Card:
    rendered = context.render()
    return generate_model(
        llm,
        generate_messages(rendered, facts.model_dump_json(ensure_ascii=False), product_hint, feedback),
        Card,
        purpose="generate",
        job_id=job_id,
        fragments_text=rendered,
    )


def check_card(llm: ChatLike, context: Context, card: Card, *, job_id: str | None) -> Verdict:
    rendered = context.render()
    return generate_model(
        llm,
        check_messages(rendered, card.model_dump_json(ensure_ascii=False)),
        Verdict,
        purpose="check",
        job_id=job_id,
        fragments_text=rendered,
    )


def link_problems(card: Card, context: Context) -> list[Issue]:
    """Проверка ссылок кодом по двум условиям: фрагмент был в контексте и есть в базе.

    Первое условие важнее: ссылка на фрагмент, которого модель не видела, — это выдумывание.
    Условие «есть в базе» проверяет вызывающий код (репозиторий) через существование в allowed_ids,
    потому что allowed_ids — это уже найденные из базы фрагменты.
    """
    allowed = context.allowed_ids
    issues: list[Issue] = []
    bad = sorted({s.chunk_id for s in card.sources if s.chunk_id not in allowed})
    if bad:
        issues.append(
            Issue(
                field="sources", problem=f"ссылка на фрагмент, которого не было в контексте: {', '.join(bad)}"
            )
        )
    bad_map = sorted({v for v in card.characteristic_sources.values() if v not in allowed})
    if bad_map:
        issues.append(
            Issue(
                field="characteristic_sources",
                problem=f"характеристика ссылается на фрагмент вне контекста: {', '.join(bad_map)}",
            )
        )
    return issues


def decide_status(card: Card, problems: list[Issue], threshold: float) -> str:
    """Низкая уверенность или нерешённые проблемы — карточку ждёт человек, а не «готово»."""
    if problems or card.confidence < threshold:
        return STATUS_REVIEW
    return STATUS_WAITING


def _group(problems: list[Issue]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for p in problems:
        name = p.field if p.field in Card.model_fields else "characteristics"
        grouped.setdefault(name, []).append(p.problem)
    return {k: "; ".join(v) for k, v in grouped.items()}


def run_pipeline(
    llm: ChatLike,
    context: Context,
    product_hint: str | None,
    *,
    job_id: str | None,
) -> PipelineOutcome:
    settings = get_settings()
    rendered = context.render()
    facts = extract_facts(llm, context, product_hint, job_id=job_id)
    card = generate_card(llm, context, facts, product_hint, job_id=job_id)
    rounds = 0
    while True:
        problems = link_problems(card, context)
        verdict = check_card(llm, context, card, job_id=job_id)
        if not verdict.ok:
            problems += verdict.issues
        if not problems:
            return PipelineOutcome(card, decide_status(card, [], settings.confidence_threshold), rounds)
        if rounds >= settings.max_repair_rounds:
            # Петля исчерпана: дальше не крутим, карточка уходит человеку с перечнем проблем.
            return PipelineOutcome(card, STATUS_REVIEW, rounds, problems)
        rounds += 1
        draft = _as_dict(card)
        draft = repair_fields(llm, draft, _group(problems), Card, job_id=job_id, fragments_text=rendered)
        try:
            card = Card.model_validate(draft)
        except ValidationError as exc:
            # Переделка не довела до валидности: это тоже проблема карточки, цикл продолжится.
            problems = [
                Issue(field=str(e["loc"][0]) if e["loc"] else "characteristics", problem=e["msg"])
                for e in exc.errors()
            ]
            if rounds >= settings.max_repair_rounds:
                return PipelineOutcome(card_fallback(draft, card), STATUS_REVIEW, rounds, problems)
            card = card_fallback(draft, card)


def card_fallback(draft: dict[str, Any], previous: Card) -> Card:
    """Если переделанный черновик невалиден, оставляем предыдущую валидную карточку."""
    try:
        return Card.model_validate(draft)
    except ValidationError:
        return previous


def _as_dict(card: Card) -> dict[str, Any]:
    return json.loads(card.model_dump_json())
