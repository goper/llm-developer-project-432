"""Калибровка порога релевантности: близость лучших фрагментов для верных и мусорных запросов.

Без базы: пять документов из data/ режутся тем же кодом, что и при загрузке, векторы считаются
в памяти той моделью, что в настройках. Запуск: `uv run python -m evals.calibrate`.
Результат переносится в docs/decisions/0003-relevance-threshold.md.
"""

from pathlib import Path

from app.core.config import get_settings
from app.parsers.types import ParseError
from app.rag.embedder import get_embedder
from app.services.documents import parse_to_chunks

DATA = Path(__file__).resolve().parents[1] / "data"

QUERIES = [
    ("Какая мощность у блендера", "верный"),
    ("мотор 800 Вт", "верный"),
    ("гарантия на блендер", "верный"),
    ("объём чайника", "верный"),
    ("цена BLD-800", "верный"),
    ("KTL-1700", "артикул"),
    ("рецепт борща", "мусор"),
    ("курс доллара на завтра", "мусор"),
    ("ремонт автомобиля", "мусор"),
]


def main() -> None:
    texts: list[str] = []
    for path in sorted(DATA.glob("*")):
        if path.suffix.lower() not in {".pdf", ".docx", ".xlsx"}:
            continue
        try:
            texts += [c.text for c in parse_to_chunks(path)]
        except ParseError as exc:
            print(f"# {path.name}: пропущен ({exc})")
    embedder = get_embedder()
    passages = embedder.embed_passages(texts)
    print(f"# модель {get_settings().embedding_model}, фрагментов {len(texts)}")
    print("| Запрос | Вид | Лучший | 2-й | 3-й |")
    print("| --- | --- | --- | --- | --- |")
    for query, kind in QUERIES:
        q = embedder.embed_query(query)
        scores = sorted((sum(a * b for a, b in zip(q, p, strict=True)) for p in passages), reverse=True)
        top = " | ".join(f"{s:.3f}" for s in scores[:3])
        print(f"| {query} | {kind} | {top} |")


if __name__ == "__main__":
    main()
