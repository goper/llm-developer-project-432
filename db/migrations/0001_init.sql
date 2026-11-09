-- Шаг 2. Векторное расширение (в образе pgvector/pgvector его собрали заранее)
-- и таблица, в которой раннер отмечает применённые миграции.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
