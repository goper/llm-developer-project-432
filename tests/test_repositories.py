"""Репозитории и поиск на живой базе. Векторы задаём руками: модель эмбеддингов не грузится."""

import pytest

from app.repositories import chunks as chunks_repo
from app.repositories import documents as documents_repo
from app.repositories import jobs as jobs_repo
from app.repositories.chunks import ChunkRow

pytestmark = pytest.mark.db
DIM = 768


def unit(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def mix(*pairs: tuple[int, float]) -> list[float]:
    v = [0.0] * DIM
    for i, w in pairs:
        v[i] = w
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


def make_doc(name: str, sha: str) -> str:
    doc, _ = documents_repo.create_or_get(sha256=sha, filename=name, size_bytes=10)
    return doc.id


def test_job_idempotency_key_returns_same_job(clean_db: str) -> None:
    first, created1 = jobs_repo.create_job(
        kind="generate_card", document_ids=["a"], product_hint=None, idempotency_key="k-1"
    )
    second, created2 = jobs_repo.create_job(
        kind="generate_card", document_ids=["a"], product_hint=None, idempotency_key="k-1"
    )
    assert created1 is True
    assert created2 is False
    assert second.id == first.id


def test_job_status_changes_and_result_saved(clean_db: str) -> None:
    job, _ = jobs_repo.create_job(
        kind="generate_card", document_ids=[], product_hint="x", idempotency_key=None
    )
    jobs_repo.set_status(job.id, "searching")
    assert jobs_repo.get_job(job.id).status == "searching"
    jobs_repo.save_result(job.id, {"card": {"title": "t"}}, "waiting_approval")
    saved = jobs_repo.get_job(job.id)
    assert saved.status == "waiting_approval"
    assert saved.result == {"card": {"title": "t"}}


def test_document_upload_is_idempotent_by_hash(clean_db: str) -> None:
    a, created_a = documents_repo.create_or_get(sha256="h1", filename="a.pdf", size_bytes=3)
    b, created_b = documents_repo.create_or_get(sha256="h1", filename="a.pdf", size_bytes=3)
    assert created_a and not created_b
    assert a.id == b.id


def test_vector_text_and_hybrid_search(clean_db: str) -> None:
    doc = make_doc("spec.xlsx", "h2")
    rows = [
        ChunkRow("c-blender", doc, 0, 1, "Характеристики", "text", None, None, "Мощность блендера 800 Вт"),
        ChunkRow(
            "c-article", doc, 1, None, "Спецификация", "row", "KTL-1700", None, "KTL-1700: мощность 2200 Вт"
        ),
        ChunkRow("c-other", doc, 2, None, None, "text", None, None, "Гарантия два года"),
    ]
    chunks_repo.replace_chunks(doc, rows)
    chunks_repo.set_embeddings(
        [
            ("c-blender", unit(0)),  # смысл «мощность»
            ("c-article", unit(1)),  # артикул: по смыслу далеко от запроса
            ("c-other", unit(2)),
        ]
    )

    # Запрос по смыслу: вектор ближе всего к c-blender.
    query = mix((0, 0.95), (3, 0.05))
    vec_hits = chunks_repo.search_vector(None, "блендер", 5, threshold=0.5, vector=query)
    assert [h.id for h in vec_hits] == ["c-blender"]

    # Порог отсекает слабые совпадения.
    assert chunks_repo.search_vector(None, "мусор", 5, threshold=0.5, vector=unit(5)) == []

    # Поиск по словам находит артикул буква в букву, хотя вектор далёк.
    text_hits = chunks_repo.search_fts(None, "KTL-1700", 5)
    assert [h.id for h in text_hits] == ["c-article"]

    # Гибрид: объединение обоих списков; фрагмент, найденный обоими, выше.
    both = chunks_repo.search_hybrid(
        None, "мощность", 5, threshold=0.5, rrf_k=60, vector=mix((0, 1.0), (1, 0.6))
    )
    ids = [h.id for h in both]
    assert "c-blender" in ids and "c-article" in ids
    assert ids[0] == "c-blender"


def test_hybrid_fuses_by_rank_not_score(clean_db: str) -> None:
    doc = make_doc("r.docx", "h3")
    chunks_repo.replace_chunks(
        doc,
        [
            ChunkRow("r1", doc, 0, None, None, "text", None, None, "слово альфа"),
            ChunkRow("r2", doc, 1, None, None, "text", None, None, "слово бета"),
        ],
    )
    chunks_repo.set_embeddings([("r1", unit(0)), ("r2", unit(1))])
    hits = chunks_repo.search_hybrid(None, "альфа", 5, threshold=0.5, rrf_k=60, vector=unit(1))
    scores = {h.id: h.score for h in hits}
    # r1 найден только словами (ранг 1), r2 только вектором (ранг 1): вклады равны, порядок стабилен по сумме.
    assert set(scores) == {"r1", "r2"}
    assert abs(scores["r1"] - scores["r2"]) < 1e-9


def test_reindex_is_empty_on_second_run(clean_db: str) -> None:
    from app.rag.reindex import reindex

    class StubEmbedder:
        def embed_passages(self, texts: list[str]) -> list[list[float]]:
            return [unit(0) for _ in texts]

    doc = make_doc("n.pdf", "h4")
    chunks_repo.replace_chunks(doc, [ChunkRow("n1", doc, 0, 1, None, "text", None, None, "текст")])
    assert reindex(embedder=StubEmbedder()) == 1  # type: ignore[arg-type]
    assert reindex(embedder=StubEmbedder()) == 0  # type: ignore[arg-type]
