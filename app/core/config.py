"""Настройки приложения. Читаются из переменных окружения и файла .env (см. .env.example)."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # База данных. Пул создаётся при старте приложения (app/core/db.py).
    database_url: str = "postgresql://app:app@localhost:5434/cards"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # Модель: OpenAI-совместимый API (LM Studio, Ollama или OpenRouter).
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "qwen2.5-14b-instruct"  # основная генерация
    llm_cheap_model: str = "qwen2.5-7b-instruct"  # служебные вызовы: проверка, классификация, детекторы
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 3  # повторы одного вызова (клиент), не шага
    llm_retry_base_seconds: float = 1.0
    # Как просим JSON: "schema" — схема уходит в запрос (response_format), "prompt" — текстом в инструкции.
    llm_structured_mode: str = "prompt"
    # Цены в долларах за миллион токенов. Decimal, а не float: деньги не считаем числами с плавающей точкой.
    price_main_input_per_mtok: Decimal = Decimal("0.50")
    price_main_output_per_mtok: Decimal = Decimal("1.50")
    price_cheap_input_per_mtok: Decimal = Decimal("0.05")
    price_cheap_output_per_mtok: Decimal = Decimal("0.15")

    # Эмбеддинги: локальная модель sentence-transformers, префиксы берутся из её карточки.
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dim: int = 384
    embedding_query_prefix: str = "query: "
    embedding_passage_prefix: str = "passage: "
    embedding_batch_size: int = 32
    # Порог релевантности (косинусная близость). Калибровка: docs/decisions/0003-relevance-threshold.md
    relevance_threshold: float = 0.82
    search_top_k: int = 8
    rrf_k: int = 60  # константа в формуле слияния рангов: 1 / (k + позиция)

    # Фрагменты и контекст.
    chunk_size: int = 800
    chunk_overlap: int = 120
    context_max_chars: int = 6000  # предел контекста генерации, в символах
    max_upload_bytes: int = 20 * 1024 * 1024
    upload_dir: Path = ROOT_DIR / "var" / "uploads"

    # Петли и пороги пайплайна.
    max_repair_rounds: int = 3  # петля переделки: не больше трёх кругов
    max_structured_attempts: int = 3  # лечение невалидного ответа модели
    confidence_threshold: float = 0.7  # ниже порога карточка ждёт человека
    title_max_length: int = 60
    injection_suspicious_limit: int = 2  # больше стольких подозрительных фрагментов — к человеку

    # Temporal: движок устойчивых процессов.
    temporal_address: str = Field(default="localhost:7234")
    temporal_namespace: str = "default"
    temporal_task_queue: str = "cards"
    temporal_activity_workers: int = 4

    # Логи.
    log_level: str = "INFO"

    @property
    def temporal_host(self) -> str:
        """Адрес Temporal вида host:port (то же, что temporal_address)."""
        return self.temporal_address

    @property
    def embed_dim(self) -> int:
        """Размерность вектора (то же, что embedding_dim)."""
        return self.embedding_dim

    @property
    def suspicious_chunk_limit(self) -> int:
        """Порог подозрительных фрагментов до needs_review (= injection_suspicious_limit)."""
        return self.injection_suspicious_limit


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Готовый объект настроек для модулей, которым удобнее импорт `from app.core.config import settings`.
settings = get_settings()
