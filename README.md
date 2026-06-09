# ai-chat (aichat)

Сервис AI-чата по транскрипциям встреч. Прод: https://velunoapp.shop

Документация и операционные процедуры — в [`docs/`](docs/) (источник истины).
Деплой и CI/CD — см. [`docs/07-deployment.md`](docs/07-deployment.md).

## CD status

Автодеплой по push в `main` через GitHub Actions (`.github/workflows/deploy.yml`):
SSH на общий сервер → `git pull --ff-only` → `docker compose up -d --build` →
post-deploy healthcheck gate (`GET /healthz`) → авто-rollback при провале.

<!-- CD verify: 2026-06-09 — проверка прохождения автодеплоя и e2e на проде -->
