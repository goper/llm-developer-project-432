<?php

declare(strict_types=1);

namespace App\Core;

use Symfony\Component\DependencyInjection\Attribute\Autowire;

/**
 * Все настройки приложения в одном типизированном классе (аналог app/core/config.py на pydantic-settings).
 * Значения берутся из переменных окружения: .env — значения по умолчанию, .env.local — локальные и секреты.
 */
final readonly class Config
{
    /**
     * @param array<string, array{in: string, out: string}> $prices цены за 1M токенов, строками (деньги не во float)
     */
    public function __construct(
        #[Autowire(env: 'TEMPORAL_ADDRESS')]
        public string $temporalAddress,
        #[Autowire(env: 'LLM_BASE_URL')]
        public string $llmBaseUrl,
        #[Autowire(env: 'LLM_API_KEY')]
        public string $llmApiKey,
        #[Autowire(env: 'LLM_MODEL_MAIN')]
        public string $modelMain,
        #[Autowire(env: 'LLM_MODEL_CHEAP')]
        public string $modelCheap,
        #[Autowire(env: 'int:LLM_TIMEOUT_SEC')]
        public int $timeoutSec,
        #[Autowire(env: 'int:LLM_MAX_ATTEMPTS')]
        public int $maxAttempts,
        #[Autowire(env: 'json:LLM_PRICES')]
        public array $prices,
        #[Autowire(env: 'EMBEDDINGS_URL')]
        public string $embeddingsUrl,
        #[Autowire(env: 'float:RAG_MIN_SIM')]
        public float $minSim,
        #[Autowire(env: 'float:CONFIDENCE_THRESHOLD')]
        public float $confidenceThreshold,
        #[Autowire(env: 'float:GUARD_MAX_EXCLUDED')]
        public float $maxExcludedShare,
    ) {
    }
}
