"""Клиент Temporal для обработчиков HTTP: старт процессов, сигналы и запросы состояния."""

from temporalio.client import Client

from app.core.config import get_settings

_client: Client | None = None


async def get_client() -> Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    return _client


def card_workflow_id(job_id: str) -> str:
    return f"card-{job_id}"


def document_workflow_id(document_id: str) -> str:
    return f"parse-{document_id}"
