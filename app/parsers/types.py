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
    doc_id: str | None = None
    chunk_id: str | None = None

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
        }
