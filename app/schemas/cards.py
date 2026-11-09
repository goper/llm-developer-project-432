"""Контракт результата: карточка товара и ссылки на источники.

Модель данных — это то, на что приложение полагается, как на ответ своей базы.
Ответ модели проверяется этими классами до того, как с ним что-то делается.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings


class SourceRef(BaseModel):
    """Ссылка на фрагмент документа, откуда взято утверждение."""

    chunk_id: str = Field(min_length=1)
    page: int | None = None
    section: str | None = None


class Seo(BaseModel):
    title: str = Field(max_length=60)
    description: str = Field(max_length=160)
    keywords: list[str] = Field(default_factory=list, max_length=10)


class Card(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    characteristics: dict[str, str] = Field(default_factory=dict)
    # Какой фрагмент подтверждает характеристику: имя характеристики -> chunk_id.
    characteristic_sources: dict[str, str] = Field(default_factory=dict)
    benefits: list[str] = Field(default_factory=list)
    seo: Seo
    sources: list[SourceRef] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("title")
    @classmethod
    def _title_length(cls, value: str) -> str:
        limit = get_settings().title_max_length
        if len(value) > limit:
            raise ValueError(f"заголовок длиннее {limit} символов ({len(value)}), сократи его")
        return value

    @field_validator("characteristics", mode="before")
    @classmethod
    def _drop_empty(cls, value: Any) -> Any:
        # Характеристика с пустым значением в карточку не попадает.
        if isinstance(value, dict):
            return {
                str(k).strip(): str(v).strip() for k, v in value.items() if str(k).strip() and str(v).strip()
            }
        return value

    @model_validator(mode="after")
    def _field_not_in_both(self) -> "Card":
        both = set(self.characteristics) & set(self.missing_fields)
        if both:
            names = ", ".join(sorted(both))
            raise ValueError(f"поле не может быть и в характеристиках, и в недостающих: {names}")
        return self


class Fact(BaseModel):
    text: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    characteristic: str | None = None


class Facts(BaseModel):
    """Результат роли «извлечение»: факты из фрагментов со ссылками."""

    items: list[Fact] = Field(default_factory=list)


class Issue(BaseModel):
    field: str = Field(min_length=1)
    problem: str = Field(min_length=1)


class Verdict(BaseModel):
    """Результат роли «проверка»: соответствует ли черновик источникам."""

    ok: bool
    issues: list[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ok_means_no_issues(self) -> "Verdict":
        if self.ok and self.issues:
            raise ValueError("ok=true, но перечислены проблемы; верни ok=false или очисти issues")
        return self
