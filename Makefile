# Все команды проекта. Нужны uv (менеджер зависимостей) и docker compose.
UV ?= uv
export UV_PROJECT_ENVIRONMENT ?= .venv

.PHONY: help install up down logs migrate dev worker test lint lint-fix reindex eval clean-volumes

help:
	@echo "install       зависимости из uv.lock"
	@echo "up / down     база с pgvector и Temporal (docker compose)"
	@echo "migrate       SQL-миграции из db/migrations"
	@echo "dev           HTTP API на :8000"
	@echo "worker        воркер процессов Temporal"
	@echo "test          тесты (без доступа к модели)"
	@echo "lint          ruff check + format --check"
	@echo "reindex       досчитать векторы фрагментам без них"
	@echo "eval          метрики на эталоне; FULL=1 — весь набор"
	@echo "clean-volumes удалить тома (полный сброс состояния)"

install:
	$(UV) sync --frozen

up:
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	$(UV) run python -m app.core.migrate

dev:
	$(UV) run uvicorn app.main:app --reload --port 8000

worker:
	$(UV) run python -m app.temporal.worker

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

lint-fix:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

reindex:
	$(UV) run python -m app.rag.reindex

eval:
	$(UV) run python -m evals.run $(if $(FULL),--full,)

clean-volumes:
	docker compose down -v
