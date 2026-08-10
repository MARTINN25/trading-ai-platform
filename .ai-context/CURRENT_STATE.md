# Current Project State

**Статус:** Утверждён
**Владелец:** Product Owner
**Дата последнего изменения:** 2026-08-10
**Назначение:** предоставить AI-агентам краткий актуальный контекст перед началом задачи.

Это оперативный, не архитектурный источник состояния (см. `docs/processes/DOCUMENTATION_STANDARD.md`, раздел 3). При расхождении с `PROJECT_CHARTER.md` или утверждёнными ADR приоритет имеют они.

---

## 1. Проект

AI Trading Assistant Platform.

## 2. Текущая фаза

Инженерный и документационный фундамент.

## 3. Что уже утверждено

- `PROJECT_CHARTER.md`
- `README.md`
- `.gitattributes`
- `docs/processes/GIT_WORKFLOW.md`
- `docs/processes/DOCUMENTATION_STANDARD.md`
- `docs/DOCUMENT_REGISTER.md`
- `.ai-context/CURRENT_STATE.md`
- `templates/CLAUDE_TASK_TEMPLATE.md`
- `docs/processes/ADR_PROCESS.md`
- `templates/ADR_TEMPLATE.md`
- `docs/architecture/ENGINEERING_PRINCIPLES.md`
- `docs/product/PRODUCT_SCOPE.md`
- `docs/product/FUNCTIONAL_REQUIREMENTS.md`
- `docs/product/NON_FUNCTIONAL_REQUIREMENTS.md`
- `docs/product/USER_JOURNEYS.md`
- `docs/architecture/LOGICAL_ARCHITECTURE.md`
- `docs/architecture/MODULE_BOUNDARIES.md`
- `docs/architecture/DATA_FLOWS.md`
- `docs/architecture/FAILURE_MODEL.md`
- `docs/architecture/TECHNOLOGY_EVALUATION.md`
- `docs/decisions/ADR-0001-backend-language-and-runtime.md`
- `docs/decisions/ADR-0002-backend-api-adapter.md`
- `docs/decisions/ADR-0003-frontend-stack.md`
- `docs/decisions/ADR-0004-primary-data-store.md`
- `docs/decisions/ADR-0005-vector-search-strategy.md`
- `docs/decisions/ADR-0006-background-jobs-and-queue.md`
- `docs/decisions/ADR-0007-llm-provider-integration.md`
- `docs/decisions/ADR-0008-containerization-and-single-server-deployment.md`
- `docs/decisions/ADR-0009-observability.md`

DOC-0007 и DOC-0008 составляют единый блок управления документацией; DOC-0009 и DOC-0010 составляют единый блок архитектурного управления; PROD-0001 и PROD-0002 составляют единый блок продуктового фундамента; ARCH-0001, ARCH-0002 и ARCH-0003 составляют единый блок логической архитектуры и её синхронизации; ARCH-0004, ARCH-0005 и ARCH-0006 составляют единый блок сравнительной оценки технологий и её финализации; ADR-0001 и ADR-0001-FINAL составляют единый блок выбора и формального утверждения backend runtime; ADR-0002 и ADR-0002-FINAL составляют единый блок выбора и формального утверждения backend API adapter; ADR-0003, ADR-0003-R1, ADR-0003-R2 и ADR-0003-FINAL составляют единый блок выбора, исправления и формального утверждения frontend stack; ADR-0004 и ADR-0004-FINAL составляют единый блок выбора и формального утверждения основного транзакционного хранилища; ADR-0005 и ADR-0005-FINAL составляют единый блок определения и формального утверждения стратегии векторного поиска; ADR-0006 и ADR-0006-FINAL составляют единый блок определения и формального утверждения стратегии фоновых задач и очереди; ADR-0007 и ADR-0007-FINAL составляют единый блок выбора и формального утверждения стратегии интеграции LLM-провайдера; ADR-0008 и ADR-0008-FINAL составляют единый блок определения и формального утверждения контейнеризации и single-server deployment; ADR-0009, ADR-0009-R1 и ADR-0009-FINAL составляют единый блок определения, исправления и формального утверждения observability strategy.

## 4. Что находится на ревью в текущей задаче

Instrument Price History Vertical Slice (ветка `feat/instrument-price-history`) — исторический график цены на `/instruments/{ticker}`, ниже существующей карточки инструмента:

- **Twelve Data официальный `GET /time_series`** (`https://twelvedata.com/docs#time-series`) — подтверждён против документации и живого free-tier аккаунта перед реализацией (не угадывался по памяти); поддерживает `interval`, `outputsize` (1–5000), `order` (`asc`/`desc`), `timezone` (в т.ч. `UTC`); по умолчанию `desc`, поэтому backend **не доверяет** порядку из ответа и всегда сортирует точки по `timestamp` ASC сам;
- **Продуктовые периоды — фиксированный enum `1D`/`5D`/`1M`**, никогда сырые Twelve Data `interval`/`outputsize` наружу; backend сам маппит: `1D→5min×100`, `5D→1h×40`, `1M→1day×25` (обоснование — README, «Instrument price history»); free-tier (`8 запросов/минуту`, `800/день`) поддержал все три интервала в живых вызовах — упрощать набор периодов не понадобилось;
- `backend/src/trading_ai/market_data/types.py` — добавлены `PricePoint` (полный OHLCV, честно `None` для отсутствующих provider-полей), `InstrumentHistoryPeriod` (enum), `PriceHistory` (ticker/period/source/points), `InvalidPeriodError` + `normalize_period()` (мирроит `InvalidTickerError`/`normalize_ticker`, не `MarketDataError` — это request-validation, а не provider-call failure);
- `backend/src/trading_ai/market_data/gateway.py` — `TwelveDataGateway.get_price_history()`; общий `_get()`-helper для HTTP GET (переиспользуется `/quote` и `/time_series`), общий `_validate_payload()` для статус-кодов/error-shape; сортировка ASC — defensive, не просто request-hint;
- `backend/src/trading_ai/market_data/use_cases.py` — `GetInstrumentPriceHistory`, зависит только от gateway, **не создаёт database session**, не персистит исторические данные;
- `backend/src/trading_ai/api/routes/instruments.py` — `GET /instruments/{ticker}/history?period=1D`; `422` невалидный ticker/period, `404` unsupported ticker, `503` unavailable/rate-limit/malformed, `504` timeout; пустой `points` — `200`, не ошибка; ответ содержит только `timestamp`/`close` (не весь OHLCV — "не тащить поля на будущее");
- frontend: `instrument-api.ts` расширен (`InstrumentHistoryPeriod`/`InstrumentHistoryPoint`/`InstrumentPriceHistory`, `getInstrumentPriceHistory()` — один HTTP-запрос на вызов, без автоматического retry); **новый `PriceChart.tsx`** — небольшой собственный SVG line-chart, **без новой npm-зависимости** (сравнение с `lightweight-charts`/`Recharts` и обоснование выбора — README, «Chart implementation decision»); **новый `PriceChartSection.tsx`** — кнопки периода (`aria-pressed`), independent loading/error/retry state от карточки инструмента (сбой одного не ломает другой — подтверждено вживую реальным `429`), client-side кеш уже загруженных периодов на время визита страницы;
- rate-limit дисциплина: один chart-запрос = один provider-запрос; при открытии страницы грузится только default (`1D`); `5D`/`1M` — только по клику; без auto-refresh/polling/prefetch всех периодов;
- не добавлены: technical indicators (EMA/SMA/RSI/MACD), candlestick UI, drawing tools, TradingView embed, WebSocket, realtime streaming, news, fundamentals, portfolio, positions, trades, orders, auth, LLM, Redis, worker, caching, scheduled polling, background jobs.

Реально проверено: `pytest -v` (121 тест, включая новые unit-тесты gateway/use-case/API-route для истории — успешный ответ, перевёрнутый provider-order → ASC-нормализация, одна точка, пустой `values`, daily date-only timestamp, отсутствующий `close`, невалидный timestamp, отсутствующий `values`, опциональное поле отсутствует → `None`, timeout, rate limit, unsupported ticker, no-secret-leakage) и `mypy` — чисто; opt-in `live_provider` smoke (2 теста, включая новый history-тест: реальный AAPL, >1 точки, ASC, `close > 0`) — passed, вне обычного suite; `npm run type-check`/`npm run build` — чисто. Полный ручной browser-сценарий (headless Chromium) с настоящим Twelve Data: add AAPL → `/instruments/AAPL` → карточка инструмента + график (default `1D`) → переключение `5D`/`1M` → возврат на `1D` без повторного запроса (кеш) → `F5` работает → back-ссылка работает → реальный `429` free-tier во время верификации уронил карточку инструмента 503-ошибкой, при этом график продолжал работать независимо (наглядное живое подтверждение независимости состояний) → «Повторить» восстановил и карточку, и график по отдельности. Поиск по логам backend/frontend и production frontend-бандлу подтвердил отсутствие утечки ключа. Тестовая запись (AAPL) удалена из watchlist; dev-серверы остановлены; PostgreSQL оставлен healthy (не поднимался и не останавливался этой задачей).

## 5. Что ещё не утверждено

- конкретная версия PostgreSQL;
- Python database driver;
- ORM или data-access подход;
- migration tool;
- connection pool;
- логическая модель данных;
- физическая схема БД;
- стратегия владения таблицами модулями;
- retention policy;
- backup и restore implementation;
- managed PostgreSQL provider;
- pgvector или отдельная vector database;
- embedding provider/model;
- TimescaleDB или отдельное time-series хранилище;
- конкретная worker/queue library не утверждена;
- scheduler не утверждён;
- retry library не утверждена;
- схема job storage не утверждена;
- отдельный message broker не утверждён;
- конкретная model/model ID не утверждены;
- provider SDK/version не утверждены;
- prompt registry/storage implementation не утверждён;
- tool implementation не утверждена;
- fallback implementation не утверждена;
- ASGI server;
- authentication provider;
- Dockerfile implementation;
- Compose implementation;
- конкретный reverse proxy продукт;
- reverse proxy configuration;
- hosting/cloud provider;
- monitoring stack;
- CI/CD;
- конкретные resource limits;
- конкретные image tags/digests;
- logging library;
- structured log formatter;
- metrics implementation;
- tracing SDK/instrumentation;
- diagnostic endpoint implementation;
- retention configuration;
- monitoring provider;
- dashboards;
- alert rules;
- CI и quality gates;
- конкретные источники данных и лицензии;
- конкретные версии TypeScript, React, Next.js и Node.js;
- package manager;
- UI component library;
- styling strategy;
- state-management library;
- data-fetching library;
- charting library;
- WebSocket/realtime library;
- frontend testing libraries.

## 6. Базовая и рабочая ветки

- базовая стабильная ветка: `main`;
- рабочая ветка определяется конкретной утверждённой задачей;
- перед изменениями исполнитель обязан проверить фактическую ветку через `git branch --show-current`.

## 7. Последняя завершённая задача

Instrument Details Vertical Slice.

## 8. Текущая задача

Instrument Price History Vertical Slice — на ревью.

## 9. Следующий планируемый блок

следующий продуктовый vertical slice — после ревью Instrument Price History Vertical Slice.

## 10. Обязательные документы для чтения перед любой задачей

- `PROJECT_CHARTER.md`;
- `docs/processes/GIT_WORKFLOW.md`;
- `.ai-context/CURRENT_STATE.md`;
- документы, перечисленные в конкретной задаче.

## 11. Критические запреты

- не писать бизнес-код;
- не выбирать стек самостоятельно;
- не создавать дубли;
- не менять `main` напрямую;
- не выполнять commit/push/merge без разрешения.

## 12. Известные проблемы

- стратегия векторного поиска и остальной технологический стек не утверждены;
- конкретные источники данных, лицензии и стоимость доступа не утверждены;
- количественные NFR требуют измерений;
- CI отсутствует.

## 13. Правило обновления

Этот файл обновляется после каждой принятой задачи, если изменилось состояние проекта.
