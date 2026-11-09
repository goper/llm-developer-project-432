"""Процесс генерации в тестовом окружении Temporal: активности подменены, модели нет.

Проверяем: успех ждёт подтверждения и доходит до approved; петля переделки ограничена тремя кругами;
сигнал отказа завершает процесс отказом.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.config import get_settings
from app.temporal.payloads import (
    AssembleInput,
    CheckInput,
    DecisionInput,
    ExtractInput,
    FinishInput,
    GenerateCardInput,
    GenerateInput,
    RepairInput,
    SearchInput,
    SetStatusInput,
)
from app.temporal.workflows import GenerateCardWorkflow

CARD = {
    "title": "Блендер",
    "description": "",
    "characteristics": {"мощность": "800 Вт"},
    "characteristic_sources": {},
    "benefits": [],
    "seo": {"title": "t", "description": "d", "keywords": []},
    "sources": [],
    "missing_fields": [],
    "confidence": 0.9,
}


class Calls:
    def __init__(self, problems_rounds: int) -> None:
        self.check = 0
        self.repair = 0
        self.finish_rounds: int | None = None
        self.problems_rounds = problems_rounds


def make_stubs(calls: Calls) -> list[Any]:
    @activity.defn(name="set_job_status_activity")
    def set_status(data: SetStatusInput) -> None:
        return None

    @activity.defn(name="search_activity")
    def search(data: SearchInput) -> list[dict[str, Any]]:
        return []

    @activity.defn(name="assemble_activity")
    def assemble(data: AssembleInput) -> dict[str, Any]:
        return {"items": [], "report": {}}

    @activity.defn(name="extract_activity")
    def extract(data: ExtractInput) -> dict[str, Any]:
        return {"items": []}

    @activity.defn(name="generate_activity")
    def generate(data: GenerateCardInput) -> dict[str, Any]:
        return CARD

    @activity.defn(name="check_activity")
    def check(data: CheckInput) -> list[dict[str, str]]:
        calls.check += 1
        if calls.check <= calls.problems_rounds:
            return [{"field": "sources", "problem": "ссылка вне контекста"}]
        return []

    @activity.defn(name="repair_activity")
    def repair(data: RepairInput) -> dict[str, Any]:
        calls.repair += 1
        return CARD

    @activity.defn(name="finish_activity")
    def finish(data: FinishInput) -> str:
        calls.finish_rounds = data.rounds
        return "waiting_approval" if not data.problems else "needs_review"

    @activity.defn(name="decision_activity")
    def decision(data: DecisionInput) -> None:
        return None

    return [set_status, search, assemble, extract, generate, check, repair, finish, decision]


async def _run(calls: Calls, signal: str) -> str:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"test-{uuid.uuid4().hex[:8]}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[GenerateCardWorkflow],
            activities=make_stubs(calls),
            activity_executor=ThreadPoolExecutor(max_workers=4),
        ):
            handle = await env.client.start_workflow(
                GenerateCardWorkflow.run,
                GenerateInput(
                    job_id="job1",
                    document_ids=["d1"],
                    product_hint="блендер",
                    max_repair_rounds=get_settings().max_repair_rounds,
                ),
                id=f"card-{uuid.uuid4().hex[:8]}",
                task_queue=task_queue,
            )
            # Ждём, пока процесс дойдёт до ручной проверки (стадия не «searching»/«checking»).
            for _ in range(600):
                state = await handle.query(GenerateCardWorkflow.state)
                if state["stage"] in ("waiting_approval", "needs_review"):
                    break
                await asyncio.sleep(0.05)
            assert state["stage"] in ("waiting_approval", "needs_review"), state
            if signal == "approve":
                await handle.signal(GenerateCardWorkflow.approve)
            else:
                await handle.signal(GenerateCardWorkflow.reject)
            return await handle.result()


@pytest.mark.slow
def test_success_waits_then_approved() -> None:
    calls = Calls(problems_rounds=0)
    try:
        result = asyncio.run(_run(calls, "approve"))
    except RuntimeError as exc:  # тестовый сервер Temporal не скачан (нет сети)
        pytest.skip(f"тестовое окружение Temporal недоступно: {exc}")
    assert result == "approved"
    assert calls.repair == 0


@pytest.mark.slow
def test_repair_loop_is_bounded_and_reject_ends_process() -> None:
    calls = Calls(problems_rounds=10**6)  # проверка всегда недовольна
    try:
        result = asyncio.run(_run(calls, "reject"))
    except RuntimeError as exc:
        pytest.skip(f"тестовое окружение Temporal недоступно: {exc}")
    limit = get_settings().max_repair_rounds
    assert calls.repair == limit
    assert calls.check == limit + 1
    assert calls.finish_rounds == limit
    assert result == "rejected"
