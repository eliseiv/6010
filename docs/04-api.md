# 04 — API (обзор)

Канонический источник истины по контрактам — [modules/ai-chat/02-api-contracts.md](modules/ai-chat/02-api-contracts.md). Здесь — сводка.

## Базовый путь и аутентификация

- Базовый префикс: `/api`.
- Все endpoints требуют заголовок `X-API-Key: <API_KEY>`, **кроме** `GET /health`.
- Формат тел запроса/ответа: `application/json`. Контент ответов LLM — markdown внутри поля `content`.
- Версионирование: без префикса версии в v1 (см. TD-003).

## Сводка endpoints

| Метод | Путь | Назначение | Auth |
|---|---|---|---|
| `POST` | `/api/transcriptions` | Ingest транскрибации (+опц. summary) | X-API-Key |
| `POST` | `/api/chat/messages` | Создать сообщение в чате, получить ответ LLM | X-API-Key |
| `GET` | `/api/transcriptions/{transcription_id}/messages` | История чата (пагинация) | X-API-Key |
| `GET` | `/health` | Healthcheck | нет |

## Коды ошибок (сводка)

| Код | Значение |
|---|---|
| 400 | Невалидное тело / пустая транскрибация (empty transcription) |
| 401 | Отсутствует/неверный X-API-Key |
| 404 | transcription_id / summary_id не найден |
| 413 | Контекст слишком длинный даже после summary-first усечения (too long context) — см. контракт |
| 422 | Ошибка валидации Pydantic |
| 502 | Ошибка модели (model error) |
| 504 | Таймаут обращения к OpenAI |

Точные схемы request/response, примеры и формат тела ошибки — в [modules/ai-chat/02-api-contracts.md](modules/ai-chat/02-api-contracts.md).
