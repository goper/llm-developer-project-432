"""Досчёт векторов фрагментам, у которых их нет. Повторный запуск без новых фрагментов ничего не делает."""

import logging
import sys

from app.core.db import init_pool
from app.rag.embedder import Embedder, get_embedder
from app.repositories import chunks as chunks_repo

logger = logging.getLogger(__name__)


def reindex(*, batch_size: int = 64, embedder: Embedder | None = None, document_id: str | None = None) -> int:
    emb = embedder or get_embedder()
    total = chunks_repo.count_without_embedding(document_id)
    if total == 0:
        logger.info("векторы уже есть у всех фрагментов")
        return 0
    done = 0
    while True:
        rows = chunks_repo.list_without_embedding(batch_size, document_id)
        if not rows:
            break
        texts = [text for _, text, _ in rows]
        vectors = emb.embed_passages(texts)
        chunks_repo.set_embeddings([(row[0], vec) for row, vec in zip(rows, vectors, strict=True)])
        done += len(rows)
        logger.info("досчитано векторов: %d из %d", done, total)
    return done


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    init_pool()
    count = reindex()
    print(f"Досчитано векторов: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
