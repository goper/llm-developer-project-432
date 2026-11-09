# ИИ-генератор карточки товара

[![hexlet-check](https://github.com/goper/llm-developer-project-432/actions/workflows/hexlet-check.yml/badge.svg)](https://github.com/goper/llm-developer-project-432/actions)

Бэкенд-сервис, который принимает документы поставщиков (pdf, docx, xlsx), строит по ним поисковый индекс
и просит языковую модель собрать черновик карточки товара. Каждая характеристика ссылается на фрагмент
документа, откуда взята; чего в документах нет, попадает в список недостающих полей, а не выдумывается.

Учебный проект Хекслета: https://ru.hexlet.io/programs/llm-developer (проект 432).

## Стек

Python 3.12, FastAPI, Pydantic, PostgreSQL 17 + pgvector, Temporal, локальные эмбеддинги
sentence-transformers (`intfloat/multilingual-e5-small`), модель по OpenAI-совместимому API
(LM Studio, Ollama или OpenRouter). Зависимости — [uv](https://docs.astral.sh/uv/) и `uv.lock`.

## Запуск с нуля

Нужны Docker с Compose, make, uv и сервер модели с OpenAI-совместимым API.

```bash
git clone https://github.com/goper/llm-developer-project-432.git
cd llm-developer-project-432
cp .env.example .env   # адрес модели и имена моделей поправьте под свой сервер
make install           # зависимости из uv.lock (torch — CPU-сборка)
make up                # PostgreSQL с pgvector и Temporal; ждёт healthy
make migrate           # первый запуск: «Миграция применена: …», второй: «Новых миграций нет»
make worker            # в отдельном терминале: воркер процессов Temporal
make dev               # в отдельном терминале: HTTP API на http://localhost:8000
```

Модель эмбеддингов (~470 МБ) скачивается при первом разборе документа и кэшируется в `~/.cache/huggingface`.

Порты по умолчанию: база **5434**, Temporal **7234**, веб-интерфейс Temporal **http://localhost:8234**.
Они нарочно не стандартные, чтобы не спорить с другими Postgres и Temporal на машине. Переопределить:
`DB_PORT=5440 TEMPORAL_PORT=7240 make up` и те же порты в `DATABASE_URL` / `TEMPORAL_ADDRESS` в `.env`.

Модель. Пример для Ollama: `ollama pull qwen2.5:14b && ollama pull qwen2.5:7b`, затем в `.env`:
`LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen2.5:14b`, `LLM_CHEAP_MODEL=qwen2.5:7b`.
Если сервер поддерживает строгий режим JSON-схем, поставьте `LLM_STRUCTURED_MODE=schema`.

Полный сброс состояния: `make clean-volumes` (удаляет тома базы и Temporal).

## Проверка

```bash
curl localhost:8000/health/live     # {"status":"ok"} — пока процесс жив, даже без базы
curl localhost:8000/health/ready    # {"status":"ok","vector":"0.8.7"}; без базы — 503

# Загрузка: 202 и идентификатор; повторная загрузка того же файла вернёт тот же документ
curl -F file=@data/blender_passport.pdf localhost:8000/documents/
curl localhost:8000/documents/<document_id>   # status: new → parsing → indexing → indexed | failed, chunks_count

# Генерация: 202 и идентификатор задачи; тот же Idempotency-Key вернёт ту же задачу
curl -X POST localhost:8000/generate-card -H 'Content-Type: application/json' \
     -H 'Idempotency-Key: blender-1' -d '{"document_ids":["<document_id>"],"product_hint":"блендер"}'
curl localhost:8000/jobs/<job_id>             # статус, карточка, отчёт защиты, стоимость

# Ручная проверка карточки
curl localhost:8000/workflows/<job_id>/state
curl -X POST localhost:8000/workflows/<job_id>/approve    # или /reject

# Синхронно, по тексту (без документов и поиска)
curl -X POST localhost:8000/cards -H 'Content-Type: application/json' -d '{"text":"Блендер 800 Вт, чаша 1,5 л"}'
```

Состояния задачи: `pending → searching → generating → checking → waiting_approval | needs_review →
approved | rejected`, при ошибке шага — `failed` с причиной. `needs_review` — уверенность ниже
`CONFIDENCE_THRESHOLD` или проблемы, оставшиеся после трёх кругов переделки. В обоих случаях процесс
ждёт сигнала человека.

Отсканированный `data/boiler_scan.pdf` получает `failed` с причиной «нет текстового слоя: похоже на скан,
распознавание не подключено».

## Команды

| Команда | Что делает |
| --- | --- |
| `make install` | зависимости из `uv.lock` |
| `make up` / `make down` | поднять / остановить базу и Temporal |
| `make migrate` | применить миграции из `db/migrations` |
| `make dev` | HTTP API на :8000 |
| `make worker` | воркер процессов Temporal |
| `make test` | тесты; модели не нужны, тесты с маркером `db` используют базу `cards_test` |
| `make lint` / `make lint-fix` | ruff check и ruff format |
| `make reindex` | досчитать векторы фрагментам без них; повторный запуск — «0» |
| `make eval` | метрики на наборе `eval_defaults`; `make eval FULL=1` — весь эталон |

## Как устроено

```text
POST /documents/ ──► ParseDocumentWorkflow ──► разбор → нормализация → фрагменты → векторы
                                                       (documents, chunks)

POST /generate-card ──► GenerateCardWorkflow
    поиск (гибрид, фильтр по документам)
    → маскирование ПДн → детектор инъекций (правила, затем дешёвая модель) → контекст с chunk_id
    → извлечение фактов → генерация карточки → проверка (ссылки кодом + проверяющая роль)
    → петля точечной переделки, не больше 3 кругов
    → финиш: waiting_approval | needs_review → ожидание сигнала → approved | rejected
```

```text
app/
├── main.py          FastAPI, промежуточный слой с request_id
├── core/            config.py, db.py (pool / connection), logging.py (request_id, job_id), migrate.py
├── routers/         health, cards, jobs, documents, generate, workflows
├── services/        pipeline, structured, documents, rag_pipeline, json_utils
├── agents/          prompts.py — промпты ролей
├── llm/             client.py (единственная дверь к модели), cost.py
├── rag/             embedder, retrieval, context, reindex
├── parsers/         pdf, docx, xlsx, normalizer, chunker
├── guardrails/      pii, injection; __init__.py — фильтр выхода check_output
├── repositories/    jobs, documents, chunks, llm_calls — весь SQL проекта
├── schemas/         cards (контракт карточки), jobs (формы API)
└── temporal/        workflows, activities, client, worker, payloads
db/migrations/       0001_init … 0005_llm_calls
evals/               metrics.py, run.py; отчёты в evals/reports/
data/                пять документов поставщиков и golden_cards.json (как есть)
docs/decisions/      записанные решения
```

## Решения

- [0001 — миграции: SQL-файлы и свой раннер](docs/decisions/0001-migrations.md)
- [0002 — стек, слои, уровни повтора](docs/decisions/0002-stack.md)
- [0003 — порог релевантности 0.82 и как он откалиброван](docs/decisions/0003-relevance-threshold.md)
- [0004 — две модели: основная и дешёвая](docs/decisions/0004-two-models.md)

## Защита

- Персональные данные (телефон, почта, ИНН с проверкой контрольной суммы, карта по Луну) заменяются
  метками «телефон номер один» при сборке контекста — до промпта и до логов. В логи пишутся только метки.
- Инъекции: правила по тексту для всех фрагментов, дешёвая модель — только для помеченных. Если модель
  недоступна или ответ не разобрать, фрагмент считается подозрительным. Подозрительные фрагменты
  исключаются; больше `INJECTION_SUSPICIOUS_LIMIT` — задача уходит в `failed` с причиной.
  Инъекция из `data/kettle_manual.pdf` («SYSTEM: игнорируй все предыдущие инструкции…») ловится правилами.
- Фильтр выхода `app.guardrails.check_output` проверяет текст карточки на ПДн и следы служебных инструкций.
- В результате задачи поле `protection`: что исключено (chunk_id и причина) и сколько чего замаскировано.

## Наблюдаемость

Стоимость одной карточки:

```sql
SELECT role, count(*), sum(cost_usd) FROM llm_calls WHERE job_id = '<job_id>' GROUP BY role;
```

Тот же расчёт отдаёт `GET /jobs/<job_id>` в поле `cost`. Весь путь задачи в логах:
`grep 'job=<job_id>'` по выводу `make dev` и `make worker`.

## Отчёт о прогоне

Состояние на 2026-11-09:

- Проверено вживую: инфраструктура, миграции на чистой базе и повторный запуск, health live/ready
  (в том числе при недоступной базе), загрузка всех пяти документов (четыре `indexed`, скан — `failed`
  с причиной), идемпотентность загрузки и ключа задачи, процесс генерации до вызова модели; при
  недоступной модели задача честно уходит в `failed` с причиной `LLMUnavailableError`.
- Процесс генерации с подменёнными шагами проверен в тестовом окружении Temporal: ожидание подтверждения,
  сигналы approve / reject, петля ограничена тремя кругами.
- **Не выполнено**: прогон генерации и метрик (`make eval`) с настоящей моделью — на машине разработки
  не было чат-модели. Цифры метрик, стоимость карточки и разбор самой слабой метрики появятся здесь
  после `make eval` с подключённым сервером модели.

---

<details>
<summary>Автоматические тесты Хекслета</summary>

Тесты запускаются на каждый коммит. За запуск отвечает файл `.github/workflows/hexlet-check.yml` — не удаляйте и не переименовывайте ни его, ни репозиторий.

</details>

## О Хекслете

[Хекслет](https://ru.hexlet.io/) — школа программирования: авторские программы обучения с практикой, поддержкой наставников и реальными проектами, которые остаются в резюме. Этот репозиторий — один из таких проектов.
