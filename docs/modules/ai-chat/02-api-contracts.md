# ai-chat / 02 — API Contracts (источник истины)

Канонические контракты HTTP API. Все endpoints под префиксом `/api` требуют заголовок `X-API-Key`, кроме `GET /health`. Тела — `application/json`.

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

Где владелец/срок не указаны в тексте — `null` (в markdown помечается как `не указано`, см. системный prompt). structured_blocks — машинная проекция того же содержимого, что и markdown. Валидация и fallback при невалидном JSON от модели — TD-006.

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

## 4. GET /health — healthcheck (без ключа)

### Response 200

```json
{ "status": "ok" }
```

Не обращается к OpenAI. Опционально проверяет доступность БД (тогда при недоступности — 503 `{"status":"degraded"}`).
