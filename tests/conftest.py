"""Общие фикстуры. Тесты не ходят в модель: LLM подменяется фейком, эмбеддинги — векторами руками."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.migrate import migrate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DB = "postgresql://app:app@localhost:5434/cards_test"


def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB)


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    """Миграции на тестовой базе; если базы нет — тесты с маркером db пропускаются, а не падают."""
    import psycopg

    url = test_database_url()
    try:
        psycopg.connect(url, connect_timeout=3).close()
    except psycopg.OperationalError as exc:
        pytest.skip(f"нет тестовой базы ({exc.__class__.__name__}); поднимите make up")
    migrate(url)
    yield url


@pytest.fixture
def clean_db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Чистит данные перед тестом и подключает пул к тестовой базе."""
    import psycopg

    from app.core import db as db_module

    monkeypatch.setenv("DATABASE_URL", db_url)
    db_module.close_pool()
    db_module.init_pool(db_url)
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute("TRUNCATE chunks, documents, jobs, llm_calls RESTART IDENTITY CASCADE")
    yield db_url
    db_module.close_pool()
