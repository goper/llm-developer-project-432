-- Шаг 2. Включаем векторное расширение: образ базы должен быть pgvector/pgvector, на обычном образе команда упадёт.
CREATE EXTENSION IF NOT EXISTS vector;
