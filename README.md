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

#### Instrument details

`GET /instruments/{ticker}` — отдельный, read-only lookup по одному тикеру для страницы деталей инструмента (переход из watchlist по клику на тикер). В отличие от `GET /watchlist/quotes`, эта операция **не трогает БД и не создаёт database session** — это чистый market-data lookup, не связанный с watchlist persistence.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/instruments/AAPL" -Method Get
```

Пример ответа:

```json
{
  "ticker": "AAPL",
  "price": "213.45",
  "change": "2.31",
  "change_percent": "1.09",
  "open": "210.00",
  "high": "214.20",
  "low": "209.50",
  "previous_close": "211.14",
  "volume": 48213456,
  "as_of": "2026-08-10T20:00:00Z",
  "source": "twelvedata"
}
```

`open`/`high`/`low`/`previous_close`/`volume` берутся из того же `/quote`-ответа Twelve Data, который уже запрашивается для `GET /watchlist/quotes` — второй provider-эндпоинт не нужен. Любое из этих полей — `null` (никогда выдуманный `0`), если provider его не вернул или не удалось разобрать значение; `price`/`change`/`change_percent`/`as_of` обязательны — их отсутствие/некорректность превращает весь ответ в контролируемую ошибку, а не в частично заполненный объект.

Ошибки: некорректный `ticker` → `422`; тикер не поддерживается provider'ом → `404`; provider недоступен или rate limit → `503`; provider не ответил за 5 секунд → `504`. Ни один из этих ответов не содержит сырой payload provider'а, URL с ключом или текст исключения.

#### Instrument price history (chart)

`GET /instruments/{ticker}/history?period=1D` — исторические цены закрытия для графика на странице инструмента. Как и `GET /instruments/{ticker}`, это чистый read-only market-data lookup без database session.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/instruments/AAPL/history?period=1D" -Method Get
```

Пример ответа:

```json
{
  "ticker": "AAPL",
  "period": "1D",
  "source": "twelvedata",
  "points": [
    { "timestamp": "2026-08-10T13:30:00Z", "close": "306.74" },
    { "timestamp": "2026-08-10T13:35:00Z", "close": "306.62" }
  ]
}
```

**Поддерживаемые продуктовые периоды** — фиксированный набор, `1D` / `5D` / `1M`; frontend никогда не передаёт backend'у сырые Twelve Data параметры (`interval`/`outputsize`) напрямую — только один из этих трёх значений. Backend сам маппит период на provider-specific параметры официального `GET /time_series` endpoint (`https://twelvedata.com/docs#time-series`, проверено против реального free-tier аккаунта перед реализацией):

| Продуктовый период | Twelve Data `interval` | `outputsize` | Обоснование |
| --- | --- | --- | --- |
| `1D` | `5min` | 100 | покрывает полную ~6.5-часовую NYSE-сессию (~78 баров) с запасом |
| `5D` | `1h` | 40 | ~7 часовых баров/сессию × 5 сессий, с запасом на праздники |
| `1M` | `1day` | 25 | календарный месяц — обычно 21–23 торговых дня |

Запросы всегда идут с `timezone=UTC` (backend не угадывает таймзону биржи и DST-правила — это делает сам provider) и `order=asc` — но backend **не доверяет** порядку из ответа и всегда сортирует точки по `timestamp` ASC самостоятельно (регресс-тест на «development»-сценарий с намеренно перевёрнутым порядком провайдера).

`points` — только `timestamp`/`close`: полный OHLC/volume существует в provider-neutral `PricePoint` на уровне gateway, но текущий line-chart не использует остальные поля, поэтому наружу они не тащатся ("не тащить поля просто на будущее"). Пустой список `points` — контролируемый успешный ответ (`200`), не ошибка — фронтенд показывает «Нет данных за выбранный период».

Ошибки: некорректный `ticker` или `period` (не один из `1D`/`5D`/`1M`) → `422`; тикер не поддерживается provider'ом → `404`; provider недоступен/rate limit → `503`; timeout → `504`. Как и у `/instruments/{ticker}`, ни один ответ не содержит сырой provider payload/URL/exception text.

**Rate-limit дисциплина** (Twelve Data free-tier — `8 запросов/минуту`, `800/день`, уже реально исчерпывался в этом проекте): один запрос графика = один provider-запрос, никогда не один запрос на точку; при открытии страницы загружается только default-период (`1D`); `5D`/`1M` запрашиваются только по клику на кнопку периода; уже загруженный период не перезапрашивается повторно при повторном клике (кешируется на клиенте на время визита страницы); автоматических retry и prefetch всех периодов нет.

**Chart implementation decision.** График — небольшой собственный SVG-компонент (`frontend/src/components/PriceChart.tsx`), без новой зависимости: на момент этой задачи `frontend/package.json` содержит только `next`/`react`/`react-dom`, а требуемый график — одна line без zoom/pan/индикаторов/candlestick, для которой полноценная chart-библиотека (`lightweight-charts`, `Recharts`) добавляла бы canvas-рендеринг, императивный жизненный цикл или D3-зависимости без реальной необходимости. `ADR-0003` (раздел 12, 589) явно оставляет charting library предметом отдельной задачи по мере готовности vertical slice — это она и есть. Если будущая задача потребует zoom/pan/candlestick/индикаторы — это станет реальным основанием пересмотреть решение.

#### Instrument news

`GET /instruments/{ticker}/news` — новости по инструменту для страницы деталей, ниже графика цены. Read-only: новости нигде не сохраняются в PostgreSQL, каждый запрос — свежий provider-запрос.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/instruments/AAPL/news" -Method Get
```

Пример ответа:

```json
{
  "ticker": "AAPL",
  "source": "finnhub",
  "items": [
    {
      "id": "141175994",
      "headline": "Apple unveils new product line",
      "source": "Reuters",
      "published_at": "2026-08-10T20:00:00Z",
      "url": "https://finnhub.io/api/news?id=...",
      "summary": "Apple announced several new products today."
    }
  ]
}
```

**Provider — отдельное implementation decision, не Twelve Data.** Перед реализацией была проверена ТОЛЬКО официальная документация Twelve Data (полный список endpoints задокументирован и явно не содержит раздела "News"); единственный близкий по смыслу endpoint — `Press releases` (`/press_releases`, Fundamentals) — был проверен живым вызовом и оказался непригоден: в ответе нет ни `source`, ни `url` на оригинальную публикацию (оба — жёсткое требование этой задачи), а `body` — сырой HTML синдицированного, часто промо-контента, упоминающего тикер лишь мимоходом, а не реальная новость по инструменту. Это была явная STOP CONDITION задачи — production-код не писался до решения Product Owner. Были исследованы официальные альтернативы (Finnhub `company-news`, Alpha Vantage `NEWS_SENTIMENT`, Marketaux); **Product Owner выбрал Finnhub** как implementation decision для этой vertical slice (свой отдельный free-tier API key, `TRADING_AI_NEWS_API_KEY`, независимый от `TRADING_AI_MARKET_DATA_API_KEY`). Как и Twelve Data, это implementation choice, а не ADR-level commitment — `backend/src/trading_ai/market_data/types.py` (`InstrumentNewsItem`/`InstrumentNews`) provider-neutral, `backend/src/trading_ai/market_data/news_gateway.py` — единственное место, знающее про Finnhub/httpx.

`GET https://finnhub.io/api/v1/company-news?symbol=...&from=...&to=...` — подтверждён живым вызовом перед реализацией (заголовок `X-Finnhub-Token`, не query-параметр `token`, по той же причине, что и у Twelve Data). Free-tier: `60 запросов/минуту` (подтверждено через `X-Ratelimit-*` заголовки живого ответа), возвращает JSON-массив объектов `headline`/`source`/`datetime` (Unix seconds, UTC)/`url`/`summary`/`id` — сортировка newest-first по умолчанию (backend не доверяет и сортирует сам). Неизвестный/неподдерживаемый тикер отвечает `200 []`, не `404` — Finnhub эту разницу не делает, поэтому `GET /instruments/{ticker}/news` тоже никогда не возвращает `404`, только пустой `items`.

Backend запрашивает фиксированное окно (последние 7 дней) одним provider-запросом на загрузку страницы и обрезает результат до 10 новостей после сортировки — provider не поддерживает server-side `limit`. Каждый отдельный news item, у которого нет `headline`/`source`/валидного `published_at`, или чей `url` не проходит проверку схемы (`http://`/`https://` — `javascript:`/`data:`/`file:` и прочее отбрасываются), молча пропускается — один плохой item не роняет весь список.

Ошибки: некорректный `ticker` → `422`; provider недоступен/rate limit → `503`; timeout → `504`; malformed provider response → `503`. Ни один ответ не содержит сырой provider payload, URL с ключом или текст исключения.

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

#### Instrument details UI

Клик по тикеру в watchlist (обычная Next.js `<Link>`-навигация, не `window.location`) открывает `/instruments/{ticker}` — отдельную страницу с более подробной рыночной информацией по одному инструменту:

1. крупная цена и абсолютное/процентное изменение с явным знаком (не только цветом) в верхней части страницы;
2. `Open` / `High` / `Low` / `Previous close` / `Volume` / `Updated` / `Source` — сеткой ниже; любое значение, которого нет в ответе backend, показывается как «Данные недоступны», никогда `0`;
3. `← Назад к watchlist` — ссылка на `/`;
4. состояние загрузки, пока запрос к backend не завершился;
5. если запрос не удался (provider недоступен/rate limit/timeout/тикер не найден) — понятное сообщение на русском и кнопка «Повторить» (без автоматических бесконечных retry); остальная часть страницы (back-ссылка, disclaimer) остаётся доступной;
6. обновление страницы (`F5`) — данные запрашиваются заново (`cache: "no-store"`), как и в watchlist.

Страница не использует UI-библиотек, WebSocket, фонового опроса, новостей, fundamentals или portfolio/orders.

#### Price chart UI

Ниже карточки инструмента — секция «График цены»:

1. три кнопки периода — `1Д` / `5Д` / `1М` (настоящие `<button>`, активный период помечен `aria-pressed="true"` и визуально выделен); default при открытии страницы — `1Д`, загружается автоматически, `5Д`/`1М` — только по клику;
2. график — простая line-диаграмма цены закрытия, точки слева направо в хронологическом порядке;
3. под графиком — «Последняя цена: ... · Период: ... · Обновлено: ...»;
4. состояние загрузки и состояние ошибки графика **независимы** от карточки инструмента выше: сбой графика (rate limit/недоступность provider'а) никогда не скрывает уже загруженную карточку, и наоборот — обе секции показывают собственную ошибку с кнопкой «Повторить», не ломая друг друга (проверено вживую: реальный `429` free-tier во время верификации уронил карточку, при этом график продолжал работать, и оба независимо восстановились по «Повторить»);
5. пустой набор точек — «Нет данных за выбранный период», не пустой график и не `0`;
6. одна точка данных отображается как точка, а не сломанная линия; полностью плоские цены не приводят к делению на ноль — рисуется горизонтальная линия;
7. направление (рост/падение) никогда не передаётся только цветом — у SVG есть текстовый `aria-label`, а «Последняя цена»/цена и изменение в карточке выше уже текстовые;
8. без tooltip/hover, без zoom/pan, без технических индикаторов — вне минимального scope этой задачи;
9. responsive — график не может выйти за пределы viewport на любой ширине экрана (`overflow: hidden` контейнер, `width: 100%` SVG).

#### Instrument news UI

Ниже графика цены — секция «Новости», до 10 карточек, newest-first:

1. каждая карточка — headline, краткое summary (только если provider реально его вернул — иначе строки просто нет, никогда не подставляется пустой текст), «Источник · время публикации», ссылка «Открыть источник →»;
2. ссылка — обычный `<a href>` с `target="_blank"` и `rel="noopener noreferrer"`, ведёт напрямую на оригинальную публикацию; backend не проксирует и не отдаёт HTML статьи — только валидированный `http(s)://` URL;
3. загрузка новостей — ровно один раз при открытии страницы инструмента; без polling, без auto-refresh, без prefetch из watchlist;
4. состояние загрузки/ошибки новостей **независимо** от карточки инструмента и графика: сбой любой из трёх секций не скрывает уже загруженные данные в других (проверено вживую: реальный `429` уронил график после `F5`, карточка инструмента и все 10 новостей продолжали отображаться без изменений; отдельно — контролируемый forced-error тест подтвердил, что «Повторить» в секции новостей восстанавливает именно её, не трогая остальные);
5. пустой список — «Свежих новостей по инструменту нет.»; ошибка provider'а — «Новости сейчас недоступны.» с кнопкой «Повторить»;
6. без бесконечного scroll, без image-heavy layout, без sentiment-цветов, без AI-меток — вне минимального scope этой задачи.

Следующий планируемый блок — см. `.ai-context/CURRENT_STATE.md`.
