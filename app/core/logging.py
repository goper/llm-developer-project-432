"""Логи с идентификаторами запроса и задачи.

request_id рождается в промежуточном слое HTTP, job_id — при создании задачи и передаётся аргументом процесса.
Оба попадают в каждую строку лога через contextvars, поэтому поиск по job_id показывает весь путь задачи.
"""

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import get_settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="-")


class ContextFilter(logging.Filter):
    """Добавляет request_id и job_id в каждую запись."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.job_id = job_id_var.get()
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s req=%(request_id)s job=%(job_id)s %(name)s: %(message)s")
    )
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(get_settings().log_level)


@contextmanager
def bind_job(job_id: str) -> Iterator[None]:
    """Привязывает job_id к текущему контексту (воркер и обработчики)."""
    token = job_id_var.set(job_id)
    try:
        yield
    finally:
        job_id_var.reset(token)


def get_logger(name: str) -> logging.Logger:
    """Логгер модуля; request_id и job_id добавляет фильтр корневого обработчика."""
    return logging.getLogger(name)
