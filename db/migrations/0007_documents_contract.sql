-- Документы: имена колонок из контракта практики.
-- sha256 -> content_hash (хэш содержимого, по нему повторная загрузка не создаёт дубля),
-- kind — формат файла (pdf | docx | xlsx), размер необязателен для записей, созданных не загрузкой.
ALTER TABLE documents RENAME COLUMN sha256 TO content_hash;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS kind text;
ALTER TABLE documents ALTER COLUMN size_bytes SET DEFAULT 0;
UPDATE documents SET kind = lower(substring(filename from '\.([^.]+)$')) WHERE kind IS NULL;
