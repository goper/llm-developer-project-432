"""Разбор pdf: текст постранично."""

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.parsers.normalizer import normalize_text, strip_running_lines
from app.parsers.types import NoTextLayerError, ParseError, Source, Unit, open_source, source_name

_MIN_TEXT_CHARS = 20


def parse_pdf(source: Source) -> list[Unit]:
    """Вернуть по одной единице на страницу (page с 1). Скан без текста — ошибка."""
    try:
        raw_pages = [page.extract_text() or "" for page in PdfReader(open_source(source)).pages]
    except (PyPdfError, OSError) as exc:
        raise ParseError(f"не удалось открыть pdf {source_name(source)}: {exc}") from exc

    if sum(len("".join(page.split())) for page in raw_pages) < _MIN_TEXT_CHARS:
        raise NoTextLayerError("нет текстового слоя: похоже на скан, распознавание не подключено")

    pages = strip_running_lines([normalize_text(page) for page in raw_pages])
    return [Unit(text=text, page=number) for number, text in enumerate(pages, start=1) if text]


# Имя из практики темы: pdf без текстового слоя.
PdfNoTextLayer = NoTextLayerError
