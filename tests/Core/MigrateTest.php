<?php

declare(strict_types=1);

namespace App\Tests\Core;

use App\Core\Migrate;
use Doctrine\DBAL\Connection;
use Doctrine\DBAL\Exception as DbalException;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

/**
 * Работает на тестовой базе cards_test (DATABASE_URL из .env.test). Схема пересоздаётся перед проверкой.
 */
final class MigrateTest extends KernelTestCase
{
    private Connection $db;

    protected function setUp(): void
    {
        self::bootKernel();
        $this->db = self::getContainer()->get(Connection::class);

        try {
            $this->db->executeStatement('DROP SCHEMA public CASCADE');
            $this->db->executeStatement('CREATE SCHEMA public');
        } catch (DbalException $e) {
            self::markTestSkipped('Тестовая база недоступна: '.$e->getMessage());
        }
    }

    public function testFirstRunAppliesInitAndSecondRunDoesNothing(): void
    {
        $migrate = self::getContainer()->get(Migrate::class);

        self::assertSame(['0001_init'], $migrate->run(), 'первый запуск применяет первую миграцию');
        self::assertSame([], $migrate->run(), 'повторный запуск ничего не применяет');

        $version = $this->db->fetchOne("SELECT extversion FROM pg_extension WHERE extname = 'vector'");
        self::assertNotFalse($version, 'после миграции расширение vector включено');

        $recorded = $this->db->fetchFirstColumn('SELECT version FROM schema_migrations ORDER BY version');
        self::assertSame(['0001_init'], $recorded);
    }
}
