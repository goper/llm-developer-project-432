"""Защитные модули: маскирование ПДн, детектор инъекций, фильтр выхода карточки.

guard_context — рубежи до модели: маскирование и проверка инъекций по фрагментам.
guard_output — фильтр выхода: ПДн и следы служебных инструкций в сгенерированном тексте.
"""

import json
from dataclasses import dataclass, field, replace
from typing import Any

from app.guardrails.injection import InjectionDetector, check_rules
from app.guardrails.pii import mask_pii

__all__ = [
    "GuardReport",
    "InjectionDetector",
    "check_output",
    "check_rules",
    "guard_context",
    "guard_output",
    "mask_pii",
]


@dataclass
class GuardReport:
    """Отчёт защиты: что замаскировано, что исключено и почему, что найдено на выходе."""

    masked: dict[str, int] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    output_issues: list[str] = field(default_factory=list)
    blocked: bool = False

    @property
    def ok(self) -> bool:
        return not self.blocked and not self.output_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "masked": dict(self.masked),
            "excluded": list(self.excluded),
            "reasons": dict(self.reasons),
            "output_issues": list(self.output_issues),
            "blocked": self.blocked,
        }


def check_output(text: str) -> list[str]:
    """Проверяет готовую карточку. Пустой список означает, что проблем нет.

    В результате только метки и имена правил, исходные значения не возвращаются.
    """
    issues = [f"персональные данные: {finding.label}" for finding in mask_pii(text).findings]
    issues += [f"след служебной инструкции: {rule}" for rule in check_rules(text)]
    return issues


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
    try:
        return replace(item, text=text)
    except TypeError:
        return item


def guard_context(
    chunks: list[Any],
    llm: Any | None = None,
    *,
    max_suspicious: int | None = None,
) -> tuple[list[Any], GuardReport]:
    """Рубежи до вызова модели: маскирование ПДн, затем детектор инъекций.

    Возвращает чистые фрагменты (тексты уже замаскированы) и отчёт. Если подозрительных
    фрагментов больше порога, report.blocked = True: документ уходит к человеку.
    Без llm работает только уровень правил, и помеченный правилами фрагмент исключается.
    """
    report = GuardReport()
    masked_items = []
    for item in chunks:
        result = mask_pii(str(_get(item, "text") or ""))
        for finding in result.findings:
            report.masked[finding.kind] = report.masked.get(finding.kind, 0) + 1
        masked_items.append(_with_text(item, result.text))

    pairs = [
        (str(_get(i, "id", "chunk_id") or n), str(_get(i, "text") or "")) for n, i in enumerate(masked_items)
    ]
    if llm is not None:
        verdicts = {v.fragment_id: v for v in InjectionDetector(llm).screen(pairs)}
        suspicious = {
            fid: f"{v.via}: {', '.join(v.rule_hits)}" for fid, v in verdicts.items() if v.suspicious
        }
    else:
        suspicious = {fid: "rules: " + ", ".join(hits) for fid, text in pairs if (hits := check_rules(text))}

    clean = [item for (fid, _), item in zip(pairs, masked_items, strict=True) if fid not in suspicious]
    report.excluded = list(suspicious)
    report.reasons = dict(suspicious)
    if max_suspicious is None:
        from app.core.config import get_settings

        max_suspicious = get_settings().injection_suspicious_limit
    report.blocked = len(suspicious) > max_suspicious
    return clean, report


def guard_output(card: Any) -> GuardReport:
    """Фильтр выхода: проверяет весь текст карточки (dict, модель или строку)."""
    if hasattr(card, "model_dump"):
        text = json.dumps(card.model_dump(), ensure_ascii=False)
    elif isinstance(card, dict | list):
        text = json.dumps(card, ensure_ascii=False)
    else:
        text = str(card)
    return GuardReport(output_issues=check_output(text))
