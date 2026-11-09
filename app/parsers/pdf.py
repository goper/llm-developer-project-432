"""Разбор pdf: текст постранично и таблицы отдельными блоками.

Таблицы ищет pdfplumber по линиям сетки. Текст страницы берётся без области таблиц,
чтобы содержимое таблицы не попало в индекс дважды: и сплошным текстом, и таблицей.
"""

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from app.parsers.normalizer import format_table, normalize_text, strip_running_lines
from app.parsers.types import NoTextLayerError, ParseError, Source, Unit, open_source, source_name

_MIN_TEXT_CHARS = 20


def parse_pdf(source: Source) -> list[Unit]:
    """Блоки по страницам (page с 1): текст страницы, затем её таблицы (kind="table").

    Скан без текстового слоя — NoTextLayerError, а не пустой результат.
    """
    try:
        with pdfplumber.open(open_source(source)) as pdf:
            pages = [_read_page(page) for page in pdf.pages]
    except (PDFSyntaxError, PdfminerException, OSError, ValueError) as exc:
        raise ParseError(f"не удалось открыть pdf {source_name(source)}: {exc}") from exc

    total_chars = sum(len("".join(text.split())) for text, tables in pages) + sum(
        len("".join(t[0].split())) for _, tables in pages for t in tables
    )
    if total_chars < _MIN_TEXT_CHARS:
        raise NoTextLayerError("нет текстового слоя: похоже на скан, распознавание не подключено")

    texts = strip_running_lines([normalize_text(text) for text, _ in pages])
    units: list[Unit] = []
    for number, (text, (_, tables)) in enumerate(zip(texts, pages, strict=True), start=1):
        if text:
            units.append(Unit(text=text, page=number))
        for table_text, header, rows in tables:
            units.append(Unit(text=table_text, page=number, kind="table", header=header, rows=rows))
    return units


def _read_page(page) -> tuple[str, list[tuple[str, str | None, tuple[tuple[str, ...], ...]]]]:
    """Текст страницы вне таблиц и таблицы страницы: (текст, строка заголовков, строки)."""
    found = page.find_tables()
    boxes = [table.bbox for table in found]

    def outside_tables(obj: dict) -> bool:
        x = (obj["x0"] + obj["x1"]) / 2
        y = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in boxes)

    text = page.filter(outside_tables).extract_text() if boxes else page.extract_text()
    tables = []
    for table in found:
        rows = [[normalize_text(cell or "") for cell in row] for row in table.extract()]
        formatted = format_table(rows)
        if formatted is not None:
            tables.append((*formatted, tuple(tuple(row) for row in rows if any(row))))
    return text or "", tables


# Имя из практики темы: pdf без текстового слоя.
PdfNoTextLayer = NoTextLayerError
