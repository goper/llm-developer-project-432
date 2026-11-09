"""Общие типы парсеров: ошибки, единицы текста и фрагменты."""

from dataclasses import dataclass
from typing import Literal


class ParseError(Exception):
    """Базовая ошибка разбора документа."""


class NoTextLayerError(ParseError):
    """В pdf нет текстового слоя (скан)."""


@dataclass(frozen=True)
class Unit:
    """Нормализованная единица текста документа."""

    text: str
    page: int | None = None
    section: str | None = None
    kind: Literal["text", "row"] = "text"
    header: str | None = None
    sku: str | None = None


@dataclass(frozen=True)
class Chunk:
    """Фрагмент документа для индексации."""

    text: str
    position: int
    page: int | None
    section: str | None
    kind: Literal["text", "row"]
    sku: str | None
