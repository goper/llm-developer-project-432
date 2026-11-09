"""Контракт результата: валидаторы карточки и ограничения моделей."""

import pytest
from pydantic import ValidationError

from app.schemas.cards import Card

BASE = {
    "title": "Блендер",
    "seo": {"title": "t", "description": "d"},
    "confidence": 0.5,
}


def test_empty_characteristics_are_dropped() -> None:
    card = Card.model_validate({**BASE, "characteristics": {"мощность": "800 Вт", "цвет": "  "}})
    assert card.characteristics == {"мощность": "800 Вт"}


def test_field_cannot_be_in_both_lists() -> None:
    with pytest.raises(ValidationError, match="и в характеристиках, и в недостающих"):
        Card.model_validate({**BASE, "characteristics": {"цвет": "белый"}, "missing_fields": ["цвет"]})


def test_confidence_range() -> None:
    with pytest.raises(ValidationError):
        Card.model_validate({**BASE, "confidence": 1.5})


def test_title_length_limit() -> None:
    with pytest.raises(ValidationError, match="заголовок длиннее"):
        Card.model_validate({**BASE, "title": "х" * 200})
