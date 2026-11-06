<?php

declare(strict_types=1);

namespace App\Tests\Controller;

use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;

final class HealthControllerTest extends WebTestCase
{
    public function testLiveAlwaysOk(): void
    {
        $client = static::createClient();
        $client->request('GET', '/health/live');

        self::assertResponseStatusCodeSame(200);
        self::assertSame(['status' => 'ok'], json_decode((string) $client->getResponse()->getContent(), true));
    }

    public function testReadyReportsDatabaseAndVector(): void
    {
        $client = static::createClient();
        $client->request('GET', '/health/ready');

        $status = $client->getResponse()->getStatusCode();
        $body = json_decode((string) $client->getResponse()->getContent(), true);

        self::assertContains($status, [200, 503], 'ready отвечает либо ok, либо 503 с причиной');
        self::assertIsArray($body);
        self::assertArrayHasKey('status', $body);
        if (200 === $status) {
            self::assertSame('ok', $body['status']);
            self::assertArrayHasKey('vector', $body);       // версия расширения видна в ответе
        } else {
            self::assertSame('fail', $body['status']);
        }
    }
}
