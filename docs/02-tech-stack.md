# 02 — Tech Stack

Единственное место фиксации стека, версий и команд. Другие агенты language-agnostic и берут команды отсюда. Если чего-то здесь нет — это блокер, не угадывать.

## Язык и runtime

- **Python 3.12** (целевой минор; в Docker — образ `python:3.12-slim`).

## Основные зависимости (runtime)

| Пакет | Версия (constraint) | Назначение |
|---|---|---|
| `fastapi` | `>=0.115,<0.116` | Web framework |
| `uvicorn[standard]` | `>=0.32,<0.33` | ASGI сервер |
| `pydantic` | `>=2.9,<3.0` | Валидация (Pydantic v2) |
| `pydantic-settings` | `>=2.5,<3.0` | Загрузка конфига из `.env` |
| `sqlalchemy` | `>=2.0.35,<2.1` | ORM/Core (async) |
| `asyncpg` | `>=0.30,<0.31` | Async-драйвер PostgreSQL |
| `alembic` | `>=1.13,<2.0` | Миграции БД |
| `openai` | `>=1.54,<2.0` | Клиент OpenAI |
| `tiktoken` | `>=0.8,<0.9` | Оценка токенов |
| `lingua-language-detector` | `>=2.0,<3.0` | Серверная детекция языка `message` для language-mirroring ([ADR-008](adr/ADR-008-deterministic-language-mirroring.md)) |
| `python-dotenv` | `>=1.0,<2.0` | Поддержка `.env` (через pydantic-settings) |

## Dev / тест зависимости

| Пакет | Версия (constraint) | Назначение |
|---|---|---|
| `pytest` | `>=8.3,<9.0` | Тестовый фреймворк |
| `pytest-asyncio` | `>=0.24,<0.25` | Async-тесты |
| `pytest-cov` | `>=5.0,<6.0` | Покрытие |
| `httpx` | `>=0.27,<0.28` | Тестовый HTTP-клиент (ASGITransport) |
| `ruff` | `>=0.7,<0.8` | Lint + format |
| `mypy` | `>=1.13,<2.0` | Статическая типизация |
| `respx` | `>=0.21,<0.22` | Мокирование HTTP (OpenAI) в тестах |

## БД

- **PostgreSQL 16** (Docker-образ `postgres:16-alpine`). Отдельный контейнер в docker-compose.

## Управление зависимостями

- Файл `pyproject.toml` (PEP 621). Опционально lock через `pip-tools` или `uv`; выбор инструмента lock — за devops (см. TD-001), но манифест зависимостей — `pyproject.toml`.

## Команды

Запускаются из корня проекта. Точные пути модулей определит devops/backend при создании скелета; ниже — канонические команды, на которые опираются остальные агенты.

| Назначение | Команда |
|---|---|
| Установка зависимостей (dev) | `pip install -e ".[dev]"` |
| Lint | `ruff check .` |
| Format (применить) | `ruff format .` |
| Format (проверка) | `ruff format --check .` |
| Type check | `mypy app` |
| Тесты | `pytest` |
| Тесты с покрытием | `pytest --cov=app --cov-report=term-missing --cov-fail-under=80` |
| Миграции (применить) | `alembic upgrade head` |
| Создать миграцию | `alembic revision --autogenerate -m "<msg>"` |
| Локальный запуск | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |

Корневой пакет приложения — `app` (директория `app/`). Это фиксированное соглашение для команд выше; backend обязан использовать его.

## Конфигурация инструментов

- `ruff`: line-length 100, target `py312`, правила по умолчанию + `I` (isort). Точная секция `[tool.ruff]` — в `pyproject.toml`, создаёт devops/backend.
- `mypy`: `strict = true` для пакета `app`.
- Coverage gate: **80%** (`--cov-fail-under=80`), см. [06-testing-strategy.md](06-testing-strategy.md).

## Что НЕ используется

- Anthropic / Claude — запрещено (см. ADR-002).
- Очереди, кэш (Redis), брокеры — не нужны в v1 (NFR простоты).
- ORM-агностичные query builders помимо SQLAlchemy.
