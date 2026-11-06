<?php

declare(strict_types=1);

namespace App\Controller;

use App\Repository\System;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

/**
 * Две проверки состояния: live — про процесс, ready — про зависимости.
 * По live оркестратор решает «перезапускать ли контейнер», по ready — «пускать ли трафик».
 */
final readonly class HealthController
{
    public function __construct(private System $system)
    {
    }

    #[Route('/health/live', name: 'health_live', methods: ['GET'])]
    public function live(): JsonResponse
    {
        return new JsonResponse(['status' => 'ok']);        // отвечает всегда, даже если база лежит
    }

    #[Route('/health/ready', name: 'health_ready', methods: ['GET'])]
    public function ready(): JsonResponse
    {
        try {
            $version = $this->system->vectorVersion();
        } catch (\Throwable $e) {
            return new JsonResponse(['status' => 'fail', 'db' => $e->getMessage()], 503);
        }

        if (null === $version) {
            return new JsonResponse(['status' => 'fail', 'vector' => 'not installed'], 503);
        }

        return new JsonResponse(['status' => 'ok', 'vector' => $version]);
    }
}
