"""Документы: загрузка, разбор, нормализация, резка, сохранение фрагментов.

Состояния документа: new -> parsing -> indexing -> indexed | failed.
Отказ с причиной — нормальный исход (например, скан без текстового слоя), а не пустой результат.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.parsers.chunker import chunk_blocks, chunk_id_for
from app.parsers.docx import parse_docx
from app.parsers.pdf import parse_pdf
from app.parsers.types import Chunk, ParseError, Source, Unit
from app.parsers.xlsx import parse_xlsx
from app.rag.reindex import reindex
from app.repositories import chunks as chunks_repo
from app.repositories import documents as documents_repo
from app.repositories.chunks import ChunkRow
from app.repositories.documents import Document

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
PARSERS = {".pdf": parse_pdf, ".docx": parse_docx, ".xlsx": parse_xlsx}


class UploadError(ValueError):
    """Файл не принят: расширение или размер."""


@dataclass(frozen=True)
class UploadResult:
    document: Document
    created: bool


def save_upload(filename: str, content: bytes) -> UploadResult:
    settings = get_settings()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError(f"расширение {ext or '—'} не поддерживается: нужен pdf, docx или xlsx")
    if not content:
        raise UploadError("файл пустой")
    if len(content) > settings.max_upload_bytes:
        raise UploadError(f"файл больше {settings.max_upload_bytes // (1024 * 1024)} МБ")
    digest = hashlib.sha256(content).hexdigest()
    doc, created = documents_repo.create_or_get(sha256=digest, filename=filename, size_bytes=len(content))
    if created:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        (settings.upload_dir / f"{digest}{ext}").write_bytes(content)
    return UploadResult(doc, created)


def source_path(doc: Document) -> Path:
    ext = Path(doc.filename).suffix.lower()
    return get_settings().upload_dir / f"{doc.sha256}{ext}"


def _chunk_id(document_id: str, position: int) -> str:
    return chunk_id_for(document_id, position)


def parse_to_chunks(
    source: Source,
    ext: str | None = None,
    doc_id: str | None = None,
    *,
    size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """Разбор файла до фрагментов, без базы: парсер по расширению, нормализация, резка.

    source — путь или содержимое файла байтами (тогда ext обязателен: "pdf" или ".pdf").
    Если передан doc_id, у фрагментов заполнены doc_id и chunk_id.
    Скан без текстового слоя и пустой документ дают ParseError с причиной, а не пустой список.
    """
    settings = get_settings()
    kind = (ext or (Path(source).suffix if isinstance(source, str | Path) else "")).lower()
    if kind and not kind.startswith("."):
        kind = f".{kind}"
    if kind not in PARSERS:
        raise ParseError(f"формат {kind or '—'} не поддерживается: нужен pdf, docx или xlsx")
    units: list[Unit] = PARSERS[kind](source)
    if not units:
        raise ParseError("в документе не нашлось текста")
    return chunk_blocks(
        units,
        doc_id,
        size=size or settings.chunk_size,
        overlap=settings.chunk_overlap if overlap is None else overlap,
    )


def parse_document(doc_id: str) -> str:
    """Шаг процесса разбора. Возвращает итоговый статус документа."""
    doc = documents_repo.get(doc_id)
    if doc is None:
        raise LookupError(f"документ {doc_id} не найден")
    documents_repo.set_status(doc_id, "parsing")
    ext = Path(doc.filename).suffix.lower()
    try:
        drafts = parse_to_chunks(source_path(doc), ext, doc_id)
    except ParseError as exc:
        documents_repo.set_status(doc_id, "failed", str(exc))
        logger.warning("документ %s не разобран: %s", doc_id, exc)
        return "failed"

    rows = [
        ChunkRow(
            id=c.chunk_id or _chunk_id(doc_id, c.position),
            document_id=doc_id,
            position=c.position,
            page=c.page,
            section=c.section,
            kind=c.kind,
            sku=c.sku,
            brand=None,
            text=c.text,
        )
        for c in drafts
    ]
    chunks_repo.replace_chunks(doc_id, rows)
    documents_repo.set_status(doc_id, "indexing")
    reindex(document_id=doc_id)
    documents_repo.set_status(doc_id, "indexed")
    logger.info("документ %s проиндексирован: фрагментов=%d", doc_id, len(rows))
    return "indexed"
