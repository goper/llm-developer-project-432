"""Пул соединений с PostgreSQL.

Пул создаётся один раз при старте приложения и закрывается при остановке (ресурс уровня приложения).
Операция берёт соединение через connection() и возвращает его сразу после работы.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

_pool: ConnectionPool | None = None


def init_pool(database_url: str | None = None) -> ConnectionPool:
    """Создаёт пул, если он ещё не создан. Вызывается на старте приложения и воркера."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=database_url or settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            open=True,
            timeout=10.0,  # ждать свободное соединение не дольше 10 с: готовность отвечает быстро
            kwargs={"autocommit": False},
        )
    return _pool


def pool() -> ConnectionPool:
    """Отдаёт пул. Если его ещё нет — создаёт (удобно для скриптов и тестов)."""
    return init_pool()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[Connection]:
    """Соединение на одну операцию: транзакция коммитится при успехе и откатывается при ошибке."""
    with pool().connection() as conn:
        yield conn
