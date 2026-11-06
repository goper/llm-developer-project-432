<?php

declare(strict_types=1);

namespace App\Repository;

use Doctrine\DBAL\Connection;
use Doctrine\DBAL\Exception;

/**
 * Служебные запросы к базе. Правило проекта: SQL живёт только в репозиториях, даже такой маленький.
 */
final class System
{
    public function __construct(private readonly Connection $db)
    {
    }

    /** Версия расширения vector или null, если оно не включено. Бросает исключение, если база недоступна.
     * @throws Exception
     */
    public function vectorVersion(): ?string
    {
        $version = $this->db->fetchOne("SELECT extversion FROM pg_extension WHERE extname = 'vector'");

        return false === $version ? null : (string) $version;
    }
}
