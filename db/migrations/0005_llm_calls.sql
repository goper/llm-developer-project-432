-- Шаг 8. Таблица вызовов модели: кто, сколько токенов, сколько стоило, сколько шло.
-- Пишет клиент модели (app/llm/client.py) после каждого вызова.
CREATE TABLE IF NOT EXISTS llm_calls (
    id                bigserial PRIMARY KEY,
    job_id            text,
    purpose           text NOT NULL,
    role              text NOT NULL,            -- main | cheap
    model             text NOT NULL,
    prompt_tokens     integer NOT NULL DEFAULT 0,
    completion_tokens integer NOT NULL DEFAULT 0,
    cost_usd          numeric(14, 8) NOT NULL DEFAULT 0,  -- деньги в numeric, не в float
    latency_ms        integer NOT NULL DEFAULT 0,
    attempts          integer NOT NULL DEFAULT 1,
    status            text NOT NULL DEFAULT 'ok',         -- ok | error
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS llm_calls_job_idx ON llm_calls (job_id);
