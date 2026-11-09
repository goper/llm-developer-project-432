"""Таблица задач. Единственное место, где есть SQL для jobs.

Каждая операция берёт соединение из пула на время запроса и возвращает его сразу,
поэтому долгий шаг процесса не держит соединение (см. app/core/db.py).
"""

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from psycopg.rows import dict_row

from app.core.db import connection


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    status: str
    document_ids: list[str] = field(default_factory=list)
    product_hint: str | None = None
    idempotency_key: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def new_job_id() -> str:
    """Идентификатор задачи: 12 шестнадцатеричных символов, как в примере API."""
    return secrets.token_hex(6)


def _row_to_job(row: dict[str, Any]) -> Job:
    return Job(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        document_ids=list(row["document_ids"] or []),
        product_hint=row["product_hint"],
        idempotency_key=row["idempotency_key"],
        result=row["result"],
        error=row["error"],
    )


def create_job(
    *,
    kind: str,
    document_ids: list[str],
    product_hint: str | None,
    idempotency_key: str | None,
) -> tuple[Job, bool]:
    """Создаёт задачу. Если ключ идемпотентности уже занят — возвращает существующую задачу.

    Второе значение: True, если задача создана сейчас; False — вернули прежнюю.
    """
    job_id = new_job_id()
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, kind, status, idempotency_key, document_ids, product_hint)
            VALUES (%s, %s, 'pending', %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, kind, status, idempotency_key, document_ids, product_hint, result, error
            """,
            (job_id, kind, idempotency_key, document_ids, product_hint),
        )
        row = cur.fetchone()
        if row is not None:
            return _row_to_job(row), True
        cur.execute(
            """
            SELECT id, kind, status, idempotency_key, document_ids, product_hint, result, error
            FROM jobs WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        existing = cur.fetchone()
        if existing is None:  # теоретически: ключ удалили между запросами
            raise RuntimeError("задача с ключом идемпотентности не найдена")
        return _row_to_job(existing), False


def get_job(job_id: str) -> Job | None:
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, kind, status, idempotency_key, document_ids, product_hint, result, error
            FROM jobs WHERE id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()
    return _row_to_job(row) if row else None


def set_status(job_id: str, status: str, error: str | None = None) -> None:
    """Короткая запись состояния. Вызывается отдельным шагом процесса, а не изнутри пайплайна."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = %s, error = %s, updated_at = now() WHERE id = %s",
            (status, error, job_id),
        )


def save_result(job_id: str, result: dict[str, Any], status: str) -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs SET result = %s::jsonb, status = %s, updated_at = now() WHERE id = %s
            """,
            (json.dumps(result, ensure_ascii=False), status, job_id),
        )
