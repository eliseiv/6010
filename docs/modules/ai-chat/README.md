# Модуль: ai-chat

AI-чат поверх транскрибаций. Единственный модуль сервиса (он же весь сервис).

- **Статус:** Implemented (код, миграции, тесты 79/79 зелёные, Docker-деплой; e2e smoke пройден). docs синхронизированы с реализацией.
- **DoD (Definition of Done) для v1:**
  - Реализованы все endpoints из [02-api-contracts.md](02-api-contracts.md).
  - Модель данных по [04-data-model.md](04-data-model.md), миграции Alembic.
  - Системный prompt (дословно ниже) и summary-first стратегия ([03-architecture.md](03-architecture.md)).
  - 10 быстрых команд (enum), structured_blocks для списочных.
  - Обработка ошибок: timeout, model error, empty transcription, too long context.
  - Тесты по [docs/06-testing-strategy.md](../../06-testing-strategy.md), coverage ≥80%.
  - Деплой по [docs/07-deployment.md](../../07-deployment.md).

## Документы модуля

| Документ | Назначение |
|---|---|
| [00-overview.md](00-overview.md) | Scope / out-of-scope |
| [01-context.md](01-context.md) | Зависимости, соседи, интеграция |
| [02-api-contracts.md](02-api-contracts.md) | Контракты endpoints (источник истины) |
| [03-architecture.md](03-architecture.md) | Слои, prompt, summary-first, error-handling |
| [04-data-model.md](04-data-model.md) | DDL, индексы (источник истины) |
| [06-rbac.md](06-rbac.md) | Модель доступа |
| [07-implementation-phases.md](07-implementation-phases.md) | Фазы реализации |
| [99-open-questions.md](99-open-questions.md) | Открытые вопросы модуля |

Документ events (`05-events.md`) не создаётся: событийной интеграции в v1 нет (см. 01-context).

## Changelog

| Дата | Изменение |
|---|---|
| 2026-06-09 | Bootstrap: зафиксированы контракты, модель, prompt, стратегии. Статус Specified. |
| 2026-06-09 | Backend: реализован сервис (`app/`) — config, модели + Alembic-миграция, auth X-API-Key (constant-time), endpoints ingest/chat/history/health, OpenAI-интеграция (таймаут + 1 retry), summary-first context (tiktoken), structured_blocks, обработка ошибок по контракту. lint/format/mypy зелёные. Тесты — за qa. |
| 2026-06-09 | Backend (факты реализации): user-сообщение фиксируется отдельным commit'ом ДО вызова LLM (durability); `translate_or_adapt` использует `transcription.language` как hint; summary/selected_text усекаются по токенам перед полным отбрасыванием; исправлен `alembic.ini` (логирование в `sys.stderr`). |
| 2026-06-09 | QA: 79/79 тестов зелёные. Выявлено противоречие docs внутри модуля (02 vs 03 про обязательность `message` при quick_command_type). |
| 2026-06-09 | DevOps: Dockerfile (multi-stage, non-root), docker-compose (api+db, healthcheck-gating), docker-entrypoint.sh (alembic upgrade head → uvicorn), .dockerignore. E2E smoke пройден. См. [07-deployment.md](../../07-deployment.md). |
| 2026-06-09 | Architect: устранено противоречие — 02-api-contracts §2 выровнен под фактическое поведение 03 (`message` обязателен и непуст всегда, в т.ч. при заданной команде → 400 `empty_transcription`). Error-коды 02↔03 сверены и согласованы. Статус → Implemented. |
| 2026-06-10 | Architect: ADR-008 (supersede ADR-007) — детерминированный language-mirroring. Серверная детекция языка (`app/core/language.py`, lingua + script-guard), явная директива языка последним system-сообщением (recency), приоритет `translate_or_adapt`, учёт в бюджете токенов. Обновлены 03-architecture, 02-api-contracts, 02-tech-stack (lingua), 06-testing-strategy (правило тестирования LLM-зависимых изменений). Требуется реализация backend + детерминированные тесты qa. |
