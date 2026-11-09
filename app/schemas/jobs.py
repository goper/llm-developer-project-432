"""Формы ответов API для задач и документов."""

from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    product_hint: str | None = Field(default=None, max_length=200)


class CardTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    product_hint: str | None = Field(default=None, max_length=200)


class JobCreated(BaseModel):
    job_id: str
    status: str


class JobView(BaseModel):
    job_id: str
    kind: str
    status: str
    document_ids: list[str]
    result: dict[str, Any] | None = None
    error: str | None = None
    cost: dict[str, Any] | None = None


class DocumentCreated(BaseModel):
    document_id: str
    status: str


class DocumentView(BaseModel):
    document_id: str
    filename: str
    status: str
    error: str | None = None
    chunks_count: int
