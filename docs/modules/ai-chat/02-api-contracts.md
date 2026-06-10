# ai-chat / 02 — API Contracts (источник истины)

Канонические контракты HTTP API. Все endpoints под префиксом `/api` требуют заголовок `X-API-Key`. Публичные endpoints без ключа: `GET /healthz` (liveness) и `GET /health` (readiness). Тела — `application/json`.

## Общий формат ошибки

```json
{
  "error": {
    "code": "string",          // машинный код, см. таблицу ниже
    "message": "string",       // человекочитаемое описание (без stack trace)
    "details": {}              // опционально, доп. контекст
  }
}
```

| HTTP | error.code | Когда |
|---|---|---|
| 400 | `empty_transcription` | full_text/message пустой или транскрибация без текста |
| 400 | `bad_request` | прочие нарушения бизнес-правил входа |
| 401 | `unauthorized` | отсутствует/неверный X-API-Key |
| 404 | `transcription_not_found` | transcription_id не найден |
| 404 | `summary_not_found` | summary_id не найден (или не принадлежит транскрибации) |
| 413 | `context_too_long` | контекст превышает бюджет даже после summary-first усечения |
| 422 | `validation_error` | ошибка валидации Pydantic |
| 502 | `model_error` | OpenAI вернул ошибку модели/API |
| 504 | `model_timeout` | таймаут обращения к OpenAI |

---

## 1. POST /api/transcriptions — ingest

Загрузка транскрибации и опционально summary.

### Request

```json
{
  "full_text": "string (required, non-empty)",
  "language": "string|null (опц., ISO-код, напр. 'ru')",
  "summary": "string|null (опц., текст summary)"
}
```

### Response 201

```json
{
  "transcription_id": "uuid",
  "summary_id": "uuid|null",     // присутствует, если был передан summary
  "created_at": "ISO-8601 timestamptz"
}
```

### Ошибки

- 400 `empty_transcription` — `full_text` пустой/whitespace.
- 401 / 422 по общим правилам.

---

## 2. POST /api/chat/messages — главный endpoint

Создаёт пользовательское сообщение, формирует контекст, запрашивает LLM, сохраняет и возвращает ответ ассистента.

### Request

```json
{
  "transcription_id": "uuid (required)",
  "message": "string (required, non-empty)",
  "selected_text": "string|null (опц.)",
  "quick_command_type": "enum|null (опц.)",
  "summary_id": "uuid|null (опц.)"
}
```

`quick_command_type` ∈ `extract_tasks | make_summary | main_idea | weekly_plan | follow_up_message | decisions | risks_questions | checklist | content_note | translate_or_adapt`.

Семантика `message`: поле **обязательно и непусто всегда**, в том числе при заданном `quick_command_type`. Пустой/whitespace `message` отклоняется до вызова LLM как `400 empty_transcription` (ранний guard, см. [03-architecture.md](03-architecture.md) §«Обработка ошибок»). При заданной команде `message` трактуется как пользовательское уточнение к команде, а основная инструкция формируется из command prompt (см. 03-architecture). Передавать команду без `message` нельзя.

### Response 201

```json
{
  "message_id": "uuid",
  "transcription_id": "uuid",
  "role": "assistant",
  "content": "string (markdown)",
  "created_at": "ISO-8601 timestamptz",
  "quick_command_type": "enum|null",
  "structured_blocks": [ /* см. ниже; null или [] если неприменимо */ ],
  "context_truncated": false,        // true, если применялся summary-first/усечение
  "context_mode": "full|summary_first|truncated"
}
```

### structured_blocks

Возвращаются (непустыми) для списочных команд: `extract_tasks, checklist, decisions, risks_questions`. Для прочих — `null`. Формат — массив объектов; тип блока зависит от команды:

```json
// extract_tasks / checklist
{ "type": "task", "text": "string", "owner": "string|null", "due": "string|null", "done": false }

// decisions
{ "type": "decision", "text": "string", "rationale": "string|null" }

// risks_questions
{ "type": "risk", "text": "string", "severity": "string|null" }
{ "type": "question", "text": "string" }
```

Где владелец/срок не указаны в тексте — `null` (в markdown помечается плейсхолдером на языке ответа: `не указано` для русского, `not specified` для английского и т. п., см. системный prompt и [ADR-007](../../adr/ADR-007-system-prompt-language-mirroring.md)). Источник истины для `structured_blocks` — машинные `null`-поля, а не текст маркера в markdown; не используй строковый матчинг плейсхолдера для построения блоков. structured_blocks — машинная проекция того же содержимого, что и markdown. Валидация и fallback при невалидном JSON от модели — TD-006.

### Ошибки

- 400 `empty_transcription` — у транскрибации нет текста / `message` пустой.
- 404 `transcription_not_found` / `summary_not_found`.
- 413 `context_too_long`.
- 502 `model_error`, 504 `model_timeout`.
- 401 / 422 по общим правилам.

Примечание: при ошибке LLM (502/504) уже сохранённое user-сообщение остаётся в истории; assistant-сообщение не создаётся.

---

## 3. GET /api/transcriptions/{transcription_id}/messages — история

Возвращает историю треда (один тред на транскрибацию), упорядоченную по времени.

### Query params

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int | 50 | Макс. число сообщений (1..200) |
| `offset` | int | 0 | Смещение |
| `order` | enum `asc\|desc` | `asc` | Порядок по `created_at` |

### Response 200

```json
{
  "transcription_id": "uuid",
  "total": 123,
  "limit": 50,
  "offset": 0,
  "messages": [
    {
      "message_id": "uuid",
      "role": "user|assistant",
      "content": "string",
      "selected_text": "string|null",
      "quick_command_type": "enum|null",
      "structured_blocks": [],
      "created_at": "ISO-8601"
    }
  ]
}
```

### Ошибки

- 404 `transcription_not_found`.
- 401 / 422 по общим правилам.

---

## 4. GET /healthz — liveness (без ключа)

Liveness-проба: «процесс жив». Используется контейнерным healthcheck `api`, общим
Traefik и внешним мониторингом. **БЕЗ auth** (как `/health`). **НЕ** зависит от БД и
OpenAI.

### Response 200 (всегда, пока процесс жив)

```json
{ "status": "ok" }
```

`/healthz` не имеет статуса `degraded` и не возвращает 503: пока FastAPI/Uvicorn
отвечает — это `200`. Недоступность БД на `/healthz` **не** влияет (иначе живой процесс
получал бы лишние рестарты от healthcheck). Проверка БД — на `/health` (ниже).

---

## 5. GET /health — readiness/health (без ключа)

Readiness/health-проба: «готов обслуживать запросы». **БЕЗ auth.** Не обращается к
OpenAI, **проверяет доступность БД**.

### Response 200 (БД доступна)

```json
{ "status": "ok" }
```

### Response 503 (БД недоступна)

```json
{ "status": "degraded" }
```

---

### Различие /healthz vs /health (зафиксировано)

| Endpoint | Семантика | Зависит от БД | Коды | Назначение |
|---|---|---|---|---|
| `GET /healthz` | liveness (процесс жив) | нет | `200` всегда | healthcheck контейнера, Traefik, внешний мониторинг |
| `GET /health` | readiness/health (готов обслуживать) | да | `200` / `503 degraded` | проверка готовности с учётом БД |

Обоснование разделения — [ADR-006](../../adr/ADR-006-prod-deploy-shared-traefik.md):
liveness не должен падать из-за временной недоступности БД, иначе оркестратор будет
рестартовать здоровый процесс; для проверки готовности (БД доступна) существует
отдельный `/health`. Оба endpoint — без `X-API-Key` (исключения из auth, см.
[05-security.md](../../05-security.md)).
