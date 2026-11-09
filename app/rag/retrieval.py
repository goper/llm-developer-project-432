"""Поиск: три режима поверх репозитория фрагментов. Порог и фильтры — параметрами.

vector_search — по смыслу (косинусная близость, порог отсекает мусор);
fts_search — по словам и артикулам (полнотекстовый поиск PostgreSQL);
hybrid_search — слияние рангов обоих (reciprocal rank fusion).
"""

from typing import Literal

from app.core.config import get_settings
from app.rag import embedder as _embedder
from app.rag.embedder import Embedder
from app.repositories import chunks as chunks_repo
from app.repositories.chunks import ChunkHit

Mode = Literal["vector", "text", "hybrid"]


def embed_query(text: str) -> list[float]:
    """Вектор запроса. Отдельной функцией, чтобы в тестах модель эмбеддингов легко подменялась."""
    return _embedder.embed_query(text)


def _vector(query: str, embedder: Embedder | None) -> list[float]:
    return embedder.embed_query(query) if embedder is not None else embed_query(query)


def _ids(doc_ids: list[str] | str | None, document_ids: list[str] | None) -> list[str] | None:
    ids = doc_ids if doc_ids is not None else document_ids
    if isinstance(ids, str):
        return [ids]
    return list(ids) if ids else None


def vector_search(
    query: str,
    top_k: int | None = None,
    *,
    threshold: float | None = None,
    doc_ids: list[str] | str | None = None,
    document_ids: list[str] | None = None,
    embedder: Embedder | None = None,
) -> list[ChunkHit]:
    s = get_settings()
    return chunks_repo.search_vector(
        _vector(query, embedder),
        top_k=top_k or s.search_top_k,
        threshold=s.relevance_threshold if threshold is None else threshold,
        document_ids=_ids(doc_ids, document_ids),
    )


def fts_search(
    query: str,
    top_k: int | None = None,
    *,
    doc_ids: list[str] | str | None = None,
    document_ids: list[str] | None = None,
) -> list[ChunkHit]:
    return chunks_repo.search_text(
        query, top_k=top_k or get_settings().search_top_k, document_ids=_ids(doc_ids, document_ids)
    )


def hybrid_search(
    query: str,
    top_k: int | None = None,
    *,
    threshold: float | None = None,
    doc_ids: list[str] | str | None = None,
    document_ids: list[str] | None = None,
    embedder: Embedder | None = None,
) -> list[ChunkHit]:
    s = get_settings()
    return chunks_repo.search_hybrid(
        _vector(query, embedder),
        query,
        top_k=top_k or s.search_top_k,
        threshold=s.relevance_threshold if threshold is None else threshold,
        rrf_k=s.rrf_k,
        document_ids=_ids(doc_ids, document_ids),
    )


def search(
    query: str,
    *,
    mode: Mode = "hybrid",
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    embedder: Embedder | None = None,
) -> list[ChunkHit]:
    if mode == "text":
        return fts_search(query, top_k, document_ids=document_ids)
    if mode == "vector":
        return vector_search(query, top_k, threshold=threshold, document_ids=document_ids, embedder=embedder)
    return hybrid_search(query, top_k, threshold=threshold, document_ids=document_ids, embedder=embedder)
