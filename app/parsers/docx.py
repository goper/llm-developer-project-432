"""Разбор docx: абзацы с секциями по заголовкам и таблицы как строки."""

import zipfile
from collections.abc import Iterator

import docx
from docx.document import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.normalizer import format_table, normalize_text
from app.parsers.types import ParseError, Source, Unit, open_source, source_name


def parse_docx(source: Source) -> list[Unit]:
    """Вернуть текстовые единицы по секциям и таблицы (kind="table") в порядке документа."""
    try:
        document = docx.Document(open_source(source))
    except (PackageNotFoundError, zipfile.BadZipFile, OSError) as exc:
        raise ParseError(f"не удалось открыть docx {source_name(source)}: {exc}") from exc

    units: list[Unit] = []
    lines: list[str] = []
    section: str | None = None
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = normalize_text(block.text)
            if not text:
                continue
            if _is_heading(block):
                _flush(units, lines, section)
                section = text
            lines.append(text)
        else:
            _flush(units, lines, section)
            units.extend(_table_units(block, section))
    _flush(units, lines, section)
    return units


def _iter_blocks(document: DocxDocument) -> Iterator[Paragraph | Table]:
    """Абзацы и таблицы в порядке следования в теле документа."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _is_heading(paragraph: Paragraph) -> bool:
    style = paragraph.style.name if paragraph.style is not None else ""
    return style.startswith(("Heading", "Заголовок"))


def _flush(units: list[Unit], lines: list[str], section: str | None) -> None:
    """Сохранить накопленные абзацы одной секции как единицу."""
    if lines:
        units.append(Unit(text="\n".join(lines), section=section))
        lines.clear()


def _table_units(table: Table, section: str | None) -> list[Unit]:
    """Таблица целиком одним блоком kind="table"; первая строка таблицы — заголовки колонок."""
    rows = [[normalize_text(cell.text) for cell in row.cells] for row in table.rows]
    formatted = format_table(rows)
    if formatted is None:
        return []
    text, header_line = formatted
    kept = tuple(tuple(row) for row in rows if any(row))
    return [Unit(text=text, section=section, kind="table", header=header_line, rows=kept)]
