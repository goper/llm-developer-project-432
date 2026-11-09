"""Данные, которые ходят между процессами и активностями Temporal. Только простые типы (dict, list, str)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerateInput:
    job_id: str
    document_ids: list[str]
    product_hint: str | None = None
    max_repair_rounds: int = 3  # лимит петли передаём аргументом: настройки в песочнице процесса не читаем


@dataclass
class SetStatusInput:
    job_id: str
    status: str
    error: str | None = None


@dataclass
class SearchInput:
    job_id: str
    query: str
    document_ids: list[str] = field(default_factory=list)


@dataclass
class AssembleInput:
    job_id: str
    hits: list[dict[str, Any]]


@dataclass
class ExtractInput:
    job_id: str
    context: dict[str, Any]
    product_hint: str | None


@dataclass
class GenerateCardInput:
    job_id: str
    context: dict[str, Any]
    facts: dict[str, Any]
    product_hint: str | None
    feedback: str | None = None


@dataclass
class CheckInput:
    job_id: str
    context: dict[str, Any]
    card: dict[str, Any]


@dataclass
class RepairInput:
    job_id: str
    context: dict[str, Any]
    card: dict[str, Any]
    problems: dict[str, str]


@dataclass
class FinishInput:
    job_id: str
    card: dict[str, Any]
    problems: list[dict[str, str]]
    rounds: int
    context_report: dict[str, Any]


@dataclass
class DecisionInput:
    job_id: str
    decision: str  # approved | rejected
