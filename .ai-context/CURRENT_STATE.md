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

Instrument News Vertical Slice (ветка `feat/instrument-news`) — секция новостей на `/instruments/{ticker}`, ниже графика цены:

- **Twelve Data не подходит для новостей — подтверждено официальной документацией, не молча заменено.** Полный документированный каталог endpoints Twelve Data (получен целиком) не содержит раздела "News"; единственный близкий по смыслу — `Press releases` (`/press_releases`, Fundamentals) — проверен живым вызовом и оказался непригоден: нет `source`, нет `url` на оригинал (оба — жёсткое требование задачи), `body` — сырой HTML синдицированного/промо-контента. Это была явная STOP CONDITION задачи: production-код не писался до решения Product Owner. Исследованы официальные альтернативы (Finnhub `company-news`, Alpha Vantage `NEWS_SENTIMENT`, Marketaux) и представлены Product Owner; **Finnhub выбран Product Owner как implementation decision** (`TRADING_AI_NEWS_API_KEY`, отдельный от `TRADING_AI_MARKET_DATA_API_KEY` free-tier ключ) — не заменяет и не предвосхищает возможный будущий ADR;
- **Finnhub `GET /company-news`** — подтверждён живым вызовом перед реализацией (не угадывался по памяти): заголовок `X-Finnhub-Token` (не query-параметр), JSON-массив с `headline`/`source`/`datetime` (Unix seconds UTC)/`url`/`summary`/`id`, newest-first по умолчанию (backend не доверяет — сортирует сам), free-tier `60 запросов/минуту`; неизвестный/неподдерживаемый тикер → `200 []`, provider не различает "нет новостей" и "тикер не существует" — поэтому `GET /instruments/{ticker}/news` никогда не возвращает `404`, только пустой `items`;
- `backend/src/trading_ai/market_data/types.py` — добавлены `InstrumentNewsItem`/`InstrumentNews` (provider-neutral; `summary` честно `None`, если provider его не вернул); ошибки переиспользуют существующую `MarketDataError`-таксономию (`TickerUnsupportedError` этим gateway никогда не поднимается — Finnhub не различает);
- `backend/src/trading_ai/market_data/news_gateway.py` (новый файл) — `FinnhubNewsGateway`, второй, отдельный от `TwelveDataGateway` provider-адаптер (ADR-0007 §22 boundary pattern); фиксированное окно 7 дней, один provider-запрос на загрузку страницы, cap 10 items после сортировки (provider не поддерживает server-side `limit`); URL валидируется схемой (`http`/`https` — `javascript:`/`data:`/`file:` и прочее отбрасываются, `urllib.parse.urlparse`); один плохой item (невалидный timestamp/URL/отсутствующий headline/source) молча пропускается, не роняет весь список;
- `backend/src/trading_ai/config.py`/`main.py` — `TRADING_AI_NEWS_API_KEY` (тот же optional-feature паттерн, что и market data: не задан → только `GET /instruments/{ticker}/news` отвечает `503`, остальное приложение не затронуто);
- `backend/src/trading_ai/market_data/use_cases.py` — `GetInstrumentNews`, зависит только от gateway, **не создаёт database session**, ничего не сохраняет;
- `backend/src/trading_ai/api/routes/instruments.py` — `GET /instruments/{ticker}/news`; `422` невалидный ticker, `503` unavailable/rate-limit/malformed, `504` timeout; пустой `items` — `200`, не ошибка;
- frontend: `instrument-api.ts` расширен (`InstrumentNewsItem`/`InstrumentNewsResponse`, `getInstrumentNews()` — один запрос за визит страницы, без auto-retry); **новый `InstrumentNewsSection.tsx`** — independent loading/error/empty/retry state от карточки и графика (сбой одной секции не ломает другие — подтверждено вживую двумя разными способами: реальный `429` уронил только график после `F5`, карточка и все 10 новостей продолжали работать; отдельно — контролируемый forced-error тест на именно news-секции подтвердил, что её «Повторить» восстанавливает только её); ссылки — `target="_blank"`/`rel="noopener noreferrer"`, плюс client-side defense-in-depth re-check схемы URL перед рендером `<a href>` поверх уже backend-валидированных данных;
- rate-limit дисциплина: один news-запрос = один provider-запрос при открытии страницы; без polling/auto-refresh/prefetch из watchlist;
- не добавлены: sentiment analysis, AI summaries, LLM, embeddings, vector search, news persistence, Redis, worker, scheduled jobs, WebSocket, notifications, portfolio, trading, orders, auth, generic news framework, UI/state-management framework.

Реально проверено: `pytest -v` (143 теста, включая 18 новых unit-тестов gateway — успешный ответ, newest-first нормализация, пустой список, отсутствующее/пустое summary → `None`, невалидный timestamp/URL/unsafe scheme → item пропущен (не вся выдача), cap на 10, timeout, rate limit, bad API key, 5xx, malformed JSON/non-array payload, no-secret-leakage; плюс use-case и API-route тесты) и `mypy` — чисто; opt-in `live_provider` smoke (3 теста, включая новый news-тест: реальный AAPL, headline/source непустые, `published_at` timezone-aware, `url` http(s), newest-first) — passed, вне обычного suite; `npm run type-check`/`npm run build` — чисто. Полный ручной browser-сценарий (headless Chromium) с настоящими Twelve Data + Finnhub: add AAPL → `/instruments/AAPL` → карточка + график + 10 реальных новостей (headline/summary/source/время/ссылка) → клик «Открыть источник →» открывает реальную статью в новой вкладке (`target=_blank`, `rel=noopener noreferrer` подтверждены) → `F5` работает (10 новостей снова) → back-ссылка работает → реальный `429` free-tier после `F5` уронил только график, карточка и новости не затронуты → «Повторить» восстановил график; отдельный forced-error прогон подтвердил independent retry именно для news-секции. Поиск по логам backend/frontend и production frontend-бандлу подтвердил отсутствие утечки обоих ключей (`secret_leak_detected=false`). Тестовая запись (AAPL) удалена из watchlist; dev-серверы остановлены; PostgreSQL оставлен healthy (не поднимался и не останавливался этой задачей).

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

Instrument Price History Vertical Slice.

## 8. Текущая задача

Instrument News Vertical Slice — на ревью.

## 9. Следующий планируемый блок

AI analysis / следующий продуктовый vertical slice — после ревью Instrument News Vertical Slice.

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
