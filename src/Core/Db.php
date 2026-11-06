<?php

declare(strict_types=1);

namespace App\Core;

use Doctrine\DBAL\Connection;

/**
 * Доступ к базе (аналог app/core/db.py с pool() и connection()).
 *
 * «Пул» на PHP: Symfony создаёт Connection один раз на процесс. В worker-режиме FrankenPHP и в RoadRunner
 * процесс живёт между запросами, поэтому соединение их переживает — пул размера 1 на каждый процесс.
 * Размер общего пула = число процессов (воркеры FrankenPHP + activities.num_workers в .rr.yaml);
 * max_connections в PostgreSQL должен быть больше их суммы.
 */
final class Db
{
    public function __construct(private readonly Connection $connection)
    {
    }

    /** Ресурс уровня приложения: живёт столько же, сколько процесс. */
    public function pool(): Connection
    {
        return $this->connection;
    }

    /**
     * Ресурс уровня операции: короткая транзакция «взял — поработал — вернул».
     * Правило урока: шаг генерации ждёт модель минутами — внутри него открытой транзакции нет,
     * статус в базу пишут отдельным коротким вызовом connection().
     *
     * @template T
     *
     * @param \Closure(Connection): T $fn
     *
     * @return T
     * @throws \Throwable
     */
    public function connection(\Closure $fn): mixed
    {
        return $this->connection->transactional($fn);
    }
}
