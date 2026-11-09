-- Фрагменты ссылаются на документ полем doc_id (имя из контракта практики).
-- Внешний ключ снимаем: фрагменты можно загрузить в индекс и без строки в documents
-- (например, тестовый набор); удаление фрагментов документа делает код (replace_chunks).
-- Уникальность (документ, позиция) заменяем обычным индексом, у служебных колонок — значения по умолчанию.
ALTER TABLE chunks RENAME COLUMN document_id TO doc_id;
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_document_id_fkey;
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_document_id_position_key;
ALTER TABLE chunks ALTER COLUMN id SET DEFAULT md5(random()::text || clock_timestamp()::text);
ALTER TABLE chunks ALTER COLUMN position SET DEFAULT 0;
ALTER INDEX IF EXISTS chunks_document_idx RENAME TO chunks_doc_idx;
CREATE INDEX IF NOT EXISTS chunks_doc_position_idx ON chunks (doc_id, position);
