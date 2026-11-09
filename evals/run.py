"""Прогон метрик: генерация по эталонным документам, сравнение, отчёт файлом.

Запуск: make eval (набор по умолчанию из eval_defaults) или make eval FULL=1 (весь набор эталона).
Отчёт пишется в evals/reports/report-<время>.json: цифры переносятся в README.
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import ROOT_DIR
from app.core.db import init_pool
from app.llm.client import get_llm_client
from app.repositories import chunks as chunks_repo
from app.repositories import documents as documents_repo
from app.services import documents as documents_service
from app.services import pipeline, rag_pipeline
from evals.metrics import characteristic_match, citation_match, judge_support

GOLDEN = ROOT_DIR / "data" / "golden_cards.json"
REPORTS = ROOT_DIR / "evals" / "reports"

logger = logging.getLogger("evals")


def _ensure_indexed(name: str) -> str:
    content = (ROOT_DIR / "data" / name).read_bytes()
    doc = documents_service.save_upload(name, content).document
    if doc.status != "indexed":
        documents_service.parse_document(doc.id)
        doc = documents_repo.get(doc.id) or doc
    if doc.status != "indexed":
        raise RuntimeError(f"{name}: документ не проиндексирован ({doc.status}: {doc.error})")
    return doc.id


def evaluate_document(name: str, expected: dict[str, Any], llm: Any) -> dict[str, Any]:
    doc_id = _ensure_indexed(name)
    job_id = f"eval-{name}"
    hits = rag_pipeline.search_step(expected["product"], [doc_id])
    context = rag_pipeline.assemble_context(hits, llm, job_id=job_id)
    outcome = pipeline.run_card_pipeline(llm, context, expected["product"], job_id=job_id)
    card = outcome.card.model_dump()

    matched, total = characteristic_match(expected.get("characteristics", {}), card["characteristics"])
    chunk_by_id = {
        h.id: {"text": h.text, "page": h.page}
        for h in chunks_repo.get_by_ids(list(context.allowed_ids)).values()
    }
    cited, probes = citation_match(
        expected.get("source_probes", {}), card["characteristic_sources"], chunk_by_id
    )
    judged = judge_support(llm, context.render(), card, job_id=job_id)
    return {
        "document": name,
        "status": outcome.status,
        "rounds": outcome.rounds,
        "characteristics": {"matched": matched, "total": total},
        "citations": {"matched": cited, "total": probes},
        "judge_supported_share": judged,
        "protection": context.report,
    }


def _share(pairs: list[tuple[int, int]]) -> float | None:
    done = sum(t for _, t in pairs)
    return round(sum(m for m, _ in pairs) / done, 3) if done else None


def run(full: bool) -> Path:
    init_pool()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    names = list(golden["documents"]) if full else list(golden["eval_defaults"])
    llm = get_llm_client()
    rows = []
    for name in names:
        logger.info("оцениваю %s", name)
        rows.append(evaluate_document(name, golden["documents"][name], llm))

    summary = {
        "characteristics_share": _share(
            [(r["characteristics"]["matched"], r["characteristics"]["total"]) for r in rows]
        ),
        "citation_share": _share([(r["citations"]["matched"], r["citations"]["total"]) for r in rows]),
        "judge_share": (
            round(
                sum(r["judge_supported_share"] for r in rows if r["judge_supported_share"] is not None)
                / max(1, sum(1 for r in rows if r["judge_supported_share"] is not None)),
                3,
            )
        ),
    }
    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "set": "full" if full else "default",
        "documents": rows,
        "summary": summary,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"report-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="весь набор эталона")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = run(args.full)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(f"{'документ':<22}{'характеристики':>16}{'цитирование':>13}{'судья':>8}  статус")
    for r in report["documents"]:
        ch = f"{r['characteristics']['matched']}/{r['characteristics']['total']}"
        ct = f"{r['citations']['matched']}/{r['citations']['total']}"
        judge = "-" if r["judge_supported_share"] is None else f"{r['judge_supported_share']:.2f}"
        print(f"{r['document']:<22}{ch:>16}{ct:>13}{judge:>8}  {r['status']}")
    print("средние:", json.dumps(report["summary"], ensure_ascii=False))
    print(f"отчёт: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
