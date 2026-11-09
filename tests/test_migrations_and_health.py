"""Миграции: повторный запуск ничего не применяет. Проверки состояния: живость и готовность."""

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.config import get_settings
from app.core.migrate import migrate

pytestmark = pytest.mark.db


def test_second_migrate_applies_nothing(db_url: str) -> None:
    assert migrate(db_url) == []


def test_live_works_and_ready_reports_vector(clean_db: str) -> None:
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["vector"]


def test_live_survives_database_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    # Пул указываем на недоступный порт: живость обязана ответить, готовность — нет.
    broken = get_settings().model_copy(update={"database_url": "postgresql://app:app@127.0.0.1:1/none"})
    db_module.close_pool()
    monkeypatch.setattr(db_module, "get_settings", lambda: broken)
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 503
    finally:
        db_module.close_pool()
