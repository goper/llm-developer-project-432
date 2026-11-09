"""Фрагменты документов и поиск по ним. SQL проекта по фрагментам живёт только здесь.

Три режима поиска — три отдельных метода:
- search_vector: ближайшие по косинусной близости (порог отсекает мусор);
- search_text: полнотекстовый поиск по словам и артикулам;
- search_hybrid: слияние рангов (reciprocal rank fusion): фрагмент, найденный обоими, выше.
Слияние идёт по позициям в списках, а не по оценкам: оценки двух поисков несопоставимы.
"""

from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from app.core.db import connection


@dataclass(frozen=True)
class ChunkRow:
    id: str
    document_id: str
    position: int
    page: int | None
    section: str | None
    kind: str
    sku: str | None
    brand: str | None
    text: str


@dataclass(frozen=True)
class ChunkHit:
    id: str
    document_id: str
    text: str
    page: int | None
    section: str | None
    sku: str | None
    brand: str | None
    score: float

    def metadata(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "page": self.page,
            "section": self.section,
            "sku": self.sku,
            "brand": self.brand,
        }


_FIELDS = "c.id, c.doc_id, c.text, c.page, c.section, c.sku, c.brand"


def _hit(row: dict[str, Any], score: float) -> ChunkHit:
    return ChunkHit(
        id=row["id"],
        document_id=row["doc_id"],
        text=row["text"],
        page=row["page"],
        section=row["section"],
        sku=row["sku"],
        brand=row["brand"],
        score=score,
    )


def replace_chunks(document_id: str, chunks: list[ChunkRow]) -> int:
    """Заменяет все фрагменты документа новыми. Повторный разбор даёт те же строки, без дублей."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE doc_id = %s", (document_id,))
        cur.executemany(
            """
            INSERT INTO chunks (id, doc_id, position, page, section, kind, sku, brand, text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (c.id, document_id, c.position, c.page, c.section, c.kind, c.sku, c.brand, c.text)
                for c in chunks
            ],
        )
    return len(chunks)


def count_for_document(document_id: str) -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE doc_id = %s", (document_id,))
        (count,) = cur.fetchone()
    return int(count)


def get_by_ids(chunk_ids: list[str]) -> dict[str, ChunkHit]:
    """Проверка ссылок: какие из фрагментов реально есть в базе."""
    if not chunk_ids:
        return {}
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_FIELDS}, 0.0::float AS score FROM chunks c WHERE c.id = ANY(%s)", (chunk_ids,))
        return {r["id"]: _hit(r, 0.0) for r in cur.fetchall()}


def list_without_embedding(limit: int, document_id: str | None = None) -> list[tuple[str, str, str | None]]:
    """Фрагменты без векторов: (id, текст, артикул). Пустой результат — досчитывать нечего."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, text, sku FROM chunks
            WHERE embedding IS NULL AND (%s::text IS NULL OR doc_id = %s::text)
            ORDER BY doc_id, position LIMIT %s
            """,
            (document_id, document_id, limit),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def count_without_embedding(document_id: str | None = None) -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM chunks
            WHERE embedding IS NULL AND (%s::text IS NULL OR doc_id = %s::text)
            """,
            (document_id, document_id),
        )
        (count,) = cur.fetchone()
    return int(count)


def set_embeddings(rows: list[tuple[str, list[float]]]) -> None:
    """Пишет векторы пачкой. Вектор передаём текстом и приводим к типу vector."""
    if not rows:
        return
    with connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "UPDATE chunks SET embedding = %s::vector WHERE id = %s",
            [(_vector_literal(vec), chunk_id) for chunk_id, vec in rows],
        )


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def search_vector(
    query_vector: list[float],
    *,
    top_k: int,
    threshold: float,
    document_ids: list[str] | None = None,
) -> list[ChunkHit]:
    qv = _vector_literal(query_vector)
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_FIELDS}, 1 - (c.embedding <=> %(qv)s::vector) AS score
            FROM chunks c
            WHERE c.embedding IS NOT NULL
              AND (%(doc_ids)s::text[] IS NULL OR c.doc_id = ANY(%(doc_ids)s::text[]))
              AND 1 - (c.embedding <=> %(qv)s::vector) >= %(threshold)s
            ORDER BY c.embedding <=> %(qv)s::vector
            LIMIT %(top_k)s
            """,
            {"qv": qv, "doc_ids": document_ids, "threshold": threshold, "top_k": top_k},
        )
        return [_hit(r, float(r["score"])) for r in cur.fetchall()]


def search_text(query_text: str, *, top_k: int, document_ids: list[str] | None = None) -> list[ChunkHit]:
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_FIELDS}, ts_rank_cd(c.tsv, q) AS score
            FROM chunks c, websearch_to_tsquery('russian', %(q)s) AS q
            WHERE c.tsv @@ q
              AND (%(doc_ids)s::text[] IS NULL OR c.doc_id = ANY(%(doc_ids)s::text[]))
            ORDER BY score DESC
            LIMIT %(top_k)s
            """,
            {"q": query_text, "doc_ids": document_ids, "top_k": top_k},
        )
        return [_hit(r, float(r["score"])) for r in cur.fetchall()]


def search_hybrid(
    query_vector: list[float],
    query_text: str,
    *,
    top_k: int,
    threshold: float,
    rrf_k: int,
    document_ids: list[str] | None = None,
) -> list[ChunkHit]:
    """Слияние по обратным позициям: вклад фрагмента = сумма 1 / (rrf_k + позиция) по спискам.

    Порог относится к векторной части: текстовое совпадение по артикулу проходит и при низкой
    близости, потому что артикул по смыслу может не совпадать ни с чем.
    """
    qv = _vector_literal(query_vector)
    pool = max(top_k * 4, 20)
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            WITH vec AS (
                SELECT id, row_number() OVER (ORDER BY dist) AS rnk
                FROM (
                    SELECT c.id, c.embedding <=> %(qv)s::vector AS dist
                    FROM chunks c
                    WHERE c.embedding IS NOT NULL
                      AND (%(doc_ids)s::text[] IS NULL OR c.doc_id = ANY(%(doc_ids)s::text[]))
                      AND 1 - (c.embedding <=> %(qv)s::vector) >= %(threshold)s
                    ORDER BY dist
                    LIMIT %(pool)s
                ) s
            ),
            txt AS (
                SELECT id, row_number() OVER (ORDER BY score DESC) AS rnk
                FROM (
                    SELECT c.id, ts_rank_cd(c.tsv, q) AS score
                    FROM chunks c, websearch_to_tsquery('russian', %(q)s) AS q
                    WHERE c.tsv @@ q
                      AND (%(doc_ids)s::text[] IS NULL OR c.doc_id = ANY(%(doc_ids)s::text[]))
                    ORDER BY score DESC
                    LIMIT %(pool)s
                ) s
            ),
            fused AS (
                SELECT id, sum(1.0 / (%(rrf_k)s + rnk)) AS score
                FROM (SELECT id, rnk FROM vec UNION ALL SELECT id, rnk FROM txt) u
                GROUP BY id
            )
            SELECT {_FIELDS}, f.score
            FROM fused f
            JOIN chunks c ON c.id = f.id
            ORDER BY f.score DESC
            LIMIT %(top_k)s
            """,
            {
                "qv": qv,
                "q": query_text,
                "doc_ids": document_ids,
                "threshold": threshold,
                "pool": pool,
                "rrf_k": rrf_k,
                "top_k": top_k,
            },
        )
        return [_hit(r, float(r["score"])) for r in cur.fetchall()]
