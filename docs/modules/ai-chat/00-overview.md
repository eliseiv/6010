# ai-chat / 00 — Overview

## Назначение

Модуль реализует AI-чат поверх ранее загруженных транскрибаций: ingest текста и summary, генерация ответов LLM строго в контексте транскрибации, быстрые команды, сохранение истории.

## In scope (v1)

1. Связь чата с транскрибацией через `transcription_id` (+ опц. `summary_id`).
2. Endpoint создания сообщения: вход `transcription_id, message, selected_text?, quick_command_type?, summary_id?`; выход `message_id, content (markdown), created_at, structured_blocks?`.
3. Передача в модель контекста: полный текст, summary, выбранный фрагмент, история текущего чата.
4. Ограничение агента контекстом транскрибации (системный prompt запрещает внешние факты).
5. Быстрые команды — enum `quick_command_type`: `extract_tasks, make_summary, main_idea, weekly_plan, follow_up_message, decisions, risks_questions, checklist, content_note, translate_or_adapt`.
6. История чата по транскрибации (один тред на транскрибацию), чтение с пагинацией.
7. Обработка ошибок: timeout, model error, empty transcription, too long context.
8. Лимиты/обрезка контекста: стратегия summary-first, оценка токенов через tiktoken (см. ADR-004).
9. Передача selected_text как отдельного контекста к вопросу.
10. Формат ответа: markdown + optional `structured_blocks` (для `extract_tasks, checklist, decisions, risks_questions`).
11. Ingest endpoint: загрузка `full_text`, опц. `language`, опц. `summary`.

## Out of scope (v1)

- Несколько тредов на одну транскрибацию (ADR-005, Q-AICHAT-1).
- Streaming-ответы.
- Загрузка аудио / выполнение транскрибации.
- RAG/эмбеддинги.
- Per-user RBAC, rate limiting (TD-002).

## Связанные решения

- [ADR-002](../../adr/ADR-002-llm-provider-model.md) — провайдер/модель/бюджет.
- [ADR-004](../../adr/ADR-004-context-summary-first.md) — summary-first и tiktoken.
- [ADR-005](../../adr/ADR-005-thread-and-summary-model.md) — тред и summary.
