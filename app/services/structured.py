"""Валидация с лечением и точечная переделка.

Невалидный ответ не отдаём как ошибку сервера: возвращаем его модели вместе с текстом ошибки.
Если сломалось одно поле — переделываем только его, передав текущий черновик.
Число попыток ограничено: лечение дороже генерации, если его не ограничить.
"""

import logging
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.agents.prompts import repair_messages, schema_text
from app.core.config import get_settings
from app.llm.client import run_agent
from app.services.json_utils import JsonReplyError, parse_json_reply

logger = logging.getLogger(__name__)


class StructuredError(Exception):
    """Модель не дала валидный ответ за отведённое число попыток."""


class CardValidationError(StructuredError):
    """Асинхронный путь: ответ агента так и не прошёл схему после всех исправлений."""


class ChatReply(Protocol):
    text: str


class ChatLike(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str,
        job_id: str | None = None,
        cheap: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatReply: ...


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "ответ"
            parts.append(f"{where}: {err['msg']}")
        return "; ".join(parts)
    return str(exc)


def _top_fields(exc: ValidationError) -> dict[str, str]:
    """Сопоставляем ошибки с верхнеуровневыми полями. Пусто, если привязать нельзя."""
    problems: dict[str, str] = {}
    for err in exc.errors():
        if not err["loc"]:
            return {}
        field = str(err["loc"][0])
        problems[field] = (problems.get(field, "") + "; " if field in problems else "") + err["msg"]
    return problems


def generate_model[T: BaseModel](
    llm: ChatLike,
    messages: list[dict[str, str]],
    model_cls: type[T],
    *,
    purpose: str,
    job_id: str | None = None,
    fragments_text: str = "",
    max_attempts: int | None = None,
) -> T:
    """Просит модель ответ по схеме, лечит невалидный ответ и возвращает проверенный объект."""
    settings = get_settings()
    attempts = max_attempts or settings.max_structured_attempts
    convo = _with_schema(messages, model_cls)
    json_schema = model_cls.model_json_schema()
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        reply = llm.chat(convo, purpose=purpose, job_id=job_id, json_schema=json_schema)
        try:
            data = parse_json_reply(reply.text)
            return model_cls.model_validate(data)
        except JsonReplyError as exc:
            last_error = exc
            feedback = f"Ответ не разобрать как JSON: {exc}. Верни только JSON."
            convo = [
                *convo,
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": feedback},
            ]
        except ValidationError as exc:
            last_error = exc
            problems = _top_fields(exc)
            if problems and isinstance(data, dict) and attempt < attempts:
                # Точечная переделка: меняем только сломанные поля, остальное берём из черновика.
                data = _repair_fields(
                    llm, data, problems, model_cls, job_id=job_id, fragments_text=fragments_text
                )
                try:
                    return model_cls.model_validate(data)
                except ValidationError as again:
                    last_error = again
                    problems = _top_fields(again) or {"ответ": _describe(again)}
            feedback = f"Ответ не прошёл проверку: {_describe(last_error)}. Исправь и верни JSON целиком."
            convo = [
                *convo,
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": feedback},
            ]
        logger.warning("попытка %d/%d для %s не прошла проверку: %s", attempt, attempts, purpose, last_error)

    raise StructuredError(f"модель не дала валидный ответ за {attempts} попыток: {_describe(last_error)}")


def _with_schema(messages: list[dict[str, str]], model_cls: type[BaseModel]) -> list[dict[str, str]]:
    """Режим prompt: схему дублируем текстом в инструкции. В режиме schema она уходит в запрос."""
    if get_settings().llm_structured_mode != "prompt":
        return list(messages)
    note = "\n\nОтвет строго по этой JSON-схеме:\n" + schema_text(model_cls)
    out = [dict(m) for m in messages]
    out[0]["content"] = out[0]["content"] + note
    return out


def _repair_fields(
    llm: ChatLike,
    draft: dict[str, Any],
    problems: dict[str, str],
    model_cls: type[BaseModel],
    *,
    job_id: str | None,
    fragments_text: str,
) -> dict[str, Any]:
    """Переделывает перечисленные поля. Остальной черновик не трогаем."""
    field_schema = _fields_schema(model_cls, list(problems))
    messages = repair_messages(_dump(draft), problems, fragments_text, field_schema)
    reply = llm.chat(messages, purpose="repair_field", job_id=job_id)
    try:
        payload = parse_json_reply(reply.text)
    except JsonReplyError:
        logger.warning("точечная переделка не вернула JSON; оставляем черновик как есть")
        return draft
    fields = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(fields, dict):
        return draft
    fixed = dict(draft)
    for name in problems:
        if name in fields:
            fixed[name] = fields[name]
    return fixed


def _fields_schema(model_cls: type[BaseModel], names: list[str]) -> str:
    props = model_cls.model_json_schema().get("properties", {})
    picked = {name: props[name] for name in names if name in props}
    import json

    return json.dumps(picked, ensure_ascii=False, indent=2)


def _dump(draft: dict[str, Any]) -> str:
    import json

    return json.dumps(draft, ensure_ascii=False, indent=2)


def repair_fields[T: BaseModel](
    llm: ChatLike,
    draft: dict[str, Any],
    problems: dict[str, str],
    model_cls: type[T],
    *,
    job_id: str | None,
    fragments_text: str,
) -> dict[str, Any]:
    """Публичная точечная переделка для петли проверки пайплайна."""
    return _repair_fields(llm, draft, problems, model_cls, job_id=job_id, fragments_text=fragments_text)


# --- Асинхронный путь через агентов ролей (run_agent). ---


async def validate_or_retry[T: BaseModel](
    prompt: str,
    agent: Any | None = None,
    model_cls: type[T] | None = None,
    *,
    max_attempts: int | None = None,
) -> T:
    """Ответ агента проверяется схемой; ошибка проверки уходит обратно агенту.

    По умолчанию агент генерации и схема CardDraft. Всего max_attempts попыток (по умолчанию 3:
    первая и два исправления). Если все мимо — CardValidationError: невалидный ответ дальше не идёт.
    """
    if model_cls is None:
        from app.schemas.cards import CardDraft

        model_cls = CardDraft  # type: ignore[assignment]
    if agent is None:
        from app.agents.roles import generate_agent

        agent = generate_agent()
    attempts = max_attempts or get_settings().max_structured_attempts
    current = prompt
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        raw = await run_agent(agent, current)
        try:
            return model_cls.model_validate(parse_json_reply(raw))
        except (JsonReplyError, ValidationError) as exc:
            last_error = exc
            logger.warning("попытка %d/%d: ответ агента не прошёл проверку: %s", attempt, attempts, exc)
            current = (
                f"{prompt}\n\nТвой прошлый ответ не прошёл проверку: {_describe(exc)}\n"
                "Исправь ошибки и верни JSON целиком, без пояснений."
            )
    raise CardValidationError(
        f"ответ не прошёл проверку за {attempts} попыток: {_describe(last_error)}"
    ) from last_error


async def regenerate_field[T: BaseModel](
    agent: Any, card: T, field: str, problem: str = "", context: str = ""
) -> T:
    """Точечная переделка: агент переписывает одно поле, остальные поля карточки не меняются."""
    if isinstance(agent, BaseModel):  # допускаем порядок (card, field, problem, agent)
        agent, card, field, problem = problem, agent, card, field  # type: ignore[assignment]
    prompt = (
        f"Исправь в карточке только поле «{field}» (field: {field}). "
        f"Проблема: {problem or 'не прошло проверку'}. Остальные поля не меняй.\n"
        f'Верни JSON {{"{field}": новое значение}} или карточку целиком.\n\n'
        f"КАРТОЧКА:\n{card.model_dump_json()}"
    )
    if context:
        prompt += f"\n\nФРАГМЕНТЫ:\n{context}"
    raw = await run_agent(agent, prompt)
    data = parse_json_reply(raw)
    value = data.get(field, data.get("value")) if isinstance(data, dict) else data
    if isinstance(data, dict) and "fields" in data and isinstance(data["fields"], dict):
        value = data["fields"].get(field, value)
    return type(card).model_validate({**card.model_dump(), field: value})


def confidence_gate(card: Any, threshold: float | None = None) -> str:
    """Низкая уверенность — карточку ждёт человек (needs_review), иначе — обычное подтверждение."""
    limit = get_settings().confidence_threshold if threshold is None else threshold
    confidence = card.get("confidence", 0) if isinstance(card, dict) else getattr(card, "confidence", 0)
    return "needs_review" if float(confidence or 0) < limit else "done"
