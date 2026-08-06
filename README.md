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
$env:TRADING_AI_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/trading_ai"
```

`TRADING_AI_DATABASE_URL` **не обязательна для запуска приложения**: `from trading_ai.main import app` и `GET /health` работают и без неё. Она обязательна только для реального доступа к БД — `GET /ready` (иначе вернёт `503`) и для команд Alembic (иначе — контролируемая ошибка, а не попытка подключения с пустым URL).

#### `/health` и `/ready`

- `GET /health` — лёгкий liveness-сигнал. Не обращается к БД и ни к какой другой зависимости, не требует `TRADING_AI_DATABASE_URL`. Отвечает `{"status": "ok"}`, пока жив процесс.
- `GET /ready` — readiness-сигнал. Если `TRADING_AI_DATABASE_URL` не задан — сразу `503 {"status": "unavailable"}` (engine не создаётся). Если задан — выполняет один безопасный запрос `SELECT 1` к PostgreSQL через async SQLAlchemy/asyncpg: при успехе `200 {"status": "ok"}`, при недоступности БД `503 {"status": "unavailable"}`. Ни в одном случае ответ не раскрывает connection string, хост, имя пользователя, текст SQL-ошибки или stack trace. Не запускает миграции и не создаёт схему.

#### PostgreSQL и миграции (Alembic)

Реальный сервер PostgreSQL в рамках этой задачи не поднимается автоматически — пользователь запускает его локально самостоятельно (Docker/Compose здесь не создаются, это предмет отдельной задачи). База данных не создаёт схему автоматически — это выполняется явно через Alembic. В отличие от самого приложения, Alembic **всегда** требует `TRADING_AI_DATABASE_URL` — без неё команды ниже завершатся понятной ошибкой, а не попыткой подключения с пустым URL:

```
# применить все миграции
python -m alembic upgrade head

# откатить последнюю миграцию
python -m alembic downgrade -1

# показать текущую применённую ревизию
python -m alembic current
```

Baseline-миграция (`0001_initial_baseline`) не создаёт ни одной бизнес-таблицы — она только устанавливает рабочую цепочку миграций для будущих задач.

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
