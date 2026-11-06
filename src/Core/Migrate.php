<?php

declare(strict_types=1);

namespace App\Core;

use Doctrine\DBAL\Connection;
use Doctrine\DBAL\Exception;
use Symfony\Component\DependencyInjection\Attribute\Autowire;

/**
 * Раннер SQL-миграций (вместо Alembic): применяет файлы db/migrations/*.sql по порядку имён
 * и запоминает применённые версии в таблице schema_migrations. Повторный запуск ничего не применяет.
 */
final class Migrate
{
    public function __construct(
        private readonly Connection $db,
        #[Autowire('%kernel.project_dir%/db/migrations')]
        private readonly string $dir,
    ) {
    }

    /**
     * @return list<string> версии, применённые этим запуском
     * @throws Exception
     * @throws \Throwable
     */
    public function run(): array
    {
        $this->db->executeStatement(
            'CREATE TABLE IF NOT EXISTS schema_migrations (
                version    text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )'
        );
        /** @var list<string> $done */
        $done = $this->db->fetchFirstColumn('SELECT version FROM schema_migrations');

        $applied = [];
        foreach ($this->files() as $file) {
            $version = basename($file, '.sql');            // 0001_init, 0002_jobs, …
            if (\in_array($version, $done, true)) {
                continue;                                   // уже применяли — пропускаем
            }
            $sql = (string) file_get_contents($file);
            $this->db->transactional(static function (Connection $c) use ($sql, $version): void {
                $c->executeStatement($sql);                 // без параметров → можно несколько команд в одном файле
                $c->insert('schema_migrations', ['version' => $version]);
            });
            $applied[] = $version;
        }

        return $applied;
    }

    /**
     * @return list<string>
     */
    private function files(): array
    {
        $files = glob($this->dir.'/*.sql') ?: [];
        sort($files, \SORT_STRING);                          // порядок задаёт числовой префикс имени

        return $files;
    }
}
