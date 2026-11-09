"""Раннер SQL-миграций.

Файлы db/migrations/NNNN_название.sql применяются по порядку имён, каждый в своей транзакции.
Версия записывается в таблицу schema_migrations. Таблицу создаёт сама первая миграция.
Повторный запуск ничего не применяет.

Запуск: python -m app.core.migrate  (или make migrate)
"""

import sys
from pathlib import Path

import psycopg

from app.core.config import ROOT_DIR, get_settings

MIGRATIONS_DIR = ROOT_DIR / "db" / "migrations"


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = sorted(directory.glob("*.sql"))
    prefixes = [f.name.split("_", 1)[0] for f in files]
    if len(set(prefixes)) != len(prefixes):
        raise RuntimeError("Два файла миграций с одним числовым префиксом недопустимы")
    return files


def applied_versions(conn: psycopg.Connection) -> set[str]:
    """Версии, которые уже записаны. Если таблицы ещё нет — пусто."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        (exists,) = cur.fetchone()
        if not exists:
            return set()
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def migrate(database_url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Применяет новые миграции и возвращает список применённых версий."""
    url = database_url or get_settings().database_url
    applied_now: list[str] = []
    with psycopg.connect(url, autocommit=False) as conn:
        done = applied_versions(conn)
        for path in migration_files(directory):
            version = path.stem
            if version in done:
                continue
            sql_text = path.read_text(encoding="utf-8")
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(sql_text)
                # К этому моменту таблица версий уже есть: её создаёт первая миграция.
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now


def main() -> int:
    applied = migrate()
    if applied:
        for version in applied:
            print(f"Миграция применена: {version}")
    else:
        print("Новых миграций нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
