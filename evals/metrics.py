"""Метрики качества на эталоне data/golden_cards.json.

1. Доля характеристик, совпавших с эталоном (значения сравниваются после нормализации).
2. Доля ссылок, где заявленный источник действительно содержит утверждение (метрика цитирования).
3. Доля утверждений, подтверждённых источниками, по вердикту модели-судьи (оценка, не истина).
"""

import json
import re
from typing import Any

from app.agents.prompts import judge_messages
from app.services.json_utils import JsonReplyError, parse_json_reply


def normalize_value(value: str) -> str:
    """«800 Вт», «800 вт», «800 Вт.» и «800вт» — одно и то же. Запятая и точка в числах тоже равны."""
    text = value.casefold().replace(" ", " ").replace(",", ".")
    text = re.sub(r"\s+", "", text)
    return text.strip(" .;")


def characteristic_match(golden: dict[str, str], card_chars: dict[str, str]) -> tuple[int, int]:
    """(совпало, всего) по ключам эталона. Ключи сравниваются без учёта регистра."""
    lookup = {k.casefold().strip(): v for k, v in card_chars.items()}
    matched = 0
    for key, expected in golden.items():
        got = lookup.get(key.casefold().strip())
        if got is not None and normalize_value(got) == normalize_value(expected):
            matched += 1
    return matched, len(golden)


def citation_match(
    probes: dict[str, dict[str, Any]],
    card_sources: dict[str, str],
    chunk_by_id: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    """(ссылок ведут на нужный текст, всего проб) по source_probes эталона."""
    ok = 0
    for name, probe in probes.items():
        chunk_id = card_sources.get(name)
        chunk = chunk_by_id.get(chunk_id or "")
        if chunk is None:
            continue
        needle = normalize_value(probe["text_contains"])
        page_ok = probe.get("page") is None or chunk.get("page") in (None, probe["page"])
        if needle in normalize_value(chunk["text"]) and page_ok:
            ok += 1
    return ok, len(probes)


def parse_judge(text: str) -> float | None:
    """Доля подтверждённых утверждений из ответа судьи. None, если ответ не разобрать."""
    try:
        data = parse_json_reply(text)
    except JsonReplyError:
        return None
    if not isinstance(data, dict):
        return None
    share = data.get("supported_share")
    if isinstance(share, int | float) and 0 <= share <= 1:
        return float(share)
    claims = data.get("claims")
    if isinstance(claims, list) and claims:
        return sum(1 for c in claims if isinstance(c, dict) and c.get("supported") is True) / len(claims)
    return None


def judge_support(llm: Any, fragments_text: str, card: dict[str, Any], *, job_id: str | None) -> float | None:
    reply = llm.chat(
        judge_messages(fragments_text, json.dumps(card, ensure_ascii=False)),
        purpose="judge",
        job_id=job_id,
        cheap=True,
    )
    return parse_judge(reply.text)
