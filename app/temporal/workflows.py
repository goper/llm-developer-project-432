"""Процессы Temporal.

GenerateCardWorkflow: поиск -> защита и контекст -> извлечение -> генерация -> проверка -> (петля) -> финиш
-> ожидание сигнала approve/reject. Пауза на сутки в процессе ничего не стоит.
ParseDocumentWorkflow: разбор одного документа.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        NON_RETRYABLE,
        assemble_activity,
        check_activity,
        decision_activity,
        extract_activity,
        finish_activity,
        generate_activity,
        parse_document_activity,
        repair_activity,
        search_activity,
        set_job_status_activity,
    )
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

STEP_TIMEOUT = timedelta(minutes=10)
STEP_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    non_retryable_error_types=NON_RETRYABLE,
)


@workflow.defn
class GenerateCardWorkflow:
    def __init__(self) -> None:
        self._stage = "pending"
        self._decision: str | None = None

    @workflow.signal
    def approve(self) -> None:
        self._decision = "approved"

    @workflow.signal
    def reject(self) -> None:
        self._decision = "rejected"

    @workflow.query
    def state(self) -> dict[str, str | None]:
        return {"stage": self._stage, "decision": self._decision}

    async def _status(self, job_id: str, status: str, error: str | None = None) -> None:
        self._stage = status
        await workflow.execute_activity(
            set_job_status_activity,
            SetStatusInput(job_id, status, error),
            start_to_close_timeout=timedelta(seconds=30),
        )

    @workflow.run
    async def run(self, data: GenerateInput) -> str:
        job_id = data.job_id
        try:
            await self._status(job_id, "searching")
            hits = await workflow.execute_activity(
                search_activity,
                SearchInput(job_id, data.product_hint or "товар", data.document_ids),
                start_to_close_timeout=STEP_TIMEOUT,
                retry_policy=STEP_RETRY,
            )

            await self._status(job_id, "generating")
            context = await workflow.execute_activity(
                assemble_activity,
                AssembleInput(job_id, hits),
                start_to_close_timeout=STEP_TIMEOUT,
                retry_policy=STEP_RETRY,
            )
            facts = await workflow.execute_activity(
                extract_activity,
                ExtractInput(job_id, context, data.product_hint),
                start_to_close_timeout=STEP_TIMEOUT,
                retry_policy=STEP_RETRY,
            )
            card = await workflow.execute_activity(
                generate_activity,
                GenerateCardInput(job_id, context, facts, data.product_hint),
                start_to_close_timeout=STEP_TIMEOUT,
                retry_policy=STEP_RETRY,
            )

            # Петля переделки: три круга и стоп. Круги крутит процесс, вызовы внутри — клиент модели.
            rounds = 0
            problems: list[dict[str, str]] = []
            max_rounds = data.max_repair_rounds
            while True:
                await self._status(job_id, "checking")
                problems = await workflow.execute_activity(
                    check_activity,
                    CheckInput(job_id, context, card),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
                if not problems or rounds >= max_rounds:
                    break
                rounds += 1
                grouped: dict[str, str] = {}
                for p in problems:
                    grouped[p["field"]] = (grouped.get(p["field"], "") + "; " + p["problem"]).lstrip("; ")
                card = await workflow.execute_activity(
                    repair_activity,
                    RepairInput(job_id, context, card, grouped),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )

            status = await workflow.execute_activity(
                finish_activity,
                FinishInput(job_id, card, problems, rounds, context.get("report", {})),
                start_to_close_timeout=timedelta(seconds=60),
            )
        except ActivityError as exc:
            await self._status(job_id, "failed", str(exc.cause or exc))
            return "failed"

        self._stage = status
        # Ручная проверка: процесс ждёт сигнала сутками, не занимая ни потока, ни соединения.
        await workflow.wait_condition(lambda: self._decision is not None)
        await workflow.execute_activity(
            decision_activity,
            DecisionInput(job_id, self._decision or "rejected"),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._stage = self._decision or "rejected"
        return self._stage


@workflow.defn
class ParseDocumentWorkflow:
    @workflow.run
    async def run(self, document_id: str) -> str:
        return await workflow.execute_activity(
            parse_document_activity,
            document_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2, non_retryable_error_types=NON_RETRYABLE),
        )


WORKFLOWS = [GenerateCardWorkflow, ParseDocumentWorkflow]
