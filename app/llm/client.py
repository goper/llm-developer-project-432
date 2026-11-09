"""Единственная дверь к модели. Остальной код про провайдера ничего не знает.

Клиент отвечает за три вещи:
- таймаут на вызов;
- повтор вызова только на ошибках, которые повтор лечит (сеть, лимит, 5xx); ошибка в запросе повтор не лечит;
- запись в таблицу llm_calls после каждого вызова: токены из ответа, стоимость, длительность.

Повтор ШАГА процесса — дело движка Temporal; повтор ВЫЗОВА — дело этого клиента. Не путать.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal, Protocol

import openai
from agents import Runner, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from openai import OpenAI

from app.core.config import Settings, get_settings
from app.llm.cost import compute_cost, price_for
from app.repositories import llm_calls as llm_calls_repo
from app.repositories.llm_calls import LlmCallRecord

logger = logging.getLogger(__name__)

Role = Literal["main", "cheap"]

RETRIABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class LLMError(Exception):
    """Базовая ошибка вызова модели."""


class LLMUnavailableError(LLMError):
    """Модель недоступна: повторы исчерпаны.

    Вызывающий решает, что делать: детектор, например, считает фрагмент подозрительным.
    """


class LLMRequestError(LLMError):
    """Ошибка в самом запросе: повтор её не лечит."""


@dataclass(frozen=True)
class LLMReply:
    text: str
    model: str
    role: Role
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    attempts: int


class _Api(Protocol):
    chat: Any


Recorder = Callable[[LlmCallRecord], None]


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        api: _Api | None = None,
        recorder: Recorder | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings or get_settings()
        # Повторы делает наш клиент, поэтому SDK повторять не должен (иначе попытки умножаются).
        self._api = api or OpenAI(
            base_url=self._settings.llm_base_url,
            api_key=self._settings.llm_api_key,
            timeout=self._settings.llm_timeout_seconds,
            max_retries=0,
        )
        self._record = recorder or llm_calls_repo.insert
        self._sleep = sleep

    def model_name(self, role: Role) -> str:
        return self._settings.llm_cheap_model if role == "cheap" else self._settings.llm_model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str,
        job_id: str | None = None,
        cheap: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMReply:
        role: Role = "cheap" if cheap else "main"
        model = self.model_name(role)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.1}
        if json_schema is not None and self._settings.llm_structured_mode == "schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": purpose, "schema": json_schema},
            }

        max_retries = self._settings.llm_max_retries
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 2):
            try:
                response = self._api.chat.completions.create(**kwargs)
            except RETRIABLE as exc:
                last_error = exc
                if attempt > max_retries:
                    break
                delay = self._settings.llm_retry_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(
                    0, self._settings.llm_retry_base_seconds
                )  # примесь, чтобы воркеры не шли synchronно
                logger.warning("повтор вызова %s через %.1f с (попытка %d): %s", purpose, delay, attempt, exc)
                self._sleep(delay)
                continue
            except openai.APIStatusError as exc:
                # 4xx кроме лимита: ошибка в запросе или в ключе — повтор не поможет
                self._log_failure(job_id, purpose, role, model, started, attempt)
                raise LLMRequestError(f"модель отклонила запрос ({exc.status_code})") from exc

            latency_ms = int((time.perf_counter() - started) * 1000)
            text = (response.choices[0].message.content or "") if response.choices else ""
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            cost = compute_cost(prompt_tokens, completion_tokens, price_for(role, self._settings))
            self._safe_record(
                LlmCallRecord(
                    job_id=job_id,
                    purpose=purpose,
                    role=role,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    attempts=attempt,
                )
            )
            logger.info(
                "вызов %s: роль=%s токены=%d/%d стоимость=%s задержка=%d мс попыток=%d",
                purpose,
                role,
                prompt_tokens,
                completion_tokens,
                cost,
                latency_ms,
                attempt,
            )
            return LLMReply(
                text=text,
                model=model,
                role=role,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                attempts=attempt,
            )

        self._log_failure(job_id, purpose, role, model, started, max_retries + 1)
        raise LLMUnavailableError(f"модель недоступна после повторов: {type(last_error).__name__}")

    def _log_failure(
        self, job_id: str | None, purpose: str, role: Role, model: str, started: float, attempts: int
    ) -> None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        self._safe_record(
            LlmCallRecord(
                job_id=job_id,
                purpose=purpose,
                role=role,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=latency_ms,
                attempts=attempts,
                status="error",
            )
        )

    def _safe_record(self, record: LlmCallRecord) -> None:
        # Учёт не должен ронять ответ модели; но ошибку записи видно в логах.
        try:
            self._record(record)
        except Exception:
            logger.exception("не удалось записать вызов модели в таблицу llm_calls")


@lru_cache
def get_llm_client() -> LLMClient:
    """Один клиент на процесс: общий пул соединений HTTP и единая точка настроек модели."""
    return LLMClient()


# --- Асинхронный путь через OpenAI Agents SDK: агенты ролей (app/agents) зовутся через run_agent. ---

_llm_ready = False


def setup_llm() -> None:
    """Один раз на процесс: SDK агентов смотрит в наш OpenAI-совместимый сервер, трассировка выключена."""
    global _llm_ready
    if _llm_ready:
        return
    settings = get_settings()
    client = openai.AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,  # повторы делает run_agent, иначе попытки умножаются
    )
    set_default_openai_client(client, use_for_tracing=False)
    set_default_openai_api("chat_completions")  # локальные серверы знают только Chat Completions
    set_tracing_disabled(True)
    _llm_ready = True


def _retryable(exc: BaseException) -> bool:
    """Повтор лечит сеть, таймаут, лимит (429) и ошибки сервера (5xx). Ошибку в запросе (4xx) — нет."""
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return True
    if isinstance(exc, openai.APIStatusError):
        status = getattr(exc, "status_code", None)
        return status == 429 or (isinstance(status, int) and status >= 500)
    return False


async def run_agent(agent: Any, prompt: str) -> str:
    """Запуск агента роли с повтором вызова на временных ошибках. Возвращает текст финального ответа."""
    setup_llm()
    settings = get_settings()
    max_retries = settings.llm_max_retries
    started = time.perf_counter()
    for attempt in range(1, max_retries + 2):
        try:
            result = await Runner.run(agent, prompt)
        except Exception as exc:
            if not _retryable(exc) or attempt > max_retries:
                raise
            delay = settings.llm_retry_base_seconds * (2 ** (attempt - 1))
            logger.warning(
                "повтор агента %s через %.1f с (попытка %d): %s", _agent_name(agent), delay, attempt, exc
            )
            await asyncio.sleep(delay)
            continue
        _record_agent_usage(agent, result, started, attempt)
        output = result.final_output
        if isinstance(output, str):
            return output
        if hasattr(output, "model_dump_json"):
            return output.model_dump_json()
        return str(output)
    raise LLMUnavailableError("модель недоступна после повторов")  # сюда не дойдём: выход в цикле


def _agent_name(agent: Any) -> str:
    return str(getattr(agent, "name", "agent"))


def _record_agent_usage(agent: Any, result: Any, started: float, attempts: int) -> None:
    """Токены и стоимость вызова агента — в llm_calls. Нет данных об использовании — не пишем."""
    usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
    if usage is None:
        return
    settings = get_settings()
    model = str(getattr(agent, "model", "") or settings.llm_model)
    role: Role = "cheap" if model == settings.llm_cheap_model else "main"
    prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    record = LlmCallRecord(
        job_id=None,
        purpose=_agent_name(agent),
        role=role,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=compute_cost(prompt_tokens, completion_tokens, price_for(role, settings)),
        latency_ms=int((time.perf_counter() - started) * 1000),
        attempts=attempts,
    )
    try:
        llm_calls_repo.insert(record)
    except Exception:
        logger.exception("не удалось записать вызов агента в таблицу llm_calls")
