"""Агенты ролей для асинхронного пути (OpenAI Agents SDK).

Агент — это инструкция роли плюс имя модели. Вызов — только через app.llm.client.run_agent:
там повторы на временных ошибках и учёт токенов. Основная модель — генерация; дешёвая —
извлечение, проверка и детектор инъекций (см. docs/decisions/0004-two-models.md).
"""

from functools import lru_cache

from agents import Agent

from app.agents.prompts import BASE_RULES
from app.core.config import get_settings

EXTRACT_INSTRUCTIONS = (
    BASE_RULES + "\nРоль: извлечение фактов. Выпиши факты о товаре с chunk_id. "
    'Формат: {"items": [{"text": "...", "chunk_id": "...", "characteristic": "имя характеристики или null"}]}'
)
GENERATE_INSTRUCTIONS = (
    BASE_RULES + "\nРоль: сборка карточки. Заполни title (не длиннее 60 символов), description, "
    "characteristics (имя -> значение), benefits, seo (title до 60, description до 160), "
    "sources (chunk_id, doc_id, page), characteristic_sources (имя характеристики -> chunk_id), "
    "missing_fields, confidence от 0 до 1."
)
CRITIC_INSTRUCTIONS = (
    BASE_RULES + "\nРоль: проверка черновика. Сверь каждое утверждение карточки с фактами и текстом "
    "поставщика. Утверждение без подтверждения, выдуманная характеристика, вода в описании — проблема. "
    'Ответ: {"verdict": "approve" | "regenerate", "issues": ["что не так", ...]}'
)


@lru_cache
def extract_agent() -> Agent:
    return Agent(name="extract", instructions=EXTRACT_INSTRUCTIONS, model=get_settings().llm_cheap_model)


@lru_cache
def generate_agent() -> Agent:
    return Agent(name="generate", instructions=GENERATE_INSTRUCTIONS, model=get_settings().llm_model)


@lru_cache
def critic_agent() -> Agent:
    return Agent(name="critic", instructions=CRITIC_INSTRUCTIONS, model=get_settings().llm_cheap_model)
