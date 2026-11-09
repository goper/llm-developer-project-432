"""Защитные модули: маскирование ПДн, детектор инъекций, фильтр выхода карточки.

guard_context — рубежи до модели: маскирование и проверка инъекций по фрагментам.
guard_output — фильтр выхода: ПДн и следы служебных инструкций в сгенерированном тексте.
"""

import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.guardrails import injection as _injection
from app.guardrails.injection import (
    InjectionDetector,
    InjectionVerdict,
    check_rules,
    detect_injection_regex,
)
from app.guardrails.pii import mask_pii

logger = logging.getLogger(__name__)

__all__ = [
    "GuardReport",
    "InjectionDetector",
    "InjectionVerdict",
    "check_output",
    "check_rules",
    "detect_injection_llm",
    "detect_injection_regex",
    "guard_context",
    "guard_output",
    "mask_pii",
]

# Следы инъекции из документа, которые могли просочиться в карточку: цена «1 рубль» по указке текста.
_OUTPUT_TRACES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("price_one_rouble", re.compile(r"(?<![\d.,])1\s*(?:рубл\w*|руб\.?|₽)", re.IGNORECASE)),
)


@dataclass
class GuardReport:
    """Отчёт защиты: что замаскировано, что исключено и почему, что найдено на выходе."""

    masked: dict[str, int] = field(default_factory=dict)
    suspicious_chunks: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    output_issues: list[str] = field(default_factory=list)
    blocked: bool = False

    @property
    def excluded(self) -> list[str]:
        return self.suspicious_chunks

    @property
    def needs_review(self) -> bool:
        """Подозрительных фрагментов больше порога — документ уходит к человеку."""
        from app.core.config import get_settings

        return self.blocked or len(self.suspicious_chunks) > get_settings().injection_suspicious_limit

    @property
    def ok(self) -> bool:
        return not self.needs_review and not self.output_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "masked": dict(self.masked),
            "excluded": list(self.suspicious_chunks),
            "reasons": dict(self.reasons),
            "output_issues": list(self.output_issues),
            "blocked": self.needs_review,
        }


def check_output(text: str) -> list[str]:
    """Проверяет готовую карточку. Пустой список означает, что проблем нет.

    В результате только метки и имена правил, исходные значения не возвращаются.
    """
    issues = [f"персональные данные: {finding.label}" for finding in mask_pii(text).findings]
    issues += [f"след служебной инструкции: {rule}" for rule in check_rules(text)]
    issues += [f"след инъекции: {name}" for name, pattern in _OUTPUT_TRACES if pattern.search(text)]
    return issues


async def detect_injection_llm(text: str) -> InjectionVerdict:
    """Уровень 2 детектора; обёртка, чтобы подмена в модуле injection тоже действовала."""
    return await _injection.detect_injection_llm(text)


def _get(item: Any, *names: str) -> Any:
    for name in names:
        if isinstance(item, dict) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return None


def _with_text(item: Any, text: str) -> Any:
    if isinstance(item, dict):
        return {**item, "text": text}
    if isinstance(item, str):
        return text
    try:
        return replace(item, text=text)
    except TypeError:
        try:
            return item.model_copy(update={"text": text})
        except AttributeError:
            return item


def _text_of(item: Any) -> str:
    return item if isinstance(item, str) else str(_get(item, "text") or "")


async def guard_context(chunks: list[Any]) -> tuple[list[Any], GuardReport]:
    """Рубежи до вызова модели: маскирование ПДн, затем детектор инъекций в два уровня.

    Правила смотрят все фрагменты; модель — только помеченные правилами. Если модель упала
    или ответ не разобрать, фрагмент считается подозрительным (закрыто при сбое).
    Возвращает чистые фрагменты (тексты уже замаскированы) и отчёт.
    """
    report = GuardReport()
    clean: list[Any] = []
    for number, item in enumerate(chunks):
        result = mask_pii(_text_of(item))
        for finding in result.findings:
            report.masked[finding.kind] = report.masked.get(finding.kind, 0) + 1
        masked_item = _with_text(item, result.text)
        chunk_id = str(_get(item, "chunk_id", "id") or number)

        rules = detect_injection_regex(result.text)
        if not rules.suspicious:
            clean.append(masked_item)
            continue
        try:
            verdict = await detect_injection_llm(result.text)
        except Exception as exc:
            logger.warning("детектор инъекций недоступен, фрагмент %s исключён: %s", chunk_id, exc)
            verdict = InjectionVerdict(True, reason=f"детектор недоступен: {type(exc).__name__}")
        if verdict.suspicious:
            report.suspicious_chunks.append(chunk_id)
            report.reasons[chunk_id] = f"правила: {rules.reason}; {verdict.reason}".strip("; ")
        else:
            clean.append(masked_item)

    report.blocked = report.needs_review
    return clean, report


def guard_output(card: Any) -> tuple[Any, list[str]]:
    """Фильтр выхода: маскирует ПДн в карточке и перечисляет проблемы.

    Принимает JSON-строку, dict или модель; возвращает то же представление с маской и список проблем.
    """
    if hasattr(card, "model_dump"):
        text = json.dumps(card.model_dump(mode="json"), ensure_ascii=False)
    elif isinstance(card, dict | list):
        text = json.dumps(card, ensure_ascii=False)
    else:
        text = str(card)
    issues = check_output(text)
    cleaned_text = mask_pii(text).text
    if isinstance(card, str):
        return cleaned_text, issues
    cleaned = json.loads(cleaned_text)
    if hasattr(card, "model_validate"):
        try:
            return type(card).model_validate(cleaned), issues
        except Exception:
            return cleaned, issues
    return cleaned, issues
