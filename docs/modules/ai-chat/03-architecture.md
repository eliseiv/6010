# ai-chat / 03 — Architecture

## Слои

| Слой | Файлы (ориентир) | Ответственность |
|---|---|---|
| Routers | `app/routers/transcriptions.py`, `app/routers/chat.py`, `app/routers/health.py` (оба `GET /healthz` и `GET /health`) | HTTP endpoints, DI auth |
| Schemas | `app/schemas/*.py` | Pydantic v2 request/response |
| Services | `app/services/ingest.py`, `app/services/chat.py`, `app/services/context.py`, `app/services/llm.py`, `app/services/blocks.py` | Бизнес-логика |
| Repositories | `app/repositories/*.py` | SQLAlchemy async доступ |
| Core | `app/core/config.py`, `app/core/security.py`, `app/core/errors.py`, `app/core/prompts.py`, `app/core/tokens.py`, `app/core/language.py`, `app/core/logging.py` | Конфиг, auth, ошибки, prompts, tiktoken, детекция языка ([ADR-008](../../adr/ADR-008-deterministic-language-mirroring.md)) |

Имена файлов — ориентир для backend; обязательным является корневой пакет `app/` (02-tech-stack) и наличие перечисленной ответственности.

## Поток главного запроса

См. sequence-диаграмму в [docs/01-architecture.md](../../01-architecture.md). Кратко:
1. Auth (X-API-Key, constant-time).
2. Загрузка transcription (+ summary по `summary_id` или последняя) и истории треда.
3. Валидация: транскрибация существует и непуста, summary_id (если задан) принадлежит транскрибации.
4. Построение контекста (summary-first, см. ниже) + детекция языка ответа и инъекция директи­вы языка последним сообщением (см. §«Language-mirroring», [ADR-008](../../adr/ADR-008-deterministic-language-mirroring.md)).
5. Сохранение user-сообщения **отдельным commit'ом ДО вызова LLM** (durability: при ошибке/таймауте модели user-сообщение уже зафиксировано в истории треда, assistant-сообщение не создаётся — см. примечание в 02-api-contracts §2).
6. Запрос к OpenAI (system prompt + контекст), таймаут `OPENAI_TIMEOUT_SECONDS`.
7. Извлечение structured_blocks для списочных команд.
8. Сохранение assistant-сообщения, ответ клиенту.

## Системный prompt (дословно, зафиксировано)

Хранится константой в `app/core/prompts.py`. Текст НЕ менять без нового ADR. Формулировка плейсхолдера и текстовое правило mirroring — [ADR-007](../../adr/ADR-007-system-prompt-language-mirroring.md). Детерминизм языка ответа обеспечивает не этот текст, а серверная детекция + явная директива (см. §«Language-mirroring», [ADR-008](../../adr/ADR-008-deterministic-language-mirroring.md)):

```
Ты AI-ассистент внутри приложения для транскрибации. Работай только с контекстом текущей транскрибации, summary и выбранными пользователем фрагментами. Не выдумывай факты вне предоставленного текста. Если ответа нет в транскрибации, так и скажи и предложи, какой дополнительный контекст нужен.
Отвечай на том же языке, на котором написано текущее сообщение пользователя. Язык транскрибации, summary и истории на язык ответа не влияет — даже если контекст на другом языке, отвечай на языке текущего вопроса. Исключение: для команды перевода/адаптации язык результата определяется самой командой (целевой язык из запроса пользователя).
Твоя задача — помогать пользователю извлекать пользу из транскрибации: делать summary, выделять action items, решения, риски, открытые вопросы, планы, follow-up сообщения, чек-листы и структурированные заметки.
Отвечай кратко и структурно. Если пользователь просит список задач, возвращай пункты с понятным действием, владельцем и сроком, если они есть в тексте. Если владельца или срока нет, помечай это на языке твоего ответа (`не указано` для русского, `not specified` для английского и т. п.).
Всегда сохраняй привязку к исходной транскрибации и не уходи в общие советы, если пользователь прямо не просит этого.
```

## Language-mirroring (детерминированный, зафиксировано) — ADR-008

Язык ответа вычисляется **на сервере**, а не доверяется самоопределению модели. Реализация — `app/core/language.py` + сборка контекста в `app/services/context.py`/`chat.py`. Полное обоснование — [ADR-008](../../adr/ADR-008-deterministic-language-mirroring.md).

**1. Детекция языка** — чистая синхронная функция `detect_response_language(message: str, transcription_language: str | None) -> str` (ISO 639-1), гибрид. Второй аргумент `transcription_language` (= `transcription.language` или `None`) — fallback-сигнал, когда `message` неопределим.
- нормализация (trim, учёт только буквенных символов);
- **script-guard (v1: кириллица + латиница):** доминирование кириллицы (`U+0400–U+04FF`, `U+0500–U+052F`) → `ru` — без обращения к библиотеке. Иная не-латинская письменность (CJK, арабица и т. п.) в v1 в ISO-код по script'у **не** маппится → уходит в fallback;
- **латиница → `lingua`** (набор: English, Russian, German, French, Spanish, Italian, Portuguese; устойчив к коротким строкам), берётся язык с макс. confidence;
- **fallback** (нет буквенных символов / доминирует не-латинская не-кириллическая письменность / `lingua` вернул `None`): `transcription_language` (если валиден ISO) иначе `DEFAULT_RESPONSE_LANGUAGE` (env, default `ru`).

Детектор `lingua` инициализируется один раз на процесс (синглтон/lru).

**2. Директива языка** — короткое **system-сообщение**, добавляется **последним** в `messages[]` (recency), формулировка-шаблон (константа в `app/core/prompts.py`):

```
CRITICAL: Respond ONLY in {language_name}. The language of the transcript, summary, and chat history is irrelevant and MUST NOT influence your output language. Write your entire answer in {language_name}.
```

`{language_name}` — английское название языка из фиксированного маппинга `ISO → English name` в `app/core/language.py` (для языков вне маппинга — сам ISO-код). Директива на английском намеренно — языково-нейтральна к контенту.

**3. Приоритет `translate_or_adapt`:** для `quick_command_type == "translate_or_adapt"` директива mirroring **НЕ инжектируется** (целевой язык определяет команда, см. §«Быстрые команды»). Для всех прочих команд и свободного чата — инжектируется.

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

Приоритет сохранения при усечении (от наивысшего): system_prompt ≈ **директива языка** ≈ текущий `message` > `selected_text` > summary > full_text > история (новые→старые). Директива языка (ADR-008) имеет наивысший приоритет и **никогда не усекается/не отбрасывается**.

### Порядок сообщений в `messages[]` (передаётся в OpenAI) — зафиксировано (ADR-008)

1. `system`: системный prompt (константа `app/core/prompts.py`).
2. контекст по summary-first: история (старые→новые), summary, full_text/selected_text — порядок/усечение по алгоритму ниже.
3. `user`: текущий `message` (+ command prompt при заданном `quick_command_type`).
4. `system`: **директива языка — всегда последнее сообщение** (recency). Пропускается только для `translate_or_adapt`.

Бюджет: директива языка короткая (< 50 токенов), входит в **system-часть** бюджета и учитывается tiktoken **до** summary-first решения наравне с системным prompt ([ADR-002](../../adr/ADR-002-llm-provider-model.md) `CONTEXT_TOKEN_BUDGET`). Она не подлежит усечению — summary-first усекает только full_text/историю/summary/selected_text, поэтому директива не ломает summary-first.

Алгоритм:
1. Собрать полный контекст и оценить токены tiktoken.
2. Если ≤ `CONTEXT_TOKEN_BUDGET` → `context_mode = "full"`.
3. Иначе исключить full_text → `context_mode = "summary_first"`, `context_truncated = true`. Если summary отсутствует → усечь full_text (а не исключить) до влезания.
4. Если всё ещё превышает → усекать историю (старую первой), затем при необходимости summary/selected_text → `context_mode = "truncated"`. summary и selected_text сначала **усекаются по токенам** (tiktoken) и отбрасываются полностью только если усечения недостаточно.
5. Если минимальный контекст не влезает → 413 `context_too_long`.

В ответе всегда выставляются `context_mode` и `context_truncated`. При усечении в markdown добавляется пометка (например: «Ответ построен по сокращённому контексту (summary вместо полного текста)»).

## Health endpoints (зафиксировано)

`app/routers/health.py` реализует два публичных endpoint без auth (контракты — в
[02-api-contracts.md](02-api-contracts.md) §4–5):

| Endpoint | Поведение | БД |
|---|---|---|
| `GET /healthz` | liveness; всегда `200 {"status":"ok"}` пока процесс жив | не трогает |
| `GET /health` | readiness; `200 {"status":"ok"}` или `503 {"status":"degraded"}` | выполняет лёгкую проверку (`SELECT 1`) |

`/healthz` намеренно не зависит от БД, чтобы контейнерный healthcheck/Traefik не
рестартовали живой процесс при временной недоступности БД (см.
[ADR-006](../../adr/ADR-006-prod-deploy-shared-traefik.md)). Контейнерный healthcheck
`api` использует `GET /healthz` (см. [07-deployment.md](../../07-deployment.md)).

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
