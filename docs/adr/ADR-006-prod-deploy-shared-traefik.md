# ADR-006 — Прод-развёртывание за общим Traefik на shared-сервере

- Статус: Accepted
- Дата: 2026-06-09
- Контекст модуля: ai-chat (весь сервис)

## Context

Сервис `ai-chat` нужно вывести в прод. Целевая среда — **общий** сервер Ubuntu 22.04
(IP `87.239.135.154`), на котором уже работают другие сервисы и **общий reverse-proxy
Traefik** (каталог `/opt/edge`, управляется владельцем сервера). Traefik:

- терминирует TLS и сам выпускает/продлевает Let's Encrypt-сертификаты
  (certresolver `le` на entrypoint `websecure`, порты 80/443 заняты им);
- маршрутизирует входящий трафик к контейнерам, подключённым к общей внешней
  docker-сети `web` (external, уже создана), по docker labels на сервисе.

Ранее (ADR-001, 07-deployment) подразумевался «свой» VPS с собственным reverse-proxy
(nginx/Caddy) рядом с сервисом. Реальная среда отличается: proxy общий и нами не
управляется. Нужно зафиксировать как именно сервис интегрируется, не ломая чужие
сервисы и edge.

## Decision

1. **Сервис не управляет TLS и не публикирует порты 80/443.** TLS, ACME и публикация
   наружу — целиком на общем Traefik. Каталог `/opt/edge` мы НЕ трогаем.

2. **Маршрут объявляется через docker labels на сервисе `api`** (Traefik
   service/router name = `aichat`, домен = apex `velunoapp.shop`):
   - `traefik.enable=true`
   - `traefik.http.routers.aichat.rule=Host(`velunoapp.shop`)`
   - `traefik.http.routers.aichat.entrypoints=websecure`
   - `traefik.http.routers.aichat.tls.certresolver=le`
   - `traefik.http.services.aichat.loadbalancer.server.port=8000`

3. **Подключение к общей внешней сети `web`** (`external: true`). `api` входит в две
   сети: `web` (для Traefik) и внутреннюю `default`/`appnet` (для доступа к БД).
   `db` — **только** во внутренней сети, без портов наружу.

4. **Топология compose-файлов:**
   - `docker-compose.yml` — базовый, expose-only, без публикации портов и без сети
     `web` (инвариант: наружу ничего не публикует);
   - `docker-compose.prod.yml` — прод-overlay: объявляет сеть `web` как external,
     добавляет Traefik labels на `api` и подключает `api` к `web` + внутренней сети;
   - `docker-compose.override.yml` — dev-overlay (проброс `8000:8000` на localhost),
     на сервере **не применяется**.

5. **Прод-деплой использует ЯВНЫЕ файлы**, чтобы dev-override не подхватился:
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

6. **CI/CD:** GitHub Actions по push в `main` → SSH на сервер → в `/opt/aichat`
   выполняет `git pull` + прод-команду выше. Репозиторий публичный
   (`github.com/eliseiv/6010`) → сервер тянет по HTTPS, отдельный токен доступа к
   GitHub не нужен.

7. **Изоляция каталога `/opt/aichat`.** Весь сервис (репозиторий, `.env`, volume БД)
   живёт в `/opt/aichat`. Edge (`/opt/edge`) и чужие сервисы не затрагиваются.

8. **Liveness-проба `GET /healthz`** добавляется как endpoint без auth, не зависящий
   от БД, для Traefik/контейнерного healthcheck/внешнего мониторинга. Отделена от
   `GET /health` (readiness c проверкой БД). См. 02-api-contracts / 03-architecture.

## Consequences

Плюсы:
- Нулевая ответственность за TLS/ACME и за публикацию портов — это даёт edge.
- Не конфликтуем с чужими сервисами: общий контракт — только сеть `web` и labels.
- Dev и prod строго разделены явными compose-файлами; dev-override не утечёт в прод.
- Публичный репозиторий упрощает CI: не нужен deploy-key к GitHub.

Минусы / ограничения:
- Зависимость от чужой конфигурации Traefik (entrypoint `websecure`, certresolver
  `le`, сеть `web`). Если владелец переименует их — деплой сломается. Зафиксировано
  как внешний контракт в 07-deployment.
- A-запись `velunoapp.shop` → `87.239.135.154` должна существовать до первого деплоя,
  иначе ACME-челлендж Let's Encrypt не пройдёт. Запись настраивает владелец домена.
- Несколько сервисов за одним Traefik → отказ edge затрагивает всех (вне нашего scope).

## Alternatives

- **Собственный reverse-proxy (nginx/Caddy) в нашем compose** — отклонено: порты
  80/443 заняты общим Traefik, два proxy на одном хосте конфликтуют; дублирование
  TLS/ACME-логики.
- **Публикация порта `api` напрямую на хост + проксирование Traefik по host-порту** —
  отклонено: лишняя экспозиция порта, обходит модель docker-сетей Traefik, хуже
  изоляция.
- **Отдельный выделенный VPS только под сервис** — отклонено: дороже и избыточно для
  одного небольшого сервиса; общий сервер уже доступен.

## Связь с другими ADR

Уточняет deployment-часть [ADR-001](ADR-001-stack-and-topology.md) (монолит +
PostgreSQL в Docker остаётся в силе; меняется только способ публикации наружу:
общий Traefik вместо абстрактного «reverse-proxy на VPS»). ADR-001 не отменяется.
