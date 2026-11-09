"""Эмбеддинги локально через sentence-transformers.

Модель грузится один раз (лениво, при первом вызове), векторы считаются пачкой.
Префиксы запроса и документа берутся из настроек; у e5-моделей они часть контракта.
"""

import threading
from functools import lru_cache
from typing import Any

from app.core.config import get_settings


class Embedder:
    def __init__(
        self,
        model_name: str,
        dim: int,
        *,
        passage_prefix: str,
        query_prefix: str,
        batch_size: int,
    ) -> None:
        self._model_name = model_name
        self._dim = dim
        self._passage_prefix = passage_prefix
        self._query_prefix = query_prefix
        self._batch_size = batch_size
        self._model: Any | None = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer  # тяжёлый импорт — только здесь

                    self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        result = [[float(x) for x in row] for row in vectors]
        if any(len(v) != self._dim for v in result):
            raise ValueError(f"размерность эмбеддинга не равна {self._dim}")
        return result

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self._passage_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return Embedder(
        s.embedding_model,
        s.embedding_dim,
        passage_prefix=s.embedding_passage_prefix,
        query_prefix=s.embedding_query_prefix,
        batch_size=s.embedding_batch_size,
    )
