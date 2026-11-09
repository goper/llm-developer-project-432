"""Нормализация текста, колонтитулы и сборка строк таблиц."""

import re
from collections import Counter

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}
# Перенос по дефису: «мощ-\nность». Склеиваем, только если дальше строчная буква.
_HYPHEN_BREAK = re.compile(r"(\w)[-‐][ \t]*\n[ \t]*(?=[а-яёa-z])")
_NBSP_TABLE = str.maketrans({"\u00a0": " ", "\u202f": " "})
_SPACES = re.compile(r"[ \t]+")
_BLANK_RUN = re.compile(r"\n{3,}")
_PAGE_MARK = re.compile(
    r"(?:^|\s)(?:стр\.?|страница|page|p\.)\s*\d+(?:\s*/\s*\d+)?\s*$|^\d+(?:\s*/\s*\d+)?$",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"\d+")


def normalize_text(text: str) -> str:
    """Склеить переносы, убрать лигатуры и лишние пробелы."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1", text)
    for source, target in _LIGATURES.items():
        text = text.replace(source, target)
    text = text.translate(_NBSP_TABLE)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = _BLANK_RUN.sub("\n\n", "\n".join(lines))
    return text.strip()


def _line_key(line: str) -> str:
    """Ключ для сравнения строк; в строках-номерах страниц все цифры заменяются на «#»."""
    key = " ".join(line.split())
    if _PAGE_MARK.search(key):
        return _DIGITS.sub("#", key)
    return key


def strip_running_lines(pages: list[str]) -> list[str]:
    """Убрать колонтитулы: строки, повторяющиеся на >= 2 страницах и >= 50% страниц."""
    total = len(pages)
    if total < 2:
        return list(pages)
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({_line_key(line) for line in page.split("\n")})
    running = {key for key, count in counts.items() if count >= 2 and count / total >= 0.5}
    return ["\n".join(line for line in page.split("\n") if _line_key(line) not in running) for page in pages]


def format_row(values: list[str], headers: list[str | None]) -> tuple[str, str | None]:
    """Собрать текст строки таблицы вида «артикул: заголовок значение; ...».

    values и headers уже нормализованы; пустые значения пропускаются.
    Возвращает (текст, артикул); артикул — значение первой колонки.
    """
    sku = values[0] if values and values[0] else None
    pairs = []
    for index, value in enumerate(values[1:], start=1):
        if not value:
            continue
        header = headers[index] if index < len(headers) else None
        pairs.append(f"{header} {value}" if header else value)
    body = "; ".join(pairs)
    if sku is None:
        return body, None
    return (f"{sku}: {body}" if body else sku), sku


def clean_text(text: str) -> str:
    """Очистка текста: переносы, лигатуры, пробелы (то же, что normalize_text)."""
    return normalize_text(text)


def normalize(content: str | list[str]) -> str | list[str]:
    """Нормализация документа.

    Строка — чистится как один текст. Список страниц — сначала убираются колонтитулы,
    затем каждая страница чистится отдельно.
    """
    if isinstance(content, str):
        return normalize_text(content)
    return [normalize_text(page) for page in strip_running_lines(list(content))]
