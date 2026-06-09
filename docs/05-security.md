# 05 — Security

## Модель аутентификации

- Единый сервисный ключ `API_KEY` из `.env`. Клиент передаёт его в заголовке `X-API-Key`.
- Сравнение ключа — **constant-time** (`hmac.compare_digest` или `secrets.compare_digest`), чтобы исключить timing-атаки.
- Нет многопользовательской модели / RBAC между пользователями в v1 (см. [06-rbac.md модуля](modules/ai-chat/06-rbac.md)).
- `GET /healthz` (liveness) и `GET /health` (readiness) — единственные публичные endpoints без ключа (для healthcheck контейнера/Traefik/мониторинга, см. [07-deployment.md](07-deployment.md)). Они не раскрывают чувствительной информации (`{"status":"ok"|"degraded"}`).

Обоснование выбора API-key (вместо JWT/OAuth) — [ADR-003](adr/ADR-003-auth-api-key.md).

## Секреты

| Секрет | Источник | Примечание |
|---|---|---|
| `API_KEY` | `/opt/aichat/.env` (env приложения) | Ключ доступа к API |
| `OPENAI_API_KEY` | `/opt/aichat/.env` | Ключ OpenAI |
| `POSTGRES_PASSWORD` | `/opt/aichat/.env` | Пароль контейнера БД; единый источник пароля |
| `DATABASE_URL` | собирается Compose из `POSTGRES_*` | В compose-режиме в `.env` НЕ задаётся (см. 07-deployment §«Согласованность credentials БД»); вне compose — явно в env |
| `SSH_HOST` / `SSH_USER` / `SSH_PRIVATE_KEY` | GitHub Secrets | Доступ CI к серверу для деплоя; не прикладные секреты |

Правила:

- Секреты **только** из `.env` / переменных окружения. Никаких секретов в коде или в репозитории.
- `.env` — в `.gitignore`. В репозитории — `.env.example` с пустыми/placeholder значениями.
- Секреты **не попадают в Docker-образ** (передаются через `env_file` / environment в docker-compose в runtime, не через `ARG`/`ENV` в `Dockerfile`).
- Логи не должны содержать значений секретов и полного текста транскрибаций на уровне INFO (полный текст логируется только при необходимости отладки, на уровне DEBUG, выключенном в проде).

### Секреты в проде (общий сервер за Traefik)

См. [07-deployment.md](07-deployment.md) и [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md).

- Прикладной `.env` (`API_KEY`, `OPENAI_API_KEY`, `POSTGRES_PASSWORD` и пр.) лежит в
  `/opt/aichat/.env` на сервере: gitignored, untracked → CI его не перезаписывает.
- В **GitHub Secrets** хранятся ТОЛЬКО параметры SSH-доступа CI к серверу: `SSH_HOST`,
  `SSH_USER`, `SSH_PRIVATE_KEY`. Прикладные секреты в GitHub Secrets не помещаются.
- Репозиторий публичный (`github.com/eliseiv/6010`) — в коде/истории не должно быть ни
  одного реального секрета (только `.env.example` с placeholder'ами). Это усиливает
  правило «никаких секретов в репозитории».
- **SSH deploy-ключ:** приватный ключ — только в GitHub Secrets, публичный — в
  `authorized_keys` deploy-пользователя на сервере. Рекомендация: использовать
  отдельный (не персональный) ключ с ограниченными правами; при подозрении на
  компрометацию — немедленная ротация (удалить публичный ключ из `authorized_keys`,
  сгенерировать новую пару, обновить `SSH_PRIVATE_KEY`).
- TLS терминирует общий Traefik (Let's Encrypt, certresolver `le`); управление
  сертификатами вне нашего scope — на стороне edge (`/opt/edge`).

## Угрозы и меры (threat model, упрощённо)

| Угроза | Мера |
|---|---|
| Подбор/утечка API-ключа | Длинный случайный ключ (≥32 байта), constant-time сравнение, ротация через `.env` |
| Timing-атака на ключ | `secrets.compare_digest` |
| Утечка секретов через образ | Секреты в runtime env, не в образе; `.dockerignore` исключает `.env` |
| SQL-инъекция | SQLAlchemy с параметризованными запросами, без сырого конкатенированного SQL |
| Раскрытие данных через ошибки | Единый error handler: наружу — структурный объект ошибки без stack trace; детали — в логах |
| Abuse / стоимость OpenAI | Бюджет токенов (`CONTEXT_TOKEN_BUDGET`, `MAX_OUTPUT_TOKENS`), таймаут; rate limiting — TD-002 |
| Prompt injection через текст транскрибации | Системный prompt инструктирует не выполнять инструкции из текста как команды; пользовательский ввод и контекст разделены ролями. Остаточный риск зафиксирован — TD-004 |
| DoS большим телом запроса | Ограничение размера тела запроса (см. 02/07); валидация длины |

## Транспорт

- TLS терминируется на **общем Traefik** сервера (Let's Encrypt, entrypoint `websecure`,
  certresolver `le`) — вне scope сервиса, зафиксировано в [07-deployment.md](07-deployment.md)
  и [ADR-006](adr/ADR-006-prod-deploy-shared-traefik.md). Сервис слушает HTTP только внутри
  docker-сети (`expose: 8000`), не публикует портов 80/443 и не настраивает свой SSL.

## Encryption at rest

- Тела транскрибаций хранятся в БД в открытом виде (не PII-критично по умолчанию). Шифрование колонок — не в scope v1; при необходимости — см. TD-005.
