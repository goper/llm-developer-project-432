# ИИ-генератор карточки товара

[![hexlet-check](https://github.com/goper/llm-developer-project-432/actions/workflows/hexlet-check.yml/badge.svg)](https://github.com/goper/llm-developer-project-432/actions)

Бэкенд-сервис, который принимает документы поставщиков (pdf, docx, xlsx), строит по ним поисковый индекс
и просит языковую модель собрать черновик карточки товара. Каждая характеристика в карточке ссылается на
фрагмент документа, откуда взята; чего в документах нет, попадает в список недостающих полей, а не выдумывается.

Учебный проект Хекслета: https://ru.hexlet.io/programs/llm-developer (проект 432).

> **Язык решения — PHP 8.5 и Symfony 7.4.** Задание написано под Python, и автопроверка Хекслета
> (тесты по раскладке Python-модулей) на этом репозитории не проходит. Приёмка — по ревью наставника,
> решение и таблица соответствия стеков записаны в [docs/decisions/0002-php-symfony.md](docs/decisions/0002-php-symfony.md).

## Стек

- PHP 8.5, Symfony 7.4 LTS, FrankenPHP в worker-режиме (HTTP)
- PostgreSQL 17 + pgvector, Doctrine DBAL без ORM, SQL-миграции со своим раннером
- Temporal (устойчивые процессы), PHP SDK через RoadRunner (воркер появляется на шаге 3)
- Ollama (OpenAI-совместимый API, две модели) и контейнер эмбеддингов TEI с `intfloat/multilingual-e5-small`
- PHPUnit, PHP CS Fixer, PHPStan

Локально нужны только Docker (с Compose) и make: PHP и все расширения живут в образе.

## Установка и запуск

```bash
git clone https://github.com/goper/llm-developer-project-432.git
cd llm-developer-project-432
make install      # composer install внутри контейнера приложения (первый раз собирает образ, ~10 минут из-за grpc)
make up           # база с pgvector, Temporal, Ollama, эмбеддинги; ждёт healthy
make migrate      # SQL-миграции по порядку; второй запуск сообщит «новых миграций нет»
make dev          # HTTP API на http://localhost:8000
```

Проверка состояния:

```bash
curl localhost:8000/health/live     # {"status":"ok"} — всегда, пока процесс жив
curl localhost:8000/health/ready    # {"status":"ok","vector":"0.8.x"} — база доступна и расширение vector включено
```

Веб-интерфейс Temporal: http://localhost:8233.

Порты на хосте: приложение 8000, база 5433, Ollama 11435, эмбеддинги 8080, Temporal 7233 и 8233. Если какой-то
занят, переопределите переменной перед командой: `DB_PORT=5434 make up` (есть `APP_PORT`, `OLLAMA_PORT`,
`EMBEDDINGS_PORT`). Внутри compose сервисы ходят друг к другу по именам, хост-порты нужны только вам.

Переменные окружения: значения по умолчанию лежат в `.env` (без секретов, рассчитаны на docker compose),
локальные правки и ключи — в `.env.local` (в репозиторий не попадает). Тесты используют `.env.test` и отдельную
базу `cards_test`.

## Команды

| Команда | Что делает |
| --- | --- |
| `make install` | зависимости из `composer.lock` |
| `make up` / `make down` | поднять / остановить инфраструктуру |
| `make migrate` | применить миграции из `db/migrations` |
| `make dev` | приложение на :8000 |
| `make worker` | воркер процессов Temporal (шаг 3) |
| `make test` | PHPUnit |
| `make lint` / `make lint-fix` | PHP CS Fixer + PHPStan |
| `make reindex` | досчитать векторы фрагментам без них (шаг 6) |
| `make eval` | метрики на эталоне, `FULL=1` — весь набор (шаг 8) |

## Структура

```text
src/
├── Core/          Config.php, Db.php (pool / connection), Migrate.php
├── Command/       консольные команды: app:migrate, app:reindex, app:eval
├── Controller/    тонкие HTTP-обработчики: Health, Cards, Jobs, Documents, Generate
├── Service/       Pipeline, Structured, Documents, RagPipeline, JsonUtils
├── Agent/         Prompts — промпты ролей отдельно от логики
├── Llm/           Client (единственная дверь к модели), Cost, Reply
├── Rag/           Embedder, Retrieval, ContextBuilder
├── Parser/        Pdf, Docx, Xlsx, Normalizer, Chunker
├── Guardrail/     Pii, Injection, OutputFilter
├── Repository/    весь SQL проекта
├── Schema/        DTO: Card, Seo, SourceRef, Job
└── Temporal/      процессы и шаги: GenerateCardWorkflow, ParseDocumentWorkflow, *Activities
db/migrations/     SQL-файлы NNNN_название.sql
data/              пять документов поставщиков и эталон golden_cards.json (как есть, побайтово)
docs/decisions/    записанные архитектурные решения
evals/             прогон метрик и отчёты
tests/
```

Правила проекта: SQL только в `src/Repository`, к модели только через `App\Llm\Client`, контроллеры без
бизнес-правил, промпты в `src/Agent/Prompts.php`, тесты не ходят в модель.

## Ход работы

| Шаг | Состояние |
| --- | --- |
| 1. Понять задачу | готово |
| 2. Каркас: Compose с pgvector и Temporal, миграции, пул, health, data/ | готово |
| 3. Архитектура: клиент модели, три роли, процесс Temporal | — |
| 4. Контракт результата | — |
| 5. Документы | — |
| 6. Поиск | — |
| 7. Сборка сквозного сценария | — |
| 8. Production: стоимость, трассировка, метрики | — |
| 9. Защита | — |
| 10. Сдача: прогон с нуля, отчёт | — |

---

<details>
<summary>Автоматические тесты Хекслета</summary>

Тесты запускаются на каждый коммит. За запуск отвечает файл `.github/workflows/hexlet-check.yml` — не удаляйте и не переименовывайте ни его, ни репозиторий.

</details>

## О Хекслете

[Хекслет](https://ru.hexlet.io/) — школа программирования: авторские программы обучения с практикой, поддержкой наставников и реальными проектами, которые остаются в резюме. Этот репозиторий — один из таких проектов.
