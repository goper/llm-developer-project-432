-- Шаг 3. Таблица задач. Статус живёт здесь, а не только в истории движка процессов.
-- idempotency_key уникален: повторный запрос с тем же ключом вернёт существующую задачу.
CREATE TABLE IF NOT EXISTS jobs (
    id              text PRIMARY KEY,
    kind            text NOT NULL,
    status          text NOT NULL,
    idempotency_key text UNIQUE,
    document_ids    text[] NOT NULL DEFAULT '{}',
    product_hint    text,
    result          jsonb,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);
