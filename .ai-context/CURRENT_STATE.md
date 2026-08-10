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

Instrument Details Vertical Slice (ветка `feat/instrument-details`) — отдельная страница инструмента (`/instruments/{ticker}`), открывается кликом по тикеру в watchlist:

- **Twelve Data остаётся implementation decision**, без изменений и без нового ADR — та же граница provider-neutral контракта, что и в Watchlist Market Data Vertical Slice;
- `backend/src/trading_ai/market_data/types.py` — добавлен `InstrumentSnapshot` (superset `MarketQuote`: + `open`/`high`/`low`/`previous_close`/`volume`, все — честно `None`, если provider их не вернул, никогда придуманный `0`);
- `backend/src/trading_ai/market_data/gateway.py` — `TwelveDataGateway.get_instrument_snapshot()` переиспользует тот же `/quote`-запрос, что и `get_quote()` (второй provider-эндпоинт не понадобился — Twelve Data уже возвращает open/high/low/previous_close/volume в этом ответе); статус-код/shape-валидация вынесена в общий `_validate_payload()`, чтобы не дублировать её между `MarketQuote`- и `InstrumentSnapshot`-парсингом;
- `backend/src/trading_ai/market_data/use_cases.py` (новый файл) — `GetInstrumentDetails`, зависит только от gateway, **не создаёт database session** — это чистый market-data lookup, не связанный с watchlist persistence;
- `backend/src/trading_ai/api/routes/instruments.py` (новый файл) — `GET /instruments/{ticker}`; `422` невалидный тикер (`InvalidTickerError` уже обрабатывается глобальным handler'ом из watchlist), `404` тикер не поддерживается, `503` provider недоступен/rate limit, `504` timeout; ни один ответ не содержит сырой provider payload/URL/exception text;
- frontend: `frontend/src/lib/instrument-api.ts` (новый, отдельный от `watchlist-api.ts` typed client), `frontend/src/app/instruments/[ticker]/page.tsx` + `frontend/src/components/InstrumentDetailsView.tsx` (loading/error/retry state, back-ссылка через `next/link`, positive/negative никогда только цветом); `WatchlistPanel.tsx` — тикер теперь `<Link href="/instruments/{ticker}">` вместо `<span>`;
- не добавлены: charts, news, fundamentals, portfolio, orders, LLM, auth, WebSocket, background polling, candles, Redis, worker, caching layer, UI/state-management framework.

Реально проверено: `pytest -v` (79 тестов, включая новые unit-тесты gateway/use-case/API-route: успешный snapshot, отсутствующее/неразбираемое опциональное поле → `None`, unsupported ticker, rate limit, timeout, malformed response, no-secret-leakage) и `mypy` — чисто; `npm run type-check`/`npm run build` — чисто, `/instruments/[ticker]` собирается как dynamic route; полный ручной browser-сценарий (headless Chromium) с настоящим Twelve Data: add AAPL → watchlist показывает цену → клик по AAPL → `/instruments/AAPL` с реальными open/high/low/previous_close/volume/updated/source → back-ссылка → прямой заход по URL и `F5`-обновление работают → реальный `503` (сработал free-tier rate limit после серии запросов) корректно показал «Рыночные данные сейчас недоступны» с кнопкой «Повторить» без поломки страницы → повторный клик «Повторить» восстановил реальные данные. Поиск по логам backend/frontend и production frontend-бандлу подтвердил отсутствие утечки ключа. Тестовая запись (AAPL) удалена из watchlist; dev-серверы остановлены; PostgreSQL оставлен healthy (не поднимался и не останавливался этой задачей — уже был запущен).

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

Watchlist Market Data Vertical Slice.

## 8. Текущая задача

Instrument Details Vertical Slice — на ревью.

## 9. Следующий планируемый блок

historical price data / chart — после ревью Instrument Details Vertical Slice.

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
