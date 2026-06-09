# Документация проекта: AI-Chat over Transcriptions

Карта документации и единственный источник истины для проекта. Все агенты и разработчики обязаны читать `docs/` перед действиями. При расхождении `docs/` ↔ код — виноват тот, кто не обновил `docs/`.

## Что это за проект

Маленький автономный backend-сервис AI-чата поверх транскрибаций. Пользователь загружает транскрибацию (и опционально summary) в БД сервиса, после чего может вести чат с LLM (OpenAI), задавать вопросы по тексту и запускать быстрые команды (extract_tasks, make_summary и т.д.). Агент ограничен контекстом конкретной транскрибации.

## Карта документов (корень)

| Документ | Назначение | Статус |
|---|---|---|
| [00-vision.md](00-vision.md) | Цели, scope, NFR | Готов |
| [01-architecture.md](01-architecture.md) | Компоненты, deployment topology, диаграмма | Готов |
| [02-tech-stack.md](02-tech-stack.md) | Стек, версии, команды lint/format/test/build | Готов |
| [03-data-model.md](03-data-model.md) | Таблицы, DDL, индексы | Готов |
| [04-api.md](04-api.md) | HTTP API контракты | Готов |
| [05-security.md](05-security.md) | Auth, секреты, угрозы | Готов |
| [06-testing-strategy.md](06-testing-strategy.md) | Пирамида тестов, coverage gate | Готов |
| [07-deployment.md](07-deployment.md) | Docker, docker-compose, VPS | Готов |
| [100-known-tech-debt.md](100-known-tech-debt.md) | Реестр tech debt | Готов |
| [99-open-questions.md](99-open-questions.md) | Cross-cutting открытые вопросы | Готов |
| [adr/INDEX.md](adr/INDEX.md) | Реестр ADR | Готов |

## Модули

| Модуль | Статус | Документы |
|---|---|---|
| [ai-chat](modules/ai-chat/README.md) | Specified (не реализован) | overview, context, api-contracts, architecture, data-model, rbac, implementation-phases, open-questions |

Примечание: проект состоит из единственного модуля `ai-chat` (он же весь сервис). Корневые документы и модульные частично пересекаются по содержанию; модульные документы — детализация контрактов, корневые — обзор. Источник истины по API/данным — модульные `02-api-contracts.md` и `04-data-model.md`, корневые `04-api.md` / `03-data-model.md` ссылаются на них.

## Статусы модулей

- **Specified** — контракты зафиксированы, код не написан.
- **In progress** — реализация идёт.
- **Done** — реализовано, протестировано, ревью пройдено.

Текущий статус: `ai-chat = Specified`.
