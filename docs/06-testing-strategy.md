# 06 — Testing Strategy

## Пирамида

```
        e2e / integration (FastAPI + реальная/тестовая БД, OpenAI замокан)
      ───────────────────────────────────────────────
     unit (services: context-builder, token-оценка, prompt, error-mapping)
```

Основная масса — unit-тесты сервисного слоя; сверху — интеграционные тесты HTTP через `httpx.ASGITransport`. OpenAI всегда замокан (`respx`/monkeypatch клиента) — реальные вызовы в тестах запрещены.

## Уровни

| Уровень | Что покрывает | Инструменты |
|---|---|---|
| Unit | Построение контекста (summary-first, усечение), оценка токенов (tiktoken), маппинг ошибок→HTTP, извлечение structured_blocks, выбор системного prompt | pytest, pytest-asyncio |
| Integration | Endpoints `/api/transcriptions`, `/api/chat/messages`, `/api/transcriptions/{id}/messages`, `/health`; auth (X-API-Key); коды ошибок | pytest + httpx ASGITransport + тестовая Postgres |
| Contract | Соответствие request/response схемам из 02-api-contracts | pytest (валидация Pydantic) |

## Тестовая БД

- Используется PostgreSQL (тот же мажор, что прод — 16). Варианты: контейнер в CI или локально. Изоляция — транзакция-на-тест или пересоздание схемы. Выбор механики — за qa/devops (зафиксировать при настройке CI).

## Обязательные тест-кейсы (acceptance)

1. Ingest транскрибации возвращает `transcription_id` (и `summary_id` при переданном summary).
2. `POST /api/chat/messages` без `X-API-Key` → 401.
3. С неверным ключом → 401 (и не «протекает» через timing — проверяется логикой, не временем).
4. Пустая транскрибация / пустой message → 400.
5. transcription_id не существует → 404.
6. Успешный ответ (OpenAI замокан) → 201, поля `message_id`, `content`, `created_at`.
7. Списочная команда (`extract_tasks`/`checklist`/`decisions`/`risks_questions`) → присутствует `structured_blocks`.
8. Длинный текст > бюджета → применяется summary-first, ответ содержит пометку усечения; токены контекста ≤ бюджета.
9. Текст > бюджета даже после summary-first → 413 (too long context).
10. Таймаут OpenAI → 504; model error → 502.
11. История чата возвращается с пагинацией, в правильном порядке.
12. selected_text прокидывается в контекст.

## Coverage gate

- Минимум **80%** строк (`pytest --cov=app --cov-fail-under=80`). CI падает ниже порога.

## Запрещено в тестах

- Реальные вызовы OpenAI.
- Зависимость тестов от внешней сети.
- Хардкод секретов (использовать фикстуры/env override).
