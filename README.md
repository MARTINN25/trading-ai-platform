# AI Trading Assistant Platform

Production-платформа персонального AI-ассистента для трейдинга, предназначенная для сбора, нормализации и анализа рыночной информации, формирования прозрачных русскоязычных инсайтов и поддержки решений пользователя.

## Текущий статус

Проект находится на этапе проектирования и инженерной документации. Бизнес-код ещё не разрабатывается.

## Роли

- **Product Owner** — пользователь.
- **Solution Architect / CTO** — ChatGPT.
- **Senior Software Engineer** — Claude.

ChatGPT формирует архитектурные предложения и проводит архитектурное ревью. Claude выполняет утверждённые задачи в рамках этих предложений. Действующими источниками истины являются утверждённые документы репозитория и ADR — память AI-агентов и содержание отдельных чатов источником истины не являются.

Подробное описание миссии, целей, ролей и правил проекта — в [PROJECT_CHARTER.md](./PROJECT_CHARTER.md).

## Принципы

- Architecture First
- Documentation First
- Code Last
- Single Source of Truth
- минимально необходимые и обратимые решения

## Структура репозитория

```
PROJECT_CHARTER.md   — устав проекта (источник истины по ролям и правилам)
README.md            — данный файл
docs/architecture/    — архитектурные материалы
docs/decisions/       — Architecture Decision Records (ADR)
docs/processes/       — инженерные процессы и регламенты
```

## Для новых участников

Перед началом работы необходимо прочитать `PROJECT_CHARTER.md`, а также документы, перечисленные в конкретной задаче.

## Работа с Git

Прямые изменения в `main` запрещены. Работа выполняется в отдельных короткоживущих ветках.

## Локальный запуск (Implementation Bootstrap)

Минимальный запускаемый каркас backend и frontend без бизнес-функций (`ADR-0001`, `ADR-0002`, `ADR-0003`, `ADR-0004`). Очередь, LLM-интеграция и авторизация ещё не подключены. PostgreSQL persistence — минимальный инфраструктурный bootstrap (engine/session/health + Alembic), без бизнес-таблиц.

### Backend (CPython 3.14, FastAPI)

```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# запуск dev-сервера
fastapi dev src/trading_ai/main.py

# тесты (не требуют реально запущенный PostgreSQL)
python -m pytest -v

# type-check
python -m mypy src tests
```

Конфигурация читается из переменных окружения (`TRADING_AI_ENVIRONMENT`, `TRADING_AI_LOG_LEVEL`, `TRADING_AI_HOST`, `TRADING_AI_PORT`, `TRADING_AI_DEBUG`, `TRADING_AI_DATABASE_URL`) — значений по умолчанию для секретов нет, секретов в репозитории нет.

`backend/.env.example` документирует переменные, но **копирование `.env.example` в `.env` само по себе ничего не делает** — в проекте нет dotenv-loader (например, `python-dotenv`), поэтому файл `.env` не подхватывается автоматически. Переменные должны быть реально заданы в окружении процесса, например явно в PowerShell:

```powershell
$env:TRADING_AI_DATABASE_URL = "postgresql+asyncpg://user:password@127.0.0.1:55432/trading_ai"
```

`TRADING_AI_DATABASE_URL` **не обязательна для запуска приложения**: `from trading_ai.main import app` и `GET /health` работают и без неё. Она обязательна только для реального доступа к БД — `GET /ready` (иначе вернёт `503`) и для команд Alembic (иначе — контролируемая ошибка, а не попытка подключения с пустым URL).

#### `/health` и `/ready`

- `GET /health` — лёгкий liveness-сигнал. Не обращается к БД и ни к какой другой зависимости, не требует `TRADING_AI_DATABASE_URL`. Отвечает `{"status": "ok"}`, пока жив процесс.
- `GET /ready` — readiness-сигнал. Если `TRADING_AI_DATABASE_URL` не задан — сразу `503 {"status": "unavailable"}` (engine не создаётся). Если задан — выполняет один безопасный запрос `SELECT 1` к PostgreSQL через async SQLAlchemy/asyncpg: при успехе `200 {"status": "ok"}`, при недоступности БД `503 {"status": "unavailable"}`. Ни в одном случае ответ не раскрывает connection string, хост, имя пользователя, текст SQL-ошибки или stack trace. Не запускает миграции и не создаёт схему.

#### Локальный PostgreSQL через Docker Compose

`compose.yaml` в корне репозитория поднимает только сам PostgreSQL-сервер для локальной разработки (`ADR-0008`, раздел 23: именованный volume, `pg_isready`-healthcheck). Это **не** production-модель из `ADR-0008` (backend/frontend/worker/PostgreSQL/reverse proxy) — она остаётся предметом отдельной задачи. Dockerfile здесь не создаётся, бизнес-схема не создаётся.

PostgreSQL публикуется **только на loopback** (`127.0.0.1`), никогда на `0.0.0.0`/`[::]`, и **не** на порту `5432` по умолчанию — host-порт по умолчанию `55432` (переменная `POSTGRES_HOST_PORT`), чтобы не конфликтовать с уже установленным нативно на машине разработчика PostgreSQL (если он слушает `5432`). `5432` в `compose.yaml` — это только внутренний, container-side порт самого PostgreSQL и наружу напрямую не публикуется.

```powershell
# один раз: скопировать пример и задать реальный локальный пароль
Copy-Item ".env.compose.example" ".env.compose"
# отредактировать .env.compose — задать POSTGRES_PASSWORD (и, при необходимости, POSTGRES_HOST_PORT)

# поднять PostgreSQL в фоне
docker compose --env-file .env.compose up -d

# дождаться healthy
docker compose --env-file .env.compose ps

# обычная остановка — данные сохраняются в volume trading_ai_postgres_data
docker compose --env-file .env.compose down
```

`docker compose ps` должен показывать публикацию вида `127.0.0.1:55432->5432/tcp`.

**Удаление данных.** `docker compose --env-file .env.compose down -v` — это **не** повседневная команда остановки: флаг `-v` удаляет именованный volume `trading_ai_postgres_data` вместе со всеми локальными данными PostgreSQL безвозвратно. Используйте её осознанно, только когда действительно нужно стереть локальную БД и начать с чистого состояния:

```powershell
# ВНИМАНИЕ: удаляет volume trading_ai_postgres_data и все локальные данные PostgreSQL безвозвратно
docker compose --env-file .env.compose down -v
```

`.env.compose` — это отдельный механизм от `TRADING_AI_DATABASE_URL`: он используется Compose только для интерполяции значений в `compose.yaml` (пользователь/пароль/база/host-порт самого контейнера PostgreSQL), а не читается приложением (`ADR-0008`, раздел 29). После того как контейнер поднят, `TRADING_AI_DATABASE_URL` для приложения задаётся отдельно, использует host-порт `55432` (а не `5432`) и должна использовать те же значения, что и `.env.compose`:

```powershell
$env:TRADING_AI_DATABASE_URL = "postgresql+asyncpg://trading_ai:<пароль из .env.compose>@127.0.0.1:55432/trading_ai"
```

`.env.compose` содержит реальный (пусть и только локальный) пароль и поэтому не отслеживается git (`.gitignore`); в репозитории закоммичен только `.env.compose.example`.

Нативный Windows-Python (`backend/.venv`) подключается к этому PostgreSQL через `127.0.0.1:55432` напрямую, без каких-либо дополнительных обходов — Alembic, dev-сервер (`fastapi dev`) и опциональный integration-тест были явно проверены таким образом.

#### Миграции (Alembic)

База данных не создаёт схему автоматически — это выполняется явно через Alembic. В отличие от самого приложения, Alembic **всегда** требует `TRADING_AI_DATABASE_URL` — без неё команды ниже завершатся понятной ошибкой, а не попыткой подключения с пустым URL:

```
# применить все миграции
python -m alembic upgrade head

# откатить последнюю миграцию
python -m alembic downgrade -1

# показать текущую применённую ревизию
python -m alembic current
```

Baseline-миграция (`0001_initial_baseline`) не создаёт ни одной бизнес-таблицы — она только устанавливает рабочую цепочку миграций для будущих задач. `0002_watchlist_items` — первая бизнес-таблица (`watchlist_items`, см. ниже).

#### Интеграционный тест против реального PostgreSQL

`tests/integration/test_database_integration.py` пропускается по умолчанию (не блокирует обычный прогон `pytest -v`) и не угадывает креды сам. Запускается опционально, отдельной переменной `TRADING_AI_TEST_DATABASE_URL` (независимой от `TRADING_AI_DATABASE_URL` дев-сервера):

```powershell
$env:TRADING_AI_TEST_DATABASE_URL = "postgresql+asyncpg://trading_ai:<пароль из .env.compose>@127.0.0.1:55432/trading_ai"
python -m pytest -v -m integration tests/integration
```

Тест выполняет только `GET /ready`, то есть один безопасный `SELECT 1` — миграции не запускает и схему не создаёт.

#### Watchlist — первый вертикальный slice

`POST /watchlist` и `GET /watchlist` — первый маленький сквозной business use case поверх реального PostgreSQL (миграция `0002_watchlist_items`, таблица `watchlist_items`): domain-модель → application use case → repository → PostgreSQL, полностью за FastAPI-адаптером (`ADR-0002`, раздел 17). Это **не** полная бизнес-модель платформы — только минимальный вертикальный срез (добавить тикер, получить список, запретить дубликаты), демонстрирующий рабочий путь от HTTP до БД и обратно для будущих доменных областей.

```powershell
# добавить тикер (нормализуется: trim + uppercase)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist" -Method Post -ContentType "application/json" -Body '{"ticker":"aapl"}'
# -> { id, ticker: "AAPL", created_at }

# получить список
Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist" -Method Get

# повторное добавление того же тикера -> HTTP 409 (Invoke-RestMethod бросает исключение на 409)
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist" -Method Post -ContentType "application/json" -Body '{"ticker":"AAPL"}'
} catch {
    Write-Host "status=$([int]$_.Exception.Response.StatusCode) body=$($_.ErrorDetails.Message)"
}
```

Пустой/некорректный `ticker` (не только буквы/цифры/`.`/`-`, длиннее 15 символов) → `422`. Ответ никогда не содержит SQL-текста ошибки или stack trace — только `{"detail": "..."}`.

### Frontend (TypeScript strict, React, Next.js App Router)

```
cd frontend
npm install

# dev-сервер
npm run dev

# type-check
npm run type-check

# production build
npm run build
```

Frontend не обращается к backend, БД или внешним API — это будет добавлено отдельными задачами.
