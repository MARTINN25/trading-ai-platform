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

Instrument Search Vertical Slice (ветка `feat/instrument-search`) — поиск инструмента по тикеру/названию для добавления в watchlist без необходимости заранее знать точный тикер:

- **Provider — уже подключённый Twelve Data, официальный endpoint, STOP CONDITION не потребовалась.** Проверена официальная документация (`GET /symbol_search`, раздел Discovery) перед реализацией, не угадывалось по памяти: принимает `symbol` (полнотекстовый поиск, не только точный тикер), `outputsize` (макс. 120), возвращает `{"data": [...], "status": "ok"}` с `symbol`/`instrument_name`/`exchange`/`mic_code`/`exchange_timezone`/`instrument_type`/`country`/`currency`; 1 credit/запрос, free-tier доступен — подтверждено живым вызовом. Второй provider не понадобился;
- `backend/src/trading_ai/market_data/types.py` — добавлены `InstrumentSearchResult` (provider-neutral: только `ticker`/`name`/`exchange`/`instrument_type`/`currency` — `mic_code`/`exchange_timezone`/`country` не прокидываются, нет UI-потребности), `InvalidSearchQueryError`/`normalize_search_query` (минимум 2 символа, мирроит `InvalidPeriodError`/`InvalidTickerError`);
- `backend/src/trading_ai/market_data/gateway.py` — `TwelveDataGateway.search_instruments()` добавлен на **существующий** класс (не отдельный gateway — тот же provider/auth/`_get`/`_validate_payload`, что и quote/history); результат ограничен 10 записями (`outputsize` в запросе + defensive re-cap после ответа); один плохой item (пустой/отсутствующий `symbol`/`instrument_name`) молча пропускается, не роняет весь поиск; лог пишет `query_length`, никогда полный текст запроса;
- `backend/src/trading_ai/market_data/use_cases.py` — `SearchInstruments`, зависит только от gateway, **не создаёт database session**, ничего не сохраняет;
- `backend/src/trading_ai/api/routes/instruments.py` — `GET /instruments/search?q=apple`, **зарегистрирован раньше** `GET /instruments/{ticker}` (иначе Starlette сопоставил бы `/instruments/search` с `ticker="search"` — регресс-тестом подтверждено, что коллизии нет); `422` невалидный/короткий/отсутствующий `q`, `503` unavailable/rate-limit, `504` timeout; пустой `items` — `200`, не ошибка;
- frontend: `instrument-api.ts` расширен (`InstrumentSearchResult`/`InstrumentSearchResponse`, `searchInstruments(query, signal)` — принимает `AbortSignal`, различает `AbortError` от реальной сетевой ошибки); **`WatchlistPanel.tsx` адаптирован, не переписан** — существующее поле «Тикер» стало полем «Тикер или название»: debounce 300мс на встроенном `setTimeout` (без новой зависимости), минимум 2 символа до первого запроса, `AbortController` отменяет предыдущий незавершённый запрос при новом вводе (устаревший ответ никогда не перезаписывает актуальный — подтверждено вживую), клавиатура (`ArrowUp`/`ArrowDown`/`Enter`/`Escape`), выбор результата или submit точного тикера оба идут через один и тот же `addTicker()` → существующий `addWatchlistItem`/дубликат-flow;
- rate-limit дисциплина: один settled-query = один provider-запрос, не запрос на клавишу; после выбора результата новый provider-запрос не делается — сразу `POST /watchlist`;
- не добавлены: Elasticsearch, full-text search DB, Redis, локальный symbol catalog, scheduled sync, background jobs, WebSocket, fuzzy-search библиотека, global state framework, UI framework, portfolio, trading, auth.

Реально проверено (до R2-коррекции, см. ниже): `pytest -v` (226 тестов) и `mypy` — чисто; opt-in `live_provider` smoke — passed; `npm run type-check`/`npm run build` — чисто. Полный ручной browser-сценарий (headless Chromium) с настоящим Twelve Data: 1-символьный ввод не вызвал ни одного запроса → debounce/AbortController/keyboard-навигация подтверждены вживую; дубликат/пустой результат/`Escape` — корректно; реальный rate limit Twelve Data не сломал ни watchlist, ни поиск. `secret_leak_detected=false`.

**R1-коррекция (identity/ambiguous search result, до commit):** первая реализация поиска не учитывала, что Twelve Data `/symbol_search` возвращает один и тот же тикер на разных биржах (AAPL — NASDAQ/США и Колумбия/Мексика) и что поиск по названию компании может найти сертификаты/ETN раньше настоящего листинга (например, "Microsoft" находил `4MSFT` — сертификат в Милане — раньше `MSFT`). Добавлены `_dedupe_by_ticker` (схлопывает одинаковый тикер с разных бирж — ticker-only watchlist не может их различить) и `_rank_exact_ticker_match_first` (точное совпадение тикера с запросом — в начало списка). Explicit STOP по более широкой политике "какой листинг канонический" — ADR/PRODUCT_SCOPE на тот момент не определяли поддерживаемый рынок достаточно точно для этого решения.

**R2-коррекция (Product Owner decision — US-listed equities only, до commit):** Product Owner принял решение — MVP instrument search scope ограничен **US-listed equities**. `watchlist` остаётся ticker-only (без изменений схемы/миграции). Backend теперь запрашивает у provider максимум (`outputsize=120`, тот же 1 credit) и фильтрует ответ по `country == "United States"` **и** `instrument_type == "Common Stock"` (`_is_us_common_stock`, точное совпадение по двум полям, которые Twelve Data документирует однозначно — не угаданное сопоставление бирж/MIC-кодов; `/symbol_search` не имеет request-time фильтра по стране/бирже/типу — подтверждено официальной документацией, STOP не потребовался, поскольку max-`outputsize` + response-side фильтр реально работает). Живое подтверждение: raw-запрос "Microsoft" на `outputsize=120` вернул 107 совпадений, из них ровно один US common stock match (реальный NASDAQ:MSFT, 22-й по счёту у provider'а — недостижим при прежнем `outputsize=10`); "MSFT" точным тикером тоже возвращал Аргентину/Мексику/Перу/Польшу/Австрию раньше NASDAQ. `_dedupe_by_ticker`/`_rank_exact_ticker_match_first` сохранены как safety net после фильтра. Тесты: +6 новых gateway-тестов (AAPL NASDAQ vs BVC; MSFT NASDAQ vs BCBA depositary receipt; исключение ETF/Depositary Receipt/Certificate/Warrant; дедупликация двух true US common stock записей; exact-ticker ranking среди survivors; "Microsoft" name-search сводится к единственному NASDAQ:MSFT), + 3 существующих теста адаптированы под новый фильтр (malformed-item-skip, optional-fields-none, capped-at-limit — добавлены обязательные `country`/`instrument_type` в фикстуры). `pytest -v` — 232 passed, 12 skipped; `mypy` — чисто; opt-in `live_provider` — 2 реальных вызова (Apple, Microsoft), оба вернули ожидаемый NASDAQ-листинг первым; `npm run type-check`/`npm run build` — чисто (frontend-код не менялся в R2). Живая browser-проверка: поиск "Apple" → только `AAPL`/`AAPI`/`GAPJ`, все NASDAQ·USD/OTC·USD (ни одного не-американского листинга); поиск "Microsoft" → только `MSFT`/NASDAQ·USD (ни одного сертификата/ETN/depositary receipt); оба добавлены в watchlist и удалены после проверки. README обновлён (US-equities-only scope задокументирован в разделах "Instrument search"/"Instrument search UI"). Не создана exchange-qualified persistence, не добавлена миграция, watchlist-схема не менялась.

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

Instrument AI Analysis Vertical Slice.

## 8. Текущая задача

Instrument Search Vertical Slice — на ревью.

## 9. Следующий планируемый блок

Следующий продуктовый vertical slice (например, quality evaluation dataset для AI-анализа — ADR-0007 §52 явно требует его перед расширением production-использования модели — либо иной блок по roadmap/ADR) — после ревью Instrument Search Vertical Slice.

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
