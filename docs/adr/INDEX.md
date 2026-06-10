# ADR Index

Реестр Architecture Decision Records. Новые решения не должны противоречить действующим ADR без нового ADR.

| ADR | Заголовок | Статус | Дата |
|---|---|---|---|
| [ADR-001](ADR-001-stack-and-topology.md) | Стек и топология: Python/FastAPI монолит + PostgreSQL в Docker | Accepted | 2026-06-09 |
| [ADR-002](ADR-002-llm-provider-model.md) | LLM-провайдер OpenAI, модель и бюджет токенов | Accepted | 2026-06-09 |
| [ADR-003](ADR-003-auth-api-key.md) | Аутентификация по статическому API-key (X-API-Key) | Accepted | 2026-06-09 |
| [ADR-004](ADR-004-context-summary-first.md) | Стратегия контекста summary-first и оценка токенов tiktoken | Accepted | 2026-06-09 |
| [ADR-005](ADR-005-thread-and-summary-model.md) | Один тред на транскрибацию; summary как отдельная сущность | Accepted | 2026-06-09 |
| [ADR-006](ADR-006-prod-deploy-shared-traefik.md) | Прод-развёртывание за общим Traefik на shared-сервере | Accepted | 2026-06-09 |
| [ADR-007](ADR-007-system-prompt-language-mirroring.md) | Language-mirroring в системном prompt: ответ на языке сообщения пользователя | Superseded by ADR-008 | 2026-06-10 |
| [ADR-008](ADR-008-deterministic-language-mirroring.md) | Детерминированный language-mirroring: серверная детекция языка + явная директива (recency) | Accepted | 2026-06-10 |

## Статусы

- **Proposed** — предложено, не принято.
- **Accepted** — действует.
- **Superseded by ADR-NNN** — заменено.
- **Deprecated** — отменено без замены.
