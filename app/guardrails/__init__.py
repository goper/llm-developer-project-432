"""Защитные модули: маскирование ПДн, детектор инъекций, фильтр выхода карточки."""

from app.guardrails.injection import InjectionDetector, check_rules
from app.guardrails.pii import mask_pii

__all__ = ["InjectionDetector", "check_output", "check_rules", "mask_pii"]


def check_output(text: str) -> list[str]:
    """Проверяет готовую карточку. Пустой список означает, что проблем нет.

    В результате только метки и имена правил, исходные значения не возвращаются.
    """
    issues = [f"персональные данные: {finding.label}" for finding in mask_pii(text).findings]
    issues += [f"след служебной инструкции: {rule}" for rule in check_rules(text)]
    return issues
