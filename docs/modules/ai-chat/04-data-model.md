# ai-chat / 04 — Data Model (источник истины)

PostgreSQL 16. Применяется через Alembic. UUID PK через `gen_random_uuid()` (расширение `pgcrypto`).

## DDL

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE transcriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_text   TEXT NOT NULL,
    language    TEXT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE summaries (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcription_id  UUID NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,
    summary_text      TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcription_id    UUID NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,
    summary_id          UUID NULL REFERENCES summaries(id) ON DELETE SET NULL,
    role                TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content             TEXT NOT NULL,
    selected_text       TEXT NULL,
    quick_command_type  TEXT NULL CHECK (
        quick_command_type IN (
            'extract_tasks','make_summary','main_idea','weekly_plan',
            'follow_up_message','decisions','risks_questions','checklist',
            'content_note','translate_or_adapt'
        )
    ),
    structured_blocks   JSONB NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Индексы

```sql
CREATE INDEX ix_summaries_transcription_id        ON summaries (transcription_id);
CREATE INDEX ix_chat_messages_transcription_id    ON chat_messages (transcription_id);
-- Для истории треда в порядке времени и пагинации:
CREATE INDEX ix_chat_messages_thread_order        ON chat_messages (transcription_id, created_at, id);
CREATE INDEX ix_chat_messages_summary_id          ON chat_messages (summary_id);
```

## Правила и инварианты

- `full_text` NOT NULL и непустой (непустота проверяется на уровне приложения до записи; пустой ввод → 400).
- `role` ∈ {`user`, `assistant`}. Системный prompt в БД не хранится.
- `quick_command_type` — CHECK на 10 значений enum; NULL для обычных сообщений.
- `structured_blocks` — JSONB, NULL для не-списочных сообщений; для списочных команд — массив объектов (см. 02-api-contracts).
- `summary_id` в chat_messages — какая summary использовалась/подразумевалась (трассируемость); ON DELETE SET NULL.
- ON DELETE CASCADE от transcriptions: удаление транскрибации удаляет её summaries и chat_messages.

## Маппинг на ORM

- SQLAlchemy 2 (async), декларативные модели в `app/models/*.py` (или `app/repositories`). Типы: `Mapped[uuid.UUID]`, `Mapped[str]`, `Mapped[datetime]`, JSONB → `Mapped[list | None]` через `JSONB`.
- enum `quick_command_type` на стороне приложения — Python `Enum`/`Literal`; в БД хранится как TEXT с CHECK (без нативного PG enum для простоты миграций).

## Связь с обзорным документом

Обзор и ERD — в [docs/03-data-model.md](../../03-data-model.md). Этот документ — канонический по DDL/индексам.
