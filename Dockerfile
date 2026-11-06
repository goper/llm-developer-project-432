# Образ приложения: PHP 8.5 на FrankenPHP (HTTP, worker-режим) + бинарник RoadRunner (воркер Temporal, шаг 3)
FROM dunglas/frankenphp:1-php8.5

# grpc нужен клиенту Temporal; собирается из pecl, первая сборка занимает ~10 минут
RUN install-php-extensions pdo_pgsql pgsql zip intl bcmath sockets opcache grpc protobuf @composer

COPY --from=ghcr.io/roadrunner-server/roadrunner:latest /usr/bin/rr /usr/local/bin/rr

WORKDIR /app
# Исходники монтируются томом в compose.yml; зависимости ставятся командой `make install`
