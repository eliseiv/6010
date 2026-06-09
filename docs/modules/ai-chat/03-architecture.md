# ai-chat / 03 — Architecture

## Слои

| Слой | Файлы (ориентир) | Ответственность |
|---|---|---|
| Routers | `app/routers/transcriptions.py`, `app/routers/chat.py`, `app/routers/health.py` | HTTP endpoints, DI auth |
| Schemas | `app/schemas/*.py` | Pydantic v2 request/response |
| Services | `app/services/ingest.py`, `app/services/chat.py`, `app/services/context.py`, `app/services/llm.py`, `app/services/blocks.py` | Бизнес-логика |
| Repositories | `app/repositories/*.py` | SQLAlchemy async доступ |
| Core | `app/core/config.py`, `app/core/security.py`, `app/core/errors.py`, `app/core/prompts.py`, `app/core/tokens.py`, `app/core/logging.py` | Конфиг, auth, ошибки, prompts, tiktoken |

Имена файлов — ориентир для backend; обязательным является корневой пакет `app/` (02-tech-stack) и наличие перечисленной ответственности.

## Поток главного запроса

См. sequence-диаграмму в [docs/01-architecture.md](../../01-architecture.md). Кратко:
1. Auth (X-API-Key, constant-time).
2. Загрузка transcription (+ summary по `summary_id` или последняя) и истории треда.
3. Валидация: транскрибация существует и непуста, summary_id (если задан) принадлежит транскрибации.
4. Построение контекста (summary-first, см. ниже).
5. Сохранение user-сообщения **отдельным commit'ом ДО вызова LLM** (durability: при ошибке/таймауте модели user-сообщение уже зафиксировано в истории треда, assistant-сообщение не создаётся — см. примечание в 02-api-contracts §2).
6. Запрос к OpenAI (system prompt + контекст), таймаут `OPENAI_TIMEOUT_SECONDS`.
7. Извлечение structured_blocks для списочных команд.
8. Сохранение assistant-сообщения, ответ клиенту.

## Системный prompt (дословно, зафиксировано)

Хранится константой в `app/core/prompts.py`. Текст НЕ менять без нового ADR:

```
Ты AI-ассистент внутри приложения для транскрибации. Работай только с контекстом текущей транскрибации, summary и выбранными пользователем фрагментами. Не выдумывай факты вне предоставленного текста. Если ответа нет в транскрибации, так и скажи и предложи, какой дополнительный контекст нужен.
Твоя задача — помогать пользователю извлекать пользу из транскрибации: делать summary, выделять action items, решения, риски, открытые вопросы, планы, follow-up сообщения, чек-листы и структурированные заметки.
Отвечай кратко и структурно. Если пользователь просит список задач, возвращай пункты с понятным действием, владельцем и сроком, если они есть в тексте. Если владельца или срока нет, помечай как `не указано`.
Всегда сохраняй привязку к исходной транскрибации и не уходи в общие советы, если пользователь прямо не просит этого.
```

## Быстрые команды (quick_command_type)

Каждая команда добавляет к пользовательскому сообщению инструкцию (command prompt). enum и назначение:

| Команда | Инструкция (суть) | structured_blocks |
|---|---|---|
| `extract_tasks` | Извлечь action items: действие, владелец, срок (`не указано` если нет) | да (`task`) |
| `make_summary` | Сделать краткое summary транскрибации | нет |
| `main_idea` | Сформулировать главную мысль/идею | нет |
| `weekly_plan` | Составить план на неделю на основе содержания | нет |
| `follow_up_message` | Сгенерировать follow-up сообщение по итогам | нет |
| `decisions` | Выделить принятые решения и их обоснования | да (`decision`) |
| `risks_questions` | Выделить риски и открытые вопросы | да (`risk`, `question`) |
| `checklist` | Сформировать чек-лист действий | да (`task`) |
| `content_note` | Составить структурированную заметку по содержанию | нет |
| `translate_or_adapt` | Перевести/адаптировать текст; целевой/исходный язык — из `message`, как hint используется `transcription.language` | нет |

Точные тексты command prompt — константы в `app/core/prompts.py` (backend формулирует по сути выше; при изменении смысла — ADR). Для команд со structured_blocks модель инструктируется вернуть, помимо markdown, машиночитаемый JSON-блок (например, в fenced-блоке), который сервис парсит в `structured_blocks`.

## Стратегия контекста: summary-first (ADR-004)

Реализуется в `app/services/context.py` + `app/core/tokens.py` (tiktoken).

Приоритет (от наивысшего): system_prompt > текущий `message` > `selected_text` > summary > full_text > история (новые→старые).

Алгоритм:
1. Собрать полный контекст и оценить токены tiktoken.
2. Если ≤ `CONTEXT_TOKEN_BUDGET` → `context_mode = "full"`.
3. Иначе исключить full_text → `context_mode = "summary_first"`, `context_truncated = true`. Если summary отсутствует → усечь full_text (а не исключить) до влезания.
4. Если всё ещё превышает → усекать историю (старую первой), затем при необходимости summary/selected_text → `context_mode = "truncated"`. summary и selected_text сначала **усекаются по токенам** (tiktoken) и отбрасываются полностью только если усечения недостаточно.
5. Если минимальный контекст не влезает → 413 `context_too_long`.

В ответе всегда выставляются `context_mode` и `context_truncated`. При усечении в markdown добавляется пометка (например: «Ответ построен по сокращённому контексту (summary вместо полного текста)»).

## Обработка ошибок (зафиксировано)

| Ситуация | Обработка | HTTP |
|---|---|---|
| empty transcription / empty message | проверка до вызова LLM | 400 `empty_transcription` |
| transcription_id не найден | проверка в репозитории | 404 `transcription_not_found` |
| summary_id не найден/чужой | проверка | 404 `summary_not_found` |
| too long context | после summary-first/усечения не влезает | 413 `context_too_long` |
| timeout OpenAI | `asyncio`/клиентский таймаут `OPENAI_TIMEOUT_SECONDS` | 504 `model_timeout` |
| model error (4xx/5xx от OpenAI, невалидный ответ) | перехват исключения клиента | 502 `model_error` |
| невалидный JSON structured_blocks от модели | fallback на `[]`, пометка; ответ всё равно 201 | 201 (TD-006) |

Единый exception handler маппит доменные исключения в формат ошибки из 02-api-contracts. Stack trace — только в логи.
