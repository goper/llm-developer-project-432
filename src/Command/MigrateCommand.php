<?php

declare(strict_types=1);

namespace App\Command;

use App\Core\Migrate;
use Doctrine\DBAL\Exception;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;

#[AsCommand(name: 'app:migrate', description: 'Применить SQL-миграции из db/migrations по порядку')]
final class MigrateCommand extends Command
{
    public function __construct(private readonly Migrate $migrate)
    {
        parent::__construct();
    }

    /**
     * @throws \Throwable
     * @throws Exception
     */
    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $applied = $this->migrate->run();
        $output->writeln($applied
            ? 'применены: '.implode(', ', $applied)
            : 'новых миграций нет');

        return Command::SUCCESS;
    }
}
