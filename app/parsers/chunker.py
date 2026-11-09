"""Нарезка единиц текста на фрагменты для индексации."""

from dataclasses import replace
from typing import Literal

from app.parsers.types import Chunk, Unit

_BOUNDARY_WINDOW = 100
_SENTENCE_END = ".!?;"


def chunk_units(units: list[Unit], *, size: int = 800, overlap: int = 120) -> list[Chunk]:
    """Порезать единицы: текст окнами с перекрытием, строка таблицы — целым фрагментом."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("нужно size > 0 и 0 <= overlap < size")

    pieces: list[Chunk] = []
    rows: list[Unit] = []
    for unit in units:
        if not unit.text.strip():
            continue
        if unit.kind == "row":
            if rows and (rows[0].section, rows[0].header) != (unit.section, unit.header):
                pieces.extend(_chunk_rows(rows, size))
                rows = []
            rows.append(unit)
            continue
        if rows:
            pieces.extend(_chunk_rows(rows, size))
            rows = []
        pieces.extend(_chunk_text(unit, size, overlap))
    if rows:
        pieces.extend(_chunk_rows(rows, size))

    return [replace(chunk, position=number) for number, chunk in enumerate(pieces)]


def _chunk_text(unit: Unit, size: int, overlap: int) -> list[Chunk]:
    """Окна по size символов с перекрытием; граница — по пробелу или концу предложения."""
    text = unit.text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = _find_end(text, start, size)
        piece = text[start:end].strip()
        if piece:
            chunks.append(_make_chunk(piece, unit.page, unit.section, "text", unit.sku))
        if end >= len(text):
            break
        start = _find_next_start(text, start, end, overlap)
    return chunks


def _find_end(text: str, start: int, size: int) -> int:
    """Конец окна: ближайшая к лимиту граница слова в последних символах окна."""
    limit = min(start + size, len(text))
    if limit == len(text):
        return limit
    floor = max(start + 1, limit - _BOUNDARY_WINDOW)
    for cut in range(limit, floor, -1):
        if text[cut - 1].isspace() or (text[cut - 1] in _SENTENCE_END and text[cut].isspace()):
            return cut
    return limit


def _find_next_start(text: str, start: int, end: int, overlap: int) -> int:
    """Начало следующего окна: перекрытие назад от конца, но не раньше начала текущего."""
    candidate = end - overlap
    if candidate <= start:
        return end
    if not text[candidate - 1].isspace():
        for index in range(candidate, min(end, candidate + _BOUNDARY_WINDOW)):
            if text[index].isspace():
                candidate = index
                break
    while candidate < end and text[candidate].isspace():
        candidate += 1
    return candidate


def _chunk_rows(rows: list[Unit], size: int) -> list[Chunk]:
    """Каждая строка таблицы — отдельный фрагмент «артикул: параметр значение; ...».

    Заголовки колонок уже вписаны в текст строки, поэтому строка понятна сама по себе
    и никогда не рвётся между фрагментами (size для строк не применяется).
    """
    return [_make_chunk(unit.text, unit.page, unit.section, "row", unit.sku) for unit in rows]


def _make_chunk(
    text: str, page: int | None, section: str | None, kind: Literal["text", "row"], sku: str | None
) -> Chunk:
    return Chunk(text=text, position=0, page=page, section=section, kind=kind, sku=sku)


def chunk_blocks(blocks: list[Unit], *, size: int = 800, overlap: int = 120) -> list[Chunk]:
    """Резка структурных блоков документа на фрагменты (то же, что chunk_units)."""
    return chunk_units(blocks, size=size, overlap=overlap)
