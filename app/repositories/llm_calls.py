"""Таблица вызовов модели. Пишет клиент модели после каждого вызова (app/llm/client.py)."""

from dataclasses import dataclass
from decimal import Decimal

from psycopg.rows import dict_row

from app.core.db import connection


@dataclass(frozen=True)
class LlmCallRecord:
    job_id: str | None
    purpose: str
    role: str  # main | cheap
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    attempts: int
    status: str = "ok"


def insert(record: LlmCallRecord) -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO llm_calls (job_id, purpose, role, model, prompt_tokens, completion_tokens,
                                   cost_usd, latency_ms, attempts, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.job_id,
                record.purpose,
                record.role,
                record.model,
                record.prompt_tokens,
                record.completion_tokens,
                record.cost_usd,
                record.latency_ms,
                record.attempts,
                record.status,
            ),
        )


def cost_by_job(job_id: str) -> dict[str, object]:
    """Стоимость одной задачи: итог и разбивка по ролям (main / cheap)."""
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT role, count(*) AS calls, sum(prompt_tokens) AS prompt_tokens,
                   sum(completion_tokens) AS completion_tokens, sum(cost_usd) AS cost_usd
            FROM llm_calls WHERE job_id = %s GROUP BY role ORDER BY role
            """,
            (job_id,),
        )
        rows = cur.fetchall()
    total = sum((Decimal(r["cost_usd"]) for r in rows), Decimal("0"))
    return {
        "job_id": job_id,
        "total_usd": format(total, "f"),
        "by_role": [
            {
                "role": r["role"],
                "calls": r["calls"],
                "prompt_tokens": int(r["prompt_tokens"] or 0),
                "completion_tokens": int(r["completion_tokens"] or 0),
                "cost_usd": format(Decimal(r["cost_usd"]), "f"),
            }
            for r in rows
        ],
    }


def summary_by_role() -> list[dict[str, object]]:
    """Разбивка по моделям для всей таблицы: сколько вызовов и на какую сумму ушло на каждую роль."""
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT role, model, count(*) AS calls, sum(cost_usd) AS cost_usd
            FROM llm_calls GROUP BY role, model ORDER BY role, model
            """
        )
        return [
            {
                "role": r["role"],
                "model": r["model"],
                "calls": r["calls"],
                "cost_usd": format(Decimal(r["cost_usd"]), "f"),
            }
            for r in cur.fetchall()
        ]
