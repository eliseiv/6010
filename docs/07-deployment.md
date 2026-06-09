# 07 — Deployment

## Цель

Развёртывание на VPS через Docker / docker-compose. Два контейнера: `api` и `db`.

## Контейнеры

| Сервис | Образ | Порт | Назначение |
|---|---|---|---|
| `api` | сборка из `Dockerfile` (база `python:3.12-slim`) | 8000 (внутр.) | FastAPI/Uvicorn |
| `db` | `postgres:16-alpine` | 5432 (внутр.) | PostgreSQL |

TLS и публикация наружу — через reverse-proxy на VPS (nginx/Caddy), вне docker-compose сервиса. `api` слушает HTTP внутри docker-сети.

## Переменные окружения (`.env`)

| Переменная | Обязательна | Назначение | Пример (.env.example) |
|---|---|---|---|
| `API_KEY` | да | Ключ доступа к API | `change-me-32-bytes-random` |
| `OPENAI_API_KEY` | да | Ключ OpenAI | `sk-...` |
| `OPENAI_MODEL` | нет | Модель OpenAI | `gpt-4o-mini` |
| `OPENAI_TIMEOUT_SECONDS` | нет | Таймаут запроса к OpenAI | `60` |
| `CONTEXT_TOKEN_BUDGET` | нет | Бюджет токенов контекста | `100000` |
| `MAX_OUTPUT_TOKENS` | нет | Лимит токенов ответа | `2000` |
| `POSTGRES_USER` | да | Пользователь БД (для контейнера db) | `app` |
| `POSTGRES_PASSWORD` | да | Пароль БД | `change-me` |
| `POSTGRES_DB` | да | Имя БД | `app` |
| `DATABASE_URL` | только вне compose | Async DSN PostgreSQL. В docker-compose **не задаётся в `.env`** — собирается Compose в `environment` сервиса `api` из `POSTGRES_*` | (compose собирает сам) |
| `LOG_LEVEL` | нет | Уровень логирования | `INFO` |

Дефолты `OPENAI_MODEL` и бюджетов обоснованы в [ADR-002](adr/ADR-002-llm-provider-model.md).

### Согласованность credentials БД (обязательно)

Учётные данные БД задаются **в одном месте** — `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` в `.env`. `DATABASE_URL` для `api`/`alembic` собирается из них автоматически, поэтому рассинхрон пароля исключён by design.

**Как это реально работает (важно).** Docker Compose интерполирует `${...}` **только в самом compose-файле** (значения секции `environment`, `image`, и т.п.), читая переменные из `.env` рядом с compose-файлом. Внутри файлов, подключённых через `env_file:`, интерполяция `${...}` **НЕ выполняется** — их содержимое попадает в контейнер дословно. Поэтому `DATABASE_URL` с `${POSTGRES_PASSWORD}` **нельзя** держать в `.env`: внутрь `api` ушёл бы литерал `"${POSTGRES_PASSWORD}"` → `asyncpg.InvalidPasswordError` → CrashLoop.

Рабочий механизм: `DATABASE_URL` объявлен в секции `environment:` сервиса `api` в `docker-compose.yml`:

```yaml
api:
  environment:
    DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

Здесь Compose резолвит `${...}` из `.env` до старта контейнера, и `api`/`alembic` получают уже собранный DSN с реальным паролем. Значения из `environment:` имеют приоритет над `env_file:`, так что единый источник пароля — `POSTGRES_PASSWORD`.

При смене пароля меняй его **только** в `POSTGRES_PASSWORD` (`.env`). В `.env` `DATABASE_URL` для compose-режима не задаётся.

Исключение — запуск `alembic`/приложения **вне** docker-compose: там нет Compose-интерполяции, нужен явный `DATABASE_URL` (раскомментировать пример в `.env.example`) с тем же паролем, что и `POSTGRES_PASSWORD`.

## Dockerfile (требования)

- База `python:3.12-slim`, non-root user.
- Многослойная сборка: сначала зависимости (`pyproject.toml`), потом код (кэш слоёв).
- **Никаких секретов в образе** (нет `ARG`/`ENV` с ключами). `.dockerignore` исключает `.env`, `.git`, `tests` (опц.), `__pycache__`.
- Entrypoint: применить миграции (`alembic upgrade head`), затем запустить uvicorn.

## docker-compose (требования)

- Сервисы `api`, `db` в общей сети.
- `api.env_file: .env`; секреты — только в runtime, не в build args.
- `db` с volume для персистентности (`pgdata`).
- `db` healthcheck (`pg_isready`); `api` зависит от `db` по healthcheck.
- `api` healthcheck: `GET /health`.
- Перезапуск `restart: unless-stopped`.

## Порядок запуска

```bash
cp .env.example .env   # заполнить секреты
docker compose up -d --build
# api применит миграции на старте, затем поднимет uvicorn
```

## Dev vs Prod запуск (публикация порта api)

Основной `docker-compose.yml` НЕ публикует порт `api` наружу (`expose`-only): на VPS
публикация и TLS обеспечиваются reverse-proxy, а сам `api` слушает HTTP только внутри
docker-сети. Это prod-инвариант — менять его в `docker-compose.yml` нельзя.

Для локальной разработки (открыть Swagger UI `/docs` в браузере) добавлен
`docker-compose.override.yml`, который пробрасывает `8000:8000` на хост.

| Режим | Команда | Override применяется? | Порт api на хосте |
|---|---|---|---|
| **Dev (локально)** | `docker compose up -d --build` | **Да** (авто-подхват) | `localhost:8000` опубликован |
| **Prod (VPS)** | `docker compose -f docker-compose.yml up -d --build` | **Нет** (явный `-f`) | не публикуется, только reverse-proxy |

Механика: `docker compose` без флагов `-f` автоматически сливает `docker-compose.yml`
+ `docker-compose.override.yml`. Как только указан явный `-f docker-compose.yml`,
Compose использует только перечисленные файлы и override НЕ добавляет — поэтому
prod-команда безопасна и порт наружу не уходит.

Локальная проверка Swagger после `docker compose up`:

```bash
curl http://localhost:8000/health        # 200 {"status":"ok"}
curl http://localhost:8000/docs          # 200 Swagger UI (HTML)
curl http://localhost:8000/openapi.json  # 200 OpenAPI schema
```

`docker-compose.override.yml` не содержит секретов (только маппинг порта) и исключён
из Docker-образа через `.dockerignore`. `.env` с секретами игнорируется git
(`.gitignore`) и не попадает в образ (`.dockerignore`).

## Миграции

- Применяются автоматически на старте контейнера `api` (`alembic upgrade head`) до запуска uvicorn.
- Откат — вручную через `alembic downgrade` (в scope оператора).

## CI/CD

- CI (создаёт devops): lint (`ruff check`), format-check (`ruff format --check`), типы (`mypy app`), тесты с покрытием (gate 80%), сборка Docker-образа.
- Конкретная платформа CI (GitHub Actions и т.п.) — за devops. Lock-инструмент зависимостей — TD-001.

## Health & наблюдаемость

- `GET /health` → `200 {"status":"ok"}` (без обращения к OpenAI; опционально проверка БД).
- Структурное логирование на уровне `LOG_LEVEL`. Секреты и full_text не логируются на INFO.

## Статус реализации (фактические артефакты)

Реализовано devops, соответствует требованиям выше:

- `Dockerfile` — multi-stage сборка на `python:3.12-slim`, запуск под non-root user, без секретов в образе.
- `docker-compose.yml` — сервисы `api` + `db`, общая сеть, volume `pgdata`, `restart: unless-stopped`; `db` healthcheck (`pg_isready`), `api` зависит от `db` по healthcheck (healthcheck-gating), `api` healthcheck `GET /health`.
- `docker-entrypoint.sh` — применяет `alembic upgrade head` до запуска uvicorn.
- `.dockerignore` — исключает `.env`, `.git`, `__pycache__` и пр.
- `DATABASE_URL` собирается в `environment:` сервиса `api` из `POSTGRES_*` (см. «Согласованность credentials БД»); в `env_file`/`.env` он не задаётся, т.к. Compose не интерполирует `${...}` в env_file.
- E2E проверка интерполяции пройдена (Docker Compose v5.0.2, движок 29.2.1): стек поднят строго по `.env.example` с тестовым паролем, `printenv DATABASE_URL` внутри `api` отдаёт разрезолвленный DSN (реальный пароль, без литерала `${...}`), `alembic upgrade head` применил `0001_initial_schema`, `GET /health` = `200 {"status":"ok"}`.
