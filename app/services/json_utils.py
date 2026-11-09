"""Разбор грязного ответа модели.

Модель оборачивает JSON в markdown-заборы, пишет вступление и пояснение после.
Здесь мы достаём JSON из всех этих форм и даём понятную ошибку, если разобрать нельзя.
"""

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class JsonReplyError(ValueError):
    """В ответе модели нет разбираемого JSON."""


def parse_json_reply(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise JsonReplyError("пустой ответ модели")

    # 1. Чистый JSON.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. JSON внутри markdown-забора ```json ... ```.
    for match in _FENCE.finditer(raw):
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue

    # 3. JSON с текстом до и после: берём первый объект или массив, который разбирается.
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(raw, index)
        except json.JSONDecodeError:
            continue
        return value

    raise JsonReplyError("в ответе модели не нашлось JSON")
