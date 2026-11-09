-- Шаг 6. Поиск: векторная колонка и колонка для поиска по словам.
-- Метрика — косинусная; индекс hnsw строится под неё и дальше не меняется.
-- Размерность 384 соответствует intfloat/multilingual-e5-small (см. EMBEDDING_DIM в .env.example).
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(384);

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('russian', coalesce(sku, '') || ' ' || text)) STORED;

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin_idx ON chunks USING gin (tsv);
