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

`POST /watchlist`, `GET /watchlist`, `DELETE /watchlist/{item_id}` — сквозной business use case поверх реального PostgreSQL (миграция `0002_watchlist_items`, таблица `watchlist_items`): domain-модель → application use case → repository → PostgreSQL, полностью за FastAPI-адаптером (`ADR-0002`, раздел 17). Это **не** полная бизнес-модель платформы — только минимальный вертикальный срез (добавить тикер, получить список, удалить по id, запретить дубликаты), демонстрирующий рабочий путь от HTTP до БД и обратно для будущих доменных областей.

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

# удалить по id (id — значение из ответа POST/GET выше) -> HTTP 204, без тела ответа
Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist/1" -Method Delete

# повторное удаление того же id -> HTTP 404
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist/1" -Method Delete
} catch {
    Write-Host "status=$([int]$_.Exception.Response.StatusCode) body=$($_.ErrorDetails.Message)"
}
```

Пустой/некорректный `ticker` (не только буквы/цифры/`.`/`-`, длиннее 15 символов) → `422`. Удаление всегда по числовому `id` (не по `ticker`) — успех отвечает `204 No Content` без тела, отсутствующий `id` → `404`, нечисловой `item_id` в пути → стандартный FastAPI `422`. Ответ никогда не содержит SQL-текста ошибки или stack trace — только `{"detail": "..."}`.

#### Market data для watchlist

`GET /watchlist/quotes` возвращает те же записи watchlist, что и `GET /watchlist`, плюс лучшую доступную рыночную котировку на каждый тикер: `price`, `change`, `change_percent`, `as_of`, `source`. Это **read-only** отображение — только для просмотра, **не торговое исполнение и не рекомендация**; market data нигде не сохраняется в `watchlist_items` и не является source of truth для watchlist (persistence watchlist не меняется этой задачей).

**Provider — implementation decision, не архитектурное решение.** Конкретный market data provider не был предметом утверждённого ADR и явно отмечен неутверждённым в `.ai-context/CURRENT_STATE.md`. Как implementation decision для этого vertical slice выбран [Twelve Data](https://twelvedata.com/docs) — официальный документированный REST API, без scraping и reverse-engineered endpoints, с бесплатным tier. Смена provider в будущем не требует переписывать watchlist: `backend/src/trading_ai/market_data/types.py` — provider-neutral контракт (`MarketQuote`, error taxonomy), `backend/src/trading_ai/market_data/gateway.py` — единственное место, знающее про Twelve Data/httpx (по аналогии с `llm_gateway` adapter-слоем из `ADR-0007`, раздел 22).

```powershell
# один раз: получить бесплатный API key на twelvedata.com и добавить в окружение
$env:TRADING_AI_MARKET_DATA_API_KEY = "<ваш ключ>"

# получить watchlist с котировками
Invoke-RestMethod -Uri "http://127.0.0.1:8000/watchlist/quotes" -Method Get
```

Требования:

- `TRADING_AI_MARKET_DATA_API_KEY` **опциональна** для запуска приложения — без неё всё остальное API работает как обычно, только `GET /watchlist/quotes` отвечает `503 {"detail": "market data is not configured"}`;
- ключ передаётся provider'у только через HTTP-заголовок (`Authorization: apikey ...`), никогда как query-параметр URL — так он не попадает в логи HTTP-библиотек по умолчанию;
- ключ никогда не логируется, не возвращается в API-ответе, не передаётся во frontend/browser — только backend обращается к provider'у;
- один нерабочий тикер/provider-сбой не роняет весь список: элемент получает `"quote_error"` (`"timeout"`, `"rate_limited"`, `"unsupported"`, `"unavailable"`) вместо `price`/`change`/`as_of`, а не `0` и не выдуманные данные;
- provider-запрос ограничен таймаутом (5 секунд), без автоматических retry;
- тикеры запрашиваются последовательно, не параллельным веером — у Twelve Data нет официально документированного multi-symbol quote endpoint на базовом плане.

#### CORS

Backend по умолчанию **не** разрешает cross-origin запросы браузера. `main.py` включает минимальный `CORSMiddleware`, без credentials (`allow_credentials=False`), только `GET`/`POST`/`DELETE`, только `Content-Type` в разрешённых заголовках; список origins задаётся через `TRADING_AI_CORS_ORIGINS` (парсинг централизован в `config.py`) — **не** захардкожен в `main.py`.

- `TRADING_AI_CORS_ORIGINS` — comma-separated список origins (значения обрезаются от пробелов, пустые элементы отбрасываются);
- локальный default (если переменная не задана) — `http://localhost:3000,http://127.0.0.1:3000` (локальный frontend-dev-сервер);
- production origins задаются той же переменной в production-окружении — это отдельная deployment-конфигурация, а не значение по умолчанию из кода (`ADR-0002`, раздел 13);
- `allow_origins=["*"]` не используется никогда;
- credentials (cookies/auth headers) не используются и не планируются этим механизмом.

```powershell
# пример переопределения для production/staging
$env:TRADING_AI_CORS_ORIGINS = "https://app.example.com,https://admin.example.com"
```

### Frontend (TypeScript strict, React, Next.js App Router)

Frontend — отдельный клиент FastAPI Application API (`ADR-0003`): не обращается к БД, market/news API или LLM напрямую, только к backend через HTTP.

```powershell
cd frontend
npm install

# один раз: создать локальный .env.local (не коммитится)
Copy-Item ".env.example" ".env.local"
# по умолчанию NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 — подходит, если backend запущен локально на этом порту

# dev-сервер
npm run dev

# type-check
npm run type-check

# production build
npm run build
```

`NEXT_PUBLIC_API_BASE_URL` — публичный (не секретный) browser-side URL backend'а: префикс `NEXT_PUBLIC_` означает, что Next.js встраивает значение в клиентский bundle (`ADR-0003`, раздел 25). `frontend/.env.example` документирует переменную и отслеживается git; `frontend/.env.local` — реальный локальный файл, гitignored, никогда не коммитится. Если переменная не задана, API-клиент (`frontend/src/lib/watchlist-api.ts`) использует тот же development-default — заданный в одном централизованном месте, а не захардкоженный в компонентах.

#### Watchlist UI

После того как Postgres (см. выше) и backend (`fastapi dev src/trading_ai/main.py`, `127.0.0.1:8000`) запущены, а frontend — на `http://localhost:3000`:

1. открыть `http://localhost:3000` — отображается текущий watchlist (или пустое состояние: «Watchlist пуст. Добавьте первый тикер выше.»);
2. ввести тикер (например, `AAPL`) в поле «Тикер» и нажать «Добавить» (или Enter) — запись появляется в списке без перезагрузки страницы;
3. повторное добавление того же тикера → понятная ошибка «Такой тикер уже есть в списке.» рядом с формой;
4. пустой ввод → «Введите тикер.»;
5. кнопка «Удалить» у каждой записи — удаляет именно эту запись (без `window.confirm`) и убирает её из списка только после подтверждённого `204` от backend (без optimistic removal); во время удаления кнопка этой записи показывает «Удаление…» и отключена, остальной интерфейс остаётся доступен;
6. если удаление не удалось — запись остаётся в списке, ошибка показывается через `role="alert"`;
7. перезагрузка страницы (`F5`) — добавленный тикер остаётся, удалённый не возвращается: список реально читается из PostgreSQL при каждой загрузке (`cache: "no-store"`);
8. если backend недоступен — «Не удалось соединиться с сервером...» и кнопка «Повторить» (без автоматических бесконечных retry);
9. рядом с каждым тикером — реальная цена (`$213.45`), абсолютное и процентное дневное изменение с явным знаком `+`/`-`/`±` в тексте (не только цветом) и время последней котировки («Обновлено: 17:42»);
10. если котировка недоступна (provider timeout/rate limit/неизвестный тикер/сбой) — «Данные недоступны», никогда `0` и никогда придуманные числа;
11. кнопка «Обновить данные» — одноразовая ручная перезагрузка списка и котировок; автоматического опроса/polling нет.

Frontend не создаёт своего backend-эндпоинта — использует только существующие `GET /watchlist`, `POST /watchlist`, `DELETE /watchlist/{id}`, `GET /watchlist/quotes`. Редактирование записей UI не поддерживает — этого не поддерживает и backend. Market data — только отображение: **не торговое исполнение и не рекомендация**.
