"""Пайплайн с подменённым клиентом модели: успех, переделка, петля исчерпана, выдуманная ссылка."""

import json
from dataclasses import dataclass

from app.core.config import get_settings
from app.rag.context import Context, ContextItem
from app.services import pipeline
from app.services.json_utils import parse_json_reply


@dataclass
class Reply:
    text: str


class FakeLLM:
    """Отдаёт ответы по очереди и считает вызовы. Ответ по purpose — если задан словарь."""

    def __init__(self, script: dict[str, list[str]]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    def chat(self, messages, *, purpose, job_id=None, cheap=False, json_schema=None):
        self.calls.append(purpose)
        queue = self.script.get(purpose)
        if not queue:
            raise AssertionError(f"нет заготовленного ответа для {purpose}")
        return Reply(queue[0] if len(queue) == 1 else queue.pop(0))


CONTEXT = Context(
    items=[
        ContextItem(
            chunk_id="c1", text="Мощность 800 Вт. Гарантия 24 месяца.", page=1, section="Характеристики"
        ),
    ]
)

GOOD_CARD = {
    "title": "Блендер BLD-800, 800 Вт",
    "description": "Погружной блендер.",
    "characteristics": {"мощность": "800 Вт"},
    "characteristic_sources": {"мощность": "c1"},
    "benefits": [],
    "seo": {"title": "Блендер 800 Вт", "description": "Погружной блендер 800 Вт", "keywords": []},
    "sources": [{"chunk_id": "c1", "page": 1, "section": "Характеристики"}],
    "missing_fields": ["Цвет"],
    "confidence": 0.9,
}
FACTS = {"items": [{"text": "Мощность 800 Вт", "chunk_id": "c1", "characteristic": "мощность"}]}
OK_VERDICT = {"ok": True, "issues": []}


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_success_goes_to_waiting_approval() -> None:
    llm = FakeLLM({"extract": [_json(FACTS)], "generate": [_json(GOOD_CARD)], "check": [_json(OK_VERDICT)]})
    out = pipeline.run_card_pipeline(llm, CONTEXT, "блендер", job_id=None)
    assert out.status == "waiting_approval"
    assert out.rounds == 0
    assert out.card.characteristics == {"мощность": "800 Вт"}


def test_low_confidence_goes_to_review() -> None:
    card = {**GOOD_CARD, "confidence": 0.3}
    llm = FakeLLM({"extract": [_json(FACTS)], "generate": [_json(card)], "check": [_json(OK_VERDICT)]})
    out = pipeline.run_card_pipeline(llm, CONTEXT, None, job_id=None)
    assert out.status == "needs_review"


def test_long_title_is_repaired_point_wise() -> None:
    bad = {**GOOD_CARD, "title": "Т" * (get_settings().title_max_length + 5)}
    llm = FakeLLM(
        {
            "extract": [_json(FACTS)],
            "generate": [_json(bad)],
            "repair_field": [_json({"fields": {"title": "Блендер 800 Вт"}})],
            "check": [_json(OK_VERDICT)],
        }
    )
    out = pipeline.run_card_pipeline(llm, CONTEXT, None, job_id=None)
    assert out.card.title == "Блендер 800 Вт"
    assert out.card.description == GOOD_CARD["description"]
    assert llm.calls.count("repair_field") == 1


def test_fabricated_link_triggers_repair_then_loop_is_bounded() -> None:
    fake = {**GOOD_CARD, "sources": [{"chunk_id": "ghost"}]}
    llm = FakeLLM(
        {
            "extract": [_json(FACTS)],
            "generate": [_json(fake)],
            "repair_field": [_json({"fields": {"sources": [{"chunk_id": "ghost"}]}})],
            "check": [_json(OK_VERDICT)],
        }
    )
    out = pipeline.run_card_pipeline(llm, CONTEXT, None, job_id=None)
    assert out.status == "needs_review"
    assert out.rounds == get_settings().max_repair_rounds
    assert llm.calls.count("repair_field") == get_settings().max_repair_rounds
    assert any("не было в контексте" in p.problem for p in out.problems)


def test_link_problems_detects_unseen_chunk() -> None:
    from app.schemas.cards import Card

    card = Card.model_validate({**GOOD_CARD, "sources": [{"chunk_id": "c1"}, {"chunk_id": "x9"}]})
    problems = pipeline.link_problems(card, CONTEXT)
    assert len(problems) == 1
    assert "x9" in problems[0].problem


def test_parse_json_reply_handles_four_shapes() -> None:
    assert parse_json_reply('{"a": 1}') == {"a": 1}
    assert parse_json_reply('```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json_reply('Вот результат: {"a": 3} Надеюсь, помогло.') == {"a": 3}
    try:
        parse_json_reply("совсем не json")
    except ValueError as exc:
        assert "JSON" in str(exc)
    else:
        raise AssertionError("мусор должен давать ошибку")


def test_empty_reply_is_an_error_after_attempts() -> None:
    import pytest

    from app.services.structured import StructuredError

    llm = FakeLLM({"extract": [""]})
    with pytest.raises(StructuredError):
        pipeline.extract_facts(llm, CONTEXT, None, job_id=None)
