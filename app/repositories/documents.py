"""Таблица документов поставщиков. SQL только здесь."""

import secrets
from dataclasses import dataclass

from psycopg.rows import dict_row

from app.core.db import connection


@dataclass(frozen=True)
class Document:
    id: str
    sha256: str
    filename: str
    size_bytes: int
    status: str
    error: str | None
    chunks_count: int = 0


_COLUMNS = """
    d.id, d.content_hash AS sha256, d.filename, d.size_bytes, d.status, d.error,
    (SELECT count(*) FROM chunks c WHERE c.doc_id = d.id) AS chunks_count
"""


def _row(row: dict) -> Document:
    return Document(
        id=row["id"],
        sha256=row["sha256"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        error=row["error"],
        chunks_count=row["chunks_count"],
    )


def create_or_get(*, sha256: str, filename: str, size_bytes: int) -> tuple[Document, bool]:
    """Идемпотентная загрузка: тот же файл (по хэшу содержимого) не создаёт дубля.

    Возвращает (документ, создан_ли_сейчас).
    """
    doc_id = secrets.token_hex(6)
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO documents (id, content_hash, filename, kind, size_bytes, status)
            VALUES (%s, %s, %s, %s, %s, 'new')
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            (
                doc_id,
                sha256,
                filename,
                filename.rsplit(".", 1)[-1].lower() if "." in filename else None,
                size_bytes,
            ),
        )
        created = cur.fetchone() is not None
        cur.execute(
            f"SELECT {_COLUMNS} FROM documents d WHERE d.content_hash = %s",
            (sha256,),
        )
        return _row(cur.fetchone()), created


def get(doc_id: str) -> Document | None:
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM documents d WHERE d.id = %s", (doc_id,))
        row = cur.fetchone()
    return _row(row) if row else None


def get_many(doc_ids: list[str]) -> list[Document]:
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM documents d WHERE d.id = ANY(%s) ORDER BY d.id", (doc_ids,))
        return [_row(r) for r in cur.fetchall()]


def set_status(doc_id: str, status: str, error: str | None = None) -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET status = %s, error = %s, updated_at = now() WHERE id = %s",
            (status, error, doc_id),
        )
