# Все команды идут через docker compose: локально нужны только docker и make.
COMPOSE = docker compose
# Разовые команды идут от вашего пользователя, чтобы vendor/ и var/ не стали root-овскими; сам сервер app работает как root.
RUN     = $(COMPOSE) run --rm --user $$(id -u):$$(id -g) -e HOME=/tmp -e COMPOSER_HOME=/tmp/composer
APP     = $(RUN) --no-deps app

.PHONY: help install up down migrate dev worker test lint lint-fix reindex eval ps logs

help:           ## показать команды
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## / — /'

install:        ## зависимости из composer.lock (внутри контейнера приложения)
	$(APP) composer install --no-interaction

up:             ## инфраструктура: база с pgvector, Temporal, Ollama, эмбеддинги
	$(COMPOSE) up -d --wait db temporal ollama embeddings

down:           ## остановить всё (тома остаются)
	$(COMPOSE) down

migrate:        ## SQL-миграции по порядку; повторный запуск — «новых миграций нет»
	$(RUN) app php bin/console app:migrate

dev:            ## HTTP API на http://localhost:8000
	$(COMPOSE) up app

worker:         ## воркер процессов Temporal (шаг 3)
	$(COMPOSE) --profile worker up worker

test:           ## тесты (база cards_test поднимается вместе с инфраструктурой)
	$(RUN) app vendor/bin/phpunit

lint:           ## стиль кода и статический анализ
	$(APP) vendor/bin/php-cs-fixer fix --dry-run --diff
	$(APP) vendor/bin/phpstan analyse --memory-limit=512M

lint-fix:       ## поправить стиль автоматически
	$(APP) vendor/bin/php-cs-fixer fix

reindex:        ## досчитать векторы фрагментам без них (шаг 6)
	$(RUN) app php bin/console app:reindex

eval:           ## метрики на эталоне (шаг 8); FULL=1 — весь набор
	$(RUN) app php bin/console app:eval $(if $(FULL),--full,)

ps:             ## состояние контейнеров
	$(COMPOSE) ps

logs:           ## логи приложения
	$(COMPOSE) logs -f app
