"""Поиск: три режима поверх репозитория фрагментов. Порог и фильтры — параметрами."""

from typing import Literal

from app.core.config import get_settings
from app.rag.embedder import Embedder, get_embedder
from app.repositories import chunks as chunks_repo
from app.repositories.chunks import ChunkHit

Mode = Literal["vector", "text", "hybrid"]


def search(
    query: str,
    *,
    mode: Mode = "hybrid",
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    embedder: Embedder | None = None,
) -> list[ChunkHit]:
    s = get_settings()
    k = top_k or s.search_top_k
    thr = s.relevance_threshold if threshold is None else threshold
    if mode == "text":
        return chunks_repo.search_text(query, top_k=k, document_ids=document_ids)
    vec = (embedder or get_embedder()).embed_query(query)
    if mode == "vector":
        return chunks_repo.search_vector(vec, top_k=k, threshold=thr, document_ids=document_ids)
    return chunks_repo.search_hybrid(
        vec, query, top_k=k, threshold=thr, rrf_k=s.rrf_k, document_ids=document_ids
    )
