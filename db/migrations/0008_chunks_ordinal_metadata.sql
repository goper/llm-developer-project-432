-- Фрагменты: порядковый номер в документе называется ordinal, метаданные — в jsonb.
-- metadata дублирует страницу/секцию/артикул для выдачи в контекст и позволяет хранить
-- то, для чего отдельной колонки нет. Колонки page/section/sku остаются для фильтров и поиска.
ALTER TABLE chunks RENAME COLUMN position TO ordinal;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
DROP INDEX IF EXISTS chunks_doc_position_idx;
CREATE INDEX IF NOT EXISTS chunks_doc_ordinal_idx ON chunks (doc_id, ordinal);
UPDATE chunks
   SET metadata = jsonb_strip_nulls(jsonb_build_object(
       'doc_id', doc_id, 'page', page, 'section', section, 'kind', kind, 'articul', sku))
 WHERE metadata = '{}'::jsonb;
