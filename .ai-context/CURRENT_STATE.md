# Current Project State

**Статус:** Утверждён
**Владелец:** Product Owner
**Дата последнего изменения:** 2026-08-05
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

Watchlist Market Data Vertical Slice (ветка `feat/watchlist-market-data`) — реальные рыночные данные (price/change/change_percent/as_of/source) для каждого watchlist-тикера:

- **provider — implementation decision, не ADR.** Конкретный market-data provider не был утверждённым архитектурным решением (`CURRENT_STATE.md`, раздел 5, «конкретные источники данных и лицензии»); задача была явно остановлена перед написанием production-кода, найденные варианты (Alpha Vantage/Finnhub/Twelve Data) и их ToS/rate-limit trade-offs представлены Product Owner; **Twelve Data выбран Product Owner как implementation decision** (официальный документированный REST API, без scraping, free-tier с API key) — это НЕ заменяет и не предвосхищает возможный будущий ADR, если provider станет жёсткой платформенной зависимостью;
- `backend/src/trading_ai/market_data/` — `types.py` (provider-neutral `MarketQuote` + error taxonomy: unavailable/timeout/rate-limited/unsupported-ticker/malformed-response, mirrors `llm_gateway` pattern из `ADR-0007` §20–22, не HTTPException), `gateway.py` (единственное место с `httpx`/URL/response-shape Twelve Data; API key — только в HTTP-заголовке `Authorization`, никогда в query-параметре URL);
- watchlist application: `ListWatchlistItemsWithQuotes` — последовательный (не параллельный, не unbounded fan-out) вызов gateway на каждый item; один сбойный ticker не роняет весь список — становится safe-категорией (`timeout`/`rate_limited`/`unsupported`/`unavailable`) в результате, не exception;
- API: `GET /watchlist/quotes` — отдельный endpoint (не меняет контракт `GET /watchlist`), `503` если provider не сконфигурирован, `200` с `quote_error` на элемент при частичном сбое;
- `TRADING_AI_MARKET_DATA_API_KEY` — опциональная env-переменная (как `TRADING_AI_DATABASE_URL`), без default; ключ не логируется, не возвращается в API, не передаётся во frontend;
- **реальный инцидент, найденный и исправленный в этой же задаче:** `httpx`'s собственное INFO-логирование писало полный URL (с API key как query-параметром) в структурированные логи backend — исправлено централизованно в `trading_ai/logging.py` (httpx/httpcore logger level поднят до WARNING) и defense-in-depth в `gateway.py` (key переведён из query-параметра в заголовок); оба фикса покрыты regression-тестами и подтверждены живым вызовом Twelve Data после фикса — leak устранён, чистые логи (`operation`/`ticker`/`source`/`status`/`latency_ms`, без URL/key);
- frontend: `getWatchlistQuotes()`/`WatchlistItemQuote` в `watchlist-api.ts`; `WatchlistPanel.tsx` показывает price/change/change_percent (явный `+`/`-`/`±` в тексте, не только цветом, plus aria-label направления)/as_of, «Данные недоступны» вместо `0`/выдумки, кнопка «Обновить данные» (одноразовая ручная загрузка, без auto-polling); add/delete теперь перезагружают список через тот же quotes-endpoint вместо локального сплайса — новая запись сразу получает котировку;
- не добавлены: portfolio/trades/positions, LLM, charts, WebSocket, Redis, Kafka, worker, scheduled polling, caching layer, generic provider framework, UI/state-management framework, auth.

Реально проверено: opt-in `live_provider`-маркированный smoke-тест против настоящего Twelve Data (отдельный файл, никогда не пересекается с обычным `-m integration`), реальные `GET /watchlist/quotes` для AAPL/MSFT (включая наблюдение настоящего `429 Too Many Requests` free-tier и корректную graceful-деградацию до «Данные недоступны»), `pytest -v`/`mypy --strict`, PostgreSQL integration-тесты (реальные watchlist rows + fake gateway — без живых provider-вызовов в обычном suite), `npm run type-check`/`npm run build`, полный ручной browser-сценарий (headless Chromium): реальные котировки, «Обновить данные», add/delete flow не сломаны. Поиск по репозиторию и scratch-файлам подтвердил отсутствие утечки ключа (`secret_leak_detected=false`). Тестовые данные (AAPL/MSFT) удалены; dev-серверы остановлены; PostgreSQL оставлен healthy.

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

Watchlist Remove Item Vertical Slice.

## 8. Текущая задача

Watchlist Market Data Vertical Slice — на ревью.

## 9. Следующий планируемый блок

instrument details/chart либо следующий продуктовый vertical slice — после ревью Watchlist Market Data Vertical Slice.

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
