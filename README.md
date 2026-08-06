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

Минимальный запускаемый каркас backend и frontend без бизнес-функций (`ADR-0001`, `ADR-0002`, `ADR-0003`). PostgreSQL, очередь, LLM-интеграция и авторизация ещё не подключены.

### Backend (CPython 3.14, FastAPI)

```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# запуск dev-сервера
fastapi dev src/trading_ai/main.py

# тесты
python -m pytest -v

# type-check
python -m mypy src tests
```

Health-проверка: `GET http://127.0.0.1:8000/health` → `{"status": "ok"}`.

Конфигурация читается из переменных окружения (`TRADING_AI_ENVIRONMENT`, `TRADING_AI_LOG_LEVEL`, `TRADING_AI_HOST`, `TRADING_AI_PORT`, `TRADING_AI_DEBUG`) — значений по умолчанию для секретов нет, секретов в репозитории нет.

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
