-- Шаг 5. Документы поставщиков и их фрагменты.
-- sha256 уникален: повторная загрузка того же файла не создаёт дубля.
CREATE TABLE IF NOT EXISTS documents (
    id          text PRIMARY KEY,
    sha256      text NOT NULL UNIQUE,
    filename    text NOT NULL,
    size_bytes  integer NOT NULL,
    status      text NOT NULL,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    position    integer NOT NULL,
    page        integer,
    section     text,
    kind        text NOT NULL DEFAULT 'text',
    sku         text,
    brand       text,
    text        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, position)
);

CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);
