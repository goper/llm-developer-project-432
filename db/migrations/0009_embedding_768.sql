-- Модель эмбеддингов: intfloat/multilingual-e5-base, размерность 768 (была e5-small, 384).
-- Векторы старой модели с новыми несравнимы, поэтому они обнуляются: make reindex досчитает заново.
-- Индекс hnsw строится под тип колонки, его пересоздаём.
DROP INDEX IF EXISTS chunks_embedding_hnsw_idx;
UPDATE chunks SET embedding = NULL WHERE embedding IS NOT NULL;
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops);
