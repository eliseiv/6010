# 07 — Deployment

## Цель

Развёртывание через Docker / docker-compose. Два контейнера: `api` и `db`.

Прод-среда — **общий** сервер Ubuntu 22.04 за **общим reverse-proxy Traefik**. Топология
и интеграция с Traefik зафиксированы в [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md).

## Контейнеры

| Сервис | Образ | Порт | Назначение |
|---|---|---|---|
| `api` | сборка из `Dockerfile` (база `python:3.12-slim`) | 8000 (внутр., `expose`) | FastAPI/Uvicorn |
| `db` | `postgres:16-alpine` | 5432 (внутр.) | PostgreSQL |

TLS и публикация наружу — через **общий Traefik** на сервере (см. ниже). Сервис **не
публикует** порты 80/443, **не настраивает** свой nginx/SSL. `api` слушает HTTP внутри
docker-сети; Traefik подключается к нему по общей сети `web` на порт `8000`.

## Прод-топология (за общим Traefik)

```mermaid
graph LR
    Client[Внешний клиент] -->|HTTPS velunoapp.shop| TR[Общий Traefik\nentrypoint websecure\ncertresolver le]
    TR -->|HTTP :8000 по сети web| API[api: FastAPI/Uvicorn]
    API -->|SQL async, сеть default| DB[(PostgreSQL)]
    API -->|HTTPS| OpenAI[OpenAI API]

    subgraph SRV [Ubuntu 22.04 87.239.135.154]
        subgraph EDGE [/opt/edge - НЕ трогаем]
            TR
        end
        subgraph AICHAT [/opt/aichat - наш сервис]
            API
            DB
        end
    end

    classDef ext fill:#eee,stroke:#999;
    class EDGE ext;
```

Ключевые факты прод-окружения (источник истины — [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md)):

- Сервер: Ubuntu 22.04, IP `87.239.135.154`. На нём работают другие сервисы и общий
  Traefik (каталог `/opt/edge`) — **не трогаем**.
- Traefik терминирует TLS и сам выпускает/продлевает Let's Encrypt (certresolver `le`
  на entrypoint `websecure`). Порты 80/443 заняты Traefik; наш сервис их не публикует.
- Маршрутизация — через docker labels на сервисе `api` (Traefik router/service name =
  `aichat`), подключение к общей внешней docker-сети `web` (external, уже создана).
- Домен: apex `velunoapp.shop`, A-запись → `87.239.135.154` (настраивает владелец домена).
- Каталог сервиса на сервере: `/opt/aichat` (репозиторий, `.env`, volume БД). Изолирован
  от `/opt/edge` и чужих сервисов.

### Traefik labels на сервисе `api` (объявляются в `docker-compose.prod.yml`)

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.aichat.rule=Host(`velunoapp.shop`)"
  - "traefik.http.routers.aichat.entrypoints=websecure"
  - "traefik.http.routers.aichat.tls.certresolver=le"
  - "traefik.http.services.aichat.loadbalancer.server.port=8000"
```

### Сеть `web` (external) — внешний контракт

- `web` — общая внешняя docker-сеть, **уже создана** владельцем сервера (`external: true`).
  Наш `docker-compose.prod.yml` её **не создаёт**, только подключается.
- `api` входит в две сети: `web` (для Traefik) и внутреннюю `default`/`appnet` (для БД).
- `db` — **только** во внутренней сети, без портов наружу.
- Имена `web`, entrypoint `websecure`, certresolver `le` — внешний контракт владельца
  edge. Их переименование на стороне Traefik сломает деплой (ограничение из ADR-006).

### Требование DNS (обязательно до первого деплоя)

A-запись `velunoapp.shop` → `87.239.135.154` должна существовать **до** первого деплоя:
без неё ACME HTTP-01 челлендж Let's Encrypt не пройдёт и сертификат не выпустится.
Запись настраивает владелец домена.

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

### Размещение секретов в проде

- Файл `.env` приложения лежит в `/opt/aichat/.env` на сервере. Он **gitignored** и
  **CI его не трогает** (`git pull` не перезаписывает untracked-файл).
- В **GitHub Secrets** хранятся только параметры доступа CI к серверу: `SSH_HOST`,
  `SSH_USER`, `SSH_PRIVATE_KEY`. Прикладные секреты (`API_KEY`, `OPENAI_API_KEY`,
  `POSTGRES_PASSWORD` и пр.) в GitHub Secrets **не попадают** (см. [05-security.md](05-security.md)).

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

Топология трёх файлов (см. [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md)):

| Файл | Роль | Применяется |
|---|---|---|
| `docker-compose.yml` | Базовый: `api` + `db`, expose-only, без публикации портов и без сети `web` | Всегда |
| `docker-compose.prod.yml` | Прод-overlay: сеть `web` (external), Traefik labels, подключение `api` к `web` + внутренней сети | Только прод (явный `-f`) |
| `docker-compose.override.yml` | Dev-overlay: проброс `8000:8000` на localhost | Только dev (авто-подхват) |

Базовый `docker-compose.yml`:

- Сервисы `api`, `db` во внутренней сети (`appnet`/`default`).
- `api.env_file: .env`; секреты — только в runtime, не в build args.
- `db` с volume для персистентности (`pgdata`), без портов наружу.
- `db` healthcheck (`pg_isready`); `api` зависит от `db` по healthcheck.
- `api` healthcheck: `GET /healthz` (liveness, без БД — см. ниже «Health & наблюдаемость»).
- `api` `expose: 8000` — наружу не публикуется (прод-инвариант).
- Перезапуск `restart: unless-stopped`.

Прод-overlay `docker-compose.prod.yml`:

- Объявляет сеть `web` как `external: true` (не создаёт её).
- Добавляет на `api` Traefik labels (см. «Traefik labels» выше).
- Подключает `api` к сети `web` **и** к внутренней сети; `db` остаётся только во
  внутренней.
- Не публикует портов на хост.

## Команды запуска (dev vs prod)

Основной `docker-compose.yml` НЕ публикует порт `api` наружу (`expose`-only). Это
prod-инвариант — менять его в `docker-compose.yml` нельзя. Публикация/TLS — общий
Traefik (прод) или dev-override (локально).

| Режим | Команда | Какие файлы | Порт api на хосте | Traefik |
|---|---|---|---|---|
| **Dev (локально)** | `docker compose up -d --build` | base + `override` (авто) | `localhost:8000` опубликован | нет |
| **Prod (сервер)** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` | base + `prod` (явно) | не публикуется | да, по сети `web` |

Механика выбора файлов:

- **Dev:** `docker compose` без флагов `-f` автоматически сливает `docker-compose.yml`
  + `docker-compose.override.yml`. `docker-compose.prod.yml` при этом **не** подхватывается
  (он не входит в авто-список).
- **Prod:** перечисляем файлы **явно** через `-f`. Compose использует ТОЛЬКО
  перечисленные → `docker-compose.override.yml` НЕ добавляется (порт наружу не уходит),
  а `docker-compose.prod.yml` подключает сеть `web` и Traefik labels.

Прод-команда (на сервере, из `/opt/aichat`):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# api применит миграции (alembic upgrade head) на старте, затем поднимет uvicorn
```

Dev-команда (локально):

```bash
cp .env.example .env   # заполнить секреты
docker compose up -d --build
```

Локальная проверка Swagger после dev-запуска:

```bash
curl http://localhost:8000/healthz       # 200 {"status":"ok"} (liveness, без БД)
curl http://localhost:8000/health        # 200 {"status":"ok"} (readiness, c проверкой БД)
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

Платформа: **GitHub Actions**, репозиторий публичный (`github.com/eliseiv/6010`).

### CI (на pull request / push)

- lint (`ruff check`), format-check (`ruff format --check`), типы (`mypy app`),
  тесты с покрытием (gate 80%), сборка Docker-образа. Lock-инструмент зависимостей — TD-001.

### CD (deploy по push в `main`)

```mermaid
sequenceDiagram
    participant Dev as Разработчик
    participant GH as GitHub Actions
    participant SRV as Сервер (/opt/aichat)
    participant TR as Общий Traefik

    Dev->>GH: push в main
    GH->>SRV: SSH (SSH_HOST/SSH_USER/SSH_PRIVATE_KEY)
    SRV->>SRV: cd /opt/aichat && git pull (HTTPS, публичный репо)
    SRV->>SRV: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
    SRV->>SRV: api: alembic upgrade head, затем uvicorn
    TR->>SRV: маршрутизирует velunoapp.shop → api:8000 по сети web
```

Шаги CD:

1. Trigger: `push` в ветку `main`.
2. GitHub Actions подключается по SSH к серверу, используя `SSH_HOST`, `SSH_USER`,
   `SSH_PRIVATE_KEY` из **GitHub Secrets**.
3. На сервере: `cd /opt/aichat && git pull` — репозиторий публичный, тянется по HTTPS,
   отдельный доступ-токен к GitHub не нужен.
4. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` —
   пересборка и рестарт; `api` на старте применяет миграции и поднимает uvicorn.
5. `/opt/aichat/.env` (gitignored) CI не трогает — прикладные секреты остаются на сервере.

## Health & наблюдаемость

Две раздельные пробы (контракты — в [modules/ai-chat/02-api-contracts.md](modules/ai-chat/02-api-contracts.md)):

- **`GET /healthz` — liveness.** Всегда `200 {"status":"ok"}` пока процесс жив. **Не**
  зависит от БД и OpenAI. Используется контейнерным healthcheck `api`, Traefik и внешним
  мониторингом — чтобы недоступность БД не приводила к рестарту живого процесса.
- **`GET /health` — readiness/health.** `200 {"status":"ok"}` без обращения к OpenAI;
  проверяет доступность БД и при её недоступности возвращает `503 {"status":"degraded"}`.

Различие зафиксировано в [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md): liveness
(процесс жив) отделён от readiness (готов обслуживать, БД доступна).

- Структурное логирование на уровне `LOG_LEVEL`. Секреты и full_text не логируются на INFO.

## Статус реализации (фактические артефакты)

Реализовано devops, соответствует требованиям выше:

- `Dockerfile` — multi-stage сборка на `python:3.12-slim`, запуск под non-root user, без секретов в образе.
- `docker-compose.yml` — сервисы `api` + `db`, общая сеть, volume `pgdata`, `restart: unless-stopped`; `db` healthcheck (`pg_isready`), `api` зависит от `db` по healthcheck (healthcheck-gating), `api` healthcheck `GET /health`.
- `docker-entrypoint.sh` — применяет `alembic upgrade head` до запуска uvicorn.
- `.dockerignore` — исключает `.env`, `.git`, `__pycache__` и пр.
- `DATABASE_URL` собирается в `environment:` сервиса `api` из `POSTGRES_*` (см. «Согласованность credentials БД»); в `env_file`/`.env` он не задаётся, т.к. Compose не интерполирует `${...}` в env_file.
- E2E проверка интерполяции пройдена (Docker Compose v5.0.2, движок 29.2.1): стек поднят строго по `.env.example` с тестовым паролем, `printenv DATABASE_URL` внутри `api` отдаёт разрезолвленный DSN (реальный пароль, без литерала `${...}`), `alembic upgrade head` применил `0001_initial_schema`, `GET /health` = `200 {"status":"ok"}`.

### Прод-артефакты за общим Traefik (требуются, реализация — devops по ADR-006)

Следующее ещё не реализовано и подлежит созданию devops + backend по этому документу и [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md):

- `docker-compose.prod.yml` — прод-overlay: сеть `web` (`external: true`), Traefik labels на `api`, подключение `api` к `web` + внутренней сети.
- Endpoint `GET /healthz` (liveness, без БД) в `api` (backend) — см. модульные 02/03.
- Переключение контейнерного healthcheck `api` на `GET /healthz` (в `docker-compose.yml`).
- GitHub Actions workflow CD (deploy по push в `main`, SSH-деплой) — см. раздел CI/CD.
