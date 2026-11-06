# 0002. Язык и каркас: PHP 8.5, Symfony 7.4, FrankenPHP, RoadRunner для Temporal

Дата: 2026-11-06. Статус: принято, согласуется с наставником.

## Контекст

Задание написано под Python (FastAPI, Pydantic, psycopg, Temporal Python SDK, sentence-transformers).
Автопроверка на стороне Хекслета гоняет решение тестами по раскладке Python-модулей (`app/core/db.py` и т. п.).
Автор проекта — PHP-разработчик, основной фреймворк Symfony.

## Решение

Проект пишется на PHP 8.5 и Symfony 7.4 LTS. Каждая роль из задания закрывается PHP-инструментом:

| Роль | В задании | Здесь |
| --- | --- | --- |
| HTTP и слои | FastAPI | Symfony на FrankenPHP (worker-режим: приложение живёт между запросами) |
| Настройки | pydantic-settings | `App\Core\Config` с `#[Autowire(env: ...)]` |
| Контракт результата | Pydantic | `final readonly class` + Symfony Validator + Serializer |
| База | psycopg + пул | Doctrine DBAL без ORM, SQL только в `src/Repository` |
| Устойчивые процессы | Temporal Python SDK | `temporal/sdk` + RoadRunner (воркер в `bin/worker.php`) |
| Вызов модели | openai SDK | Symfony HttpClient к OpenAI-совместимому API (Ollama) |
| Эмбеддинги | sentence-transformers | контейнер TEI с `intfloat/multilingual-e5-small`, 384 измерения |
| Разбор документов | pypdf, python-docx, openpyxl | `smalot/pdfparser`, ZipArchive + DOMXPath, `openspout/openspout` |
| Деньги | Decimal | `BcMath\Number` + `NUMERIC(14,8)` |

Раскладка `src/` повторяет контракт задания в единственном числе: Core, Controller, Service, Agent, Llm, Rag,
Parser, Guardrail, Repository, Schema, Temporal, Command.

## Последствия

- Автопроверка Хекслета (Python-тесты) не пройдёт. Зачёт только по ревью наставника; это согласовано до старта.
- Два сервера приложений: FrankenPHP для HTTP, RoadRunner для воркера Temporal (PHP SDK работает только через него).
  Оба запускают один и тот же код Symfony из одного образа.
- Локально нужны только Docker и make: PHP 8.5 и все расширения живут в образе.
