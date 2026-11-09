"""Разбор xlsx: каждая строка данных листа — единица kind="row"."""

import zipfile
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from app.parsers.normalizer import format_row, normalize_text
from app.parsers.types import ParseError, Unit


def parse_xlsx(path: Path) -> list[Unit]:
    """Вернуть строки всех листов; первая строка каждого листа — заголовки колонок."""
    try:
        workbook = openpyxl.load_workbook(path, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, OSError) as exc:
        raise ParseError(f"не удалось открыть xlsx {path.name}: {exc}") from exc

    units: list[Unit] = []
    try:
        for sheet in workbook.worksheets:
            rows = [[_cell_to_str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
            if not rows:
                continue
            headers: list[str | None] = [value or None for value in rows[0]]
            header_line = "; ".join(header for header in headers if header) or None
            for values in rows[1:]:
                if not any(values):
                    continue
                text, sku = format_row(values, headers)
                if text:
                    units.append(
                        Unit(text=text, section=sheet.title, kind="row", header=header_line, sku=sku)
                    )
    finally:
        workbook.close()
    return units


def _cell_to_str(value: Any) -> str:
    """Значение ячейки в строку: целые без «.0», дробные как есть."""
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.10g}"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return normalize_text(str(value))
