"""Общие типы парсеров: ошибки, единицы текста и фрагменты."""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

# Источник для парсера: путь к файлу или содержимое файла байтами.
Source = Path | str | bytes | bytearray | BinaryIO


def open_source(source: Source) -> Path | BinaryIO:
    """Байты оборачиваем в поток, путь отдаём как есть."""
    if isinstance(source, bytes | bytearray):
        return io.BytesIO(bytes(source))
    if isinstance(source, str):
        return Path(source)
    return source


def source_name(source: Source) -> str:
    return source.name if isinstance(source, Path) else "файл"


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
    kind: Literal["text", "row", "table"] = "text"
    header: str | None = None
    sku: str | None = None

    @property
    def content(self) -> str:
        """Текст блока (то же, что text)."""
        return self.text


@dataclass(frozen=True)
class Chunk:
    """Фрагмент документа для индексации."""

    text: str
    position: int
    page: int | None
    section: str | None
    kind: Literal["text", "row", "table"]
    sku: str | None
    doc_id: str | None = None
    chunk_id: str | None = None

    def __getitem__(self, key: str) -> object:
        """Фрагмент читается и как словарь: chunk["text"], chunk["metadata"]["page"]."""
        if key in ("text", "chunk_id", "doc_id", "metadata", "position", "page", "section", "kind", "sku"):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: object = None) -> object:
        try:
            return self[key]
        except KeyError:
            return default

    @property
    def metadata(self) -> dict[str, object]:
        """Метаданные фрагмента: откуда он и что это."""
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "position": self.position,
            "page": self.page,
            "section": self.section,
            "kind": self.kind,
            "sku": self.sku,
            "articul": self.sku,
        }
