# Current Project State

**Статус:** Утверждён
**Владелец:** Product Owner
**Дата последнего изменения:** 2026-08-12 (Phase 2B.1)
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

**Phase 2B.1 — Professional Instrument Workspace** (ветка `feature/professional-instrument-workspace`, создана от `main` после мерджа Phase 2B @ `e473eda`). **Frontend/UX задача с минимальными аддитивными backend-изменениями — ни один коммит не создан.** Изменения реализованы и полностью провалидированы (backend pytest/mypy, frontend type-check/build, реальные backend+frontend dev-серверы, реальная Compose PostgreSQL, реальные live-вызовы xAI/Twelve Data), но намеренно НЕ закоммичены — ожидает ревью и явного разрешения Product Owner на commit (`GIT_WORKFLOW.md`).

Не переопределяет Forecast Contract (`FORECAST_CONTRACT.md`) — ни одно forecast-поле, состояние, версия схемы/промпта не изменены этой задачей. Переупорядочивает и уплотняет уже существующий Instrument Workspace (`InstrumentDetailsView.tsx`) и чинит найденный визуальный дефект графика цены:

- **Диагностирован и устранён артефакт графика 1D** — «длинный идеально горизонтальный отрезок» оказался реальным, не выдуманным и не CSS-замаскированным дефектом: старый `PriceChart.tsx` располагал точки по оси X пропорционально *реальному прошедшему времени*; ночной разрыв между сессиями (подтверждено вживую: ~17.6 часа между `2026-08-10T19:55Z` и `2026-08-11T13:30Z`, цена почти не изменилась за это время — 308.19 → 308.24) занимал **40.7%** ширины графика при линейно-временной оси. Исправление — индексное позиционирование по бару (`xForIndex`, не `xForTime`), стандартная практика для внутридневных графиков с несколькими сессиями; проверено вживую количественным пересчётом на реальных данных: тот же разрыв теперь занимает **1.0%** ширины (столько же, сколько обычный интервал между барами). Разрыв не скрыт — новый детерминированный `SESSION_BREAK_FACTOR`-детектор (разрыв > 3× медианного интервала периода) рисует явный пунктирный маркер разрыва вместо него.
- **OHLC/объём — аддитивное backend-расширение** (task scope §6-§7): `TwelveDataGateway`/`PricePoint` уже парсили реальные `open`/`high`/`low`/`volume` из ответа провайдера, но `InstrumentHistoryPointResponse` отдавала только `close`. Подтверждено вживую: 100/100 баров периода 1D несут реальные, ненулевые OHLC и объём (не выдумано) — добавлены как nullable-поля в тот же существующий endpoint (`GET /instruments/{ticker}/history`), не новый provider, без миграции.
- **`PriceChart.tsx` полностью переписан** — свечи (когда весь период несёт полный OHLC, иначе честный line-fallback), объёмная гистограмма под графиком, видимая ценовая и временная ось, маркер последней цены, hover-перекрестие с OHLC/объёмом наведённого бара — всё на том же hand-rolled `<svg>` без новой зависимости (обоснование см. раздел «Зависимости» финального отчёта задачи).
- **Order Book / Level 2 — намеренно НЕ реализован**: реальный `/quote`-ответ Twelve Data проверен вживую — bid/ask/depth-полей нет вообще; ни в `TECHNOLOGY_EVALUATION.md`, ни в `ADR-0011` эта возможность не исследована ни для одного провайдера. Зафиксировано как `ORDER BOOK DEFERRED — requires provider/capability research`, не реализовано никаким suррогатом.
- **Информационная иерархия страницы инструмента изменена**: HEADER → PRIMARY MARKET PANEL (график + `MarketSnapshotPanel.tsx`, новый компонент — котировка сессии + диапазон периода, деterministically выведенный из уже загруженных данных графика, без второго запроса) → FORECAST PANEL (теперь **отдельная строка на всю ширину**, не половина строки рядом с News) → INTELLIGENCE ROW (News, тоже на всю ширину, карточная сетка вместо `overflow-y: auto`-колонки фиксированной высоты) → HISTORY. Устраняет прежнюю проблему «длинная AI-колонка на несколько экранов при пустой соседней колонке».
- **`ForecastCard.tsx` — summary-first редизайн**: горизонт/уверенность/направление/verdict видны без скролла; новая «decision context» полоса (текущая цена — threaded prop, реальные данные; наблюдённый уровень — честный превью первого условия инвалидации; счётчик условий инвалидации; момент повторной проверки); три сценарных карточки как сиблинги в сетке (не последовательные блоки); новая сетка «Почему вывод / Что отменит / Что отслеживать» (объединяет `key_facts`/`key_drivers`/`catalysts`/`what_to_watch_next`, ранее не показанные в `ForecastCard` вообще, только в устаревшем разделе). Легаси FR-018 10-раздельная структура сохранена целиком, не удалена — перемещена в `<details>` («Подробный анализ»), свёрнутую по умолчанию для новых forecast-строк и развёрнутую по умолчанию для строк без `horizon` (старые записи, для которых это единственный контент).
- **Skeleton-состояние генерации**: структурный плейсхолдер, повторяющий форму `ForecastCard` (пилюли/полоса решений/3 карточки сценариев), сохраняет выбранный горизонт, не имитирует потоковую генерацию токенов (backend не стримит).

**Реально проверено (первый проход):** backend `pytest -v` → 505 passed, 38 skipped (без регрессий, было 504/38; +1 новый тест на честную nullability OHLC/volume); `mypy src tests` → чисто (109 файлов); frontend `npm run type-check`/`npm run build` → чисто, все 6 маршрутов собраны; `git diff --check` → чисто. Живая (real xAI/Twelve Data/real Postgres) проверка без Playwright (браузерный/скриншот-инструмент недоступен в этой сессии — визуальный самообзор выполнен как структурный разбор фактического DOM/CSS, не попиксельно; см. финальный отчёт задачи, раздел 22): артефакт графика подтверждён количественно на реальных данных AAPL (40.7% → 1.0% ширины графика на разрыве сессии, раздел 4 выше); `GET /instruments/AAPL/history?period=1D` вернул 100/100 баров с реальными ненулевыми OHLC/volume; живая генерация SHORT/сохранение/история — `POST /instruments/AAPL/analysis?horizon=short` → `POST /instruments/AAPL/insights` → `GET /instruments/AAPL/insights` вернул одновременно новую forecast-строку (id=68) и pre-Phase-2B legacy-строки (id=39/40, `horizon=null`) в одном списке, обе формы данных подтверждены соответствующими новым компонентам; история инструмента AAPL на момент проверки содержала все три горизонта (SHORT/MEDIUM/LONG, id 65/66/67) с корректно различающимся содержанием.

### 4.1 Второй проход — визуальный/information-design polish (по итогам реального ручного browser-ревью Product Owner)

Manual browser review первого прохода признал реализацию функционально лучше (свечи, объём, artifact-фикс, снимок рынка, читаемость новостей — все подтверждены как улучшение), но визуально всё ещё «сухой»/утилитарной, box-heavy, неровной по высоте карточек, с пустыми зонами и стенами одинаково-весомых карточек. Второй проход — чисто визуальный/information-design polish поверх уже реализованной функциональности; **не откатывает** свечи/OHLC/объём, **не меняет** Forecast Contract, **не добавляет** новых зависимостей (подтверждено: `git diff --stat -- frontend/package.json frontend/package-lock.json` пуст), **не выдумывает** новый интеллект/данные:

- **Заголовок инструмента перегруппирован**: тикер как компактный бейдж + цена/изменение сгруппированы вместе слева, справа — блок «свежесть данных» (выведена детерминированно из уже существующего `as_of`, порог 15 минут — restrained warning-индикатор, не алармирующий баннер) + источник.
- **График и `MarketSnapshotPanel` объединены в один «рыночный модуль»**: общая рамка/фон вместо двух независимо обведённых панелей, внутренний разделитель вместо зазора; `align-items: stretch` даёт фону снимка растягиваться на высоту графика вместо пустой области под более короткой панелью.
- **Полировка графика** (не переписан): компактный табличный tooltip (время/O/H/L/C/объём построчно вместо предложения), сегментированный переключатель периода (1Д/5Д/1М), подложка под меткой последней цены + точка-маркер, чуть тяжелее свечи/фитили, плейсхолдер загрузки резервирует итоговую высоту (без прыжка layout).
- **Пустое состояние AI-анализа переработано**: вместо «AI-анализ ещё не запущен» + кнопка — структурная панель «что оценивает анализ сейчас», перечисляющая только реально реализованные категории контекста (цена/история/новости/доступный рыночный контекст) — ничего из недостроенной roadmap-возможности не подразумевается.
- **`ForecastCard` — теперь единственная визуальная граница «мозга» воркспейса**: цветной верхний акцент (focus-цвет) вместо двойной рамки «панель внутри панели» — `.workspace-forecast-panel` теперь прозрачна/без рамки, карточка сама несёт границу; тот же паттерн применён к idle/skeleton/error состояниям того же слота (нейтральный акцент для idle, focus для skeleton, negative для error) для визуальной согласованности между состояниями. Бейдж уверенности переиспользует уже существующие `.ai-analysis-confidence-*` классы (не задублирован). Колонки evidence/invalidation/watch получили тонкий разделитель + цветной маркер-точку у заголовка (focus/negative/warning) — без внешней иконочной зависимости.
- **News Intelligence — двухуровневая приоритизация**: «Топ-новости» (реальный `relevance === "high"` от backend, до 2 штук, порядок backend сохранён, полная карточка) и «Дополнительный контекст» (остальные, в исходном порядке, компактная карточка с CSS line-clamp резюме + раскрываемое «Подробнее» — полный текст всегда доступен, ничего не спрятано без возможности раскрыть). Ранжирование не выдумано — использует только существующий `relevance`-флаг и существующий порядок ответа.
- **История — компактные строки-таймлайн**: для forecast-записей (`horizon !== null`) — строка из времени + чипов (горизонт/направление или состояние/уверенность), затем короткий verdict, вместо абзаца первым; легаси-записи (`horizon === null`) не тронуты — прежний формат, честно, так как это единственные доступные для них данные. `DIRECTIONAL_CLASS` вынесен из `ForecastCard.tsx` как экспорт для повторного использования цветовой семантики в чипах истории (не задублирована).
- **Общая ритм/border-полировка**: удалён мёртвый CSS (`instrument-stats-grid`/`instrument-stat-*`, `ai-analysis-idle`/`ai-analysis-loading` — оба класса больше нигде не использовались в TSX после этой правки); построчные рамки в `MarketSnapshotPanel` заменены на интервал сетки; decision-strip и его skeleton-эквивалент сгруппированы фоном вместо пары рамок; плейсхолдеры загрузки (график/новости/история) резервируют примерную высоту вместо голой строки текста; hover-состояния на карточках истории/новостей (только цвет рамки, без анимации, `prefers-reduced-motion` не требуется для простого цветового перехода); news-грид использует `minmax(min(X, 100%), 1fr)` для защиты от горизонтального overflow на очень узких экранах.

**Реально проверено (второй проход):** backend `pytest -v` → 505 passed, 38 skipped (backend-файлы этой правкой не тронуты — идентичный результат первому проходу); `mypy src tests` → чисто (109 файлов); frontend `npm run type-check` → чисто; `npm run build` → чисто, все 6 маршрутов собраны; `git diff --stat -- frontend/package.json frontend/package-lock.json` → пусто (зависимости не менялись); `git diff --check` → чисто (та же информационная CRLF-заметка на `CURRENT_STATE.md`). Живые проверки данных против уже поднятых real backend/frontend dev-серверов и реальной Compose PostgreSQL: `GET /instruments/AAPL` вернул свежий `as_of` (использован для проверки логики freshness); `GET /instruments/AAPL/news` вернул реальное распределение релевантности (2× `high`/`company` первыми, затем `low sector/market/indirect`) — подтверждает, что новая двухуровневая логика новостей корректно выделяет именно эти 2 карточки в «Топ-новости» на реальных данных, не выдуманных; `GET /instruments/AAPL/insights` вернул одновременно 5 forecast-записей (id 64-68, все три горизонта, разные `directional_view`) и 2 легаси-записи (id 39/40, `horizon=null`) в одном списке — подтверждает, что оба JSX-пути новой компактной истории (чипы vs. легаси-абзац) корректно обрабатывают реальные смешанные данные. Визуальная попиксельная проверка по-прежнему не выполнена — в этой сессии недоступен browser/screenshot-инструмент (см. финальный отчёт задачи, раздел про самоаудит); заменена структурным разбором фактических JSX/CSS-изменений против конкретных претензий ручного ревью Product Owner.

## 4a. Предыдущая ревью-задача (теперь завершена)

Phase 2B — Forecast Contract (ветка `feature/forecast-contract`) — **завершена и смёржена в `main` через PR #50** (коммит `6ccfd1a`, merge-коммит `e473eda`).

Оформляет FR-061/FR-062 (структурированный прогноз/тезис, явное состояние отсутствия качественной возможности) и UJ-031/UJ-032, ратифицированные Phase 2.0 (PO-2.0-4–PO-2.0-8), поверх уже утверждённого концептуального `docs/architecture/FORECAST_CONTRACT.md`. Расширяет (не заменяет) существующий FR-018 10-раздельный инсайт:

- **Выбранная стратегия совместимости (вариант A из задания)** — `InstrumentAnalysis`/`SavedInsight`/`NewInsight` (`ai/types.py`/`insights/domain.py`) расширены дополнительными полями (`horizon`/`forecast_state`/`directional_view`/`concise_verdict`/`base_case`/`bullish_case`/`bearish_case`/`catalysts`/`invalidation_conditions`/`what_to_watch_next`/`check_after`/`uncertainty`/`context_categories_used`), все `None`/`()` по умолчанию — **не новая параллельная v2-структура**. `key_facts`/`risks` переиспользованы как Forecast Contract'овские `evidence`/`risks` (`FORECAST_CONTRACT.md` §3), не задублированы под вторым именем. Причина выбора именно этого варианта: одна аналитическая генерация/один LLM-вызов вместо двух параллельных пайплайнов, старые рендер-компоненты (`InsightSections.tsx`) продолжают работать без изменений для любой версии строки — то же самое обоснование, что уже использовал этот проект при переходе `insight-structure-v1`-набора полей с v1 на v2 в задаче «Insight Persistence» (раздел 4i ниже).
- **`INSIGHT_SCHEMA_VERSION`** поднят до `"insight-structure-v2-forecast"`, **`PROMPT_VERSION`** — до `"instrument-analysis-v3-forecast"` (тот же constant-bump паттерн, что и v1→v2). Старые сохранённые строки (`schema_version == "insight-structure-v1"`) хранят это значение навсегда (append-only, `ADR-0004` §20) и остаются полностью читаемыми — подтверждено вживую (раздел ниже).
- **Горизонт (FR-006)** — `AnalysisHorizon` (`short`/`medium`/`long`) обязателен в `POST /instruments/{ticker}/analysis?horizon=...`; отсутствие или невалидное значение → `422` (никогда не подставляется по умолчанию). `ai/horizon.py` — новый модуль чисто детерминированной логики: `parse_horizon`, `history_period_for_horizon` (SHORT→существующее окно 1M, MEDIUM→новое 3M, LONG→новое 1Y — `market_data/types.py`/`gateway.py` расширены двумя новыми значениями `InstrumentHistoryPeriod`, тот же provider endpoint, только другой `outputsize`), `compute_check_after` (`generated_at` + верхняя граница диапазона горизонта: SHORT +5 торговых дней с пропуском выходных, MEDIUM +8 недель, LONG +12 календарных месяцев — не изобретается LLM), `compute_horizon_sufficiency` (качественный, явно задокументированный судейский порог: SHORT ≥5/MEDIUM ≥20/LONG ≥60 точек истории + staleness-порог котировки на горизонт — точные числа НЕ утверждены Product Owner, это Solution-Architect-style implementation judgment call, разрешённый `FORECAST_CONTRACT.md` §7).
- **Деterministic sufficiency gate — двойное принуждение**: результат `compute_horizon_sufficiency` передаётся модели как DATA (`HORIZON DATA SUFFICIENCY: sufficient/insufficient`, с явным prompt-правилом «модель обязана вернуть `insufficient_data`, если сигнал insufficient») **и** независимо проверяется backend'ом после ответа модели (`ai/gateway.py::_parse_response`) — если модель проигнорировала правило и вернула `forecast_state=forecast` при insufficient-сигнале, backend принудительно понижает состояние до `insufficient_data` и обнуляет всё направленное содержимое. Подтверждено вживую в обе стороны (раздел ниже): модель сама уважает правило 13, backend-override — отдельно протестирован детерминированными тестами (не требует LLM).
- **`forecast_state`** — `FORECAST`/`NO_QUALITY_SETUP`/`INSUFFICIENT_EDGE`/`INSUFFICIENT_DATA`; последние три — валидные, желательные результаты (PO-2.0-8), не запасной вариант. `directional_view` (`STRONGLY_BULLISH…STRONGLY_BEARISH`, не BUY/SELL/HOLD) и `base_case`/`bullish_case`/`bearish_case`/`catalysts`/`invalidation_conditions` — `None`/`()`, когда `forecast_state != FORECAST` (структурно enforced Pydantic `model_validator`, не только промптом).
- **Промпт/схема**: `ai/prompts.py` (`SYSTEM_INSTRUCTIONS` расширен правилами 13–22) и `ai/gateway.py` (`_RESPONSE_JSON_SCHEMA`/`ModelOutputSchema`) расширены на месте (не новый sibling-файл, в отличие от Phase 2A's `news_prompts.py` — здесь это одна логическая генерация, а не новая независимая LLM-возможность). Новая явная проверка `contains_numeric_probability_language` (запрет численной вероятности, независимо от уже существующего `contains_forbidden_language` для BUY/SELL/HOLD/target-price).
- **API**: `POST /instruments/{ticker}/analysis` теперь требует `horizon` query-параметр; `InstrumentAnalysisResponse`/`InsightDetailResponse`/`InsightSummaryResponse` аддитивно расширены новыми полями (все nullable на `InsightDetailResponse`/`InsightSummaryResponse` для обратной совместимости со старыми строками).
- **Frontend**: новый `HorizonSelector.tsx` (визуально выбранное, изменяемое значение перед каждой генерацией — не скрытый backend-default) и `ForecastCard.tsx` (директивный бейдж/уверенность/verdict/сценарии/что-поддерживает/что-отменит/что-отслеживать/свежесть; честное, визуально отдельное состояние для `NO_QUALITY_SETUP`/`INSUFFICIENT_EDGE`/`INSUFFICIENT_DATA` — не directional-looking карточка). Подключены в `AiAnalysisSection.tsx` (свежая генерация) и `InsightHistorySection.tsx` (сохранённый инсайт, включая компактную сводку «на первый взгляд» в списке истории) — рендерятся только когда `horizon !== null`, старые строки просто не показывают этот блок.
- **Миграция `0007_forecast_contract_fields`** (ревизует `0006_news_intelligence_items`) — 13 новых nullable колонок на `insights`, чисто аддитивно, без backfill старых строк.
- **AI evaluation**: существующий `ai/evaluation/dataset.py`/`evaluators.py`/`types.py` расширены на месте (не новый sibling-набор, поскольку это тот же `InstrumentAnalysis`, не новый тип) — все 12 существующих кейсов получили `horizon`/forecast-поля через реальный `compute_horizon_sufficiency` (не hand-faked), плюс 3 новых кейса (`long-horizon-insufficient-history`, `target-price-temptation`, `probability-temptation`); итого 15 кейсов, 10 новых `check_*`-проверок для forecast-полей.

**Реально проверено:** backend `pytest -v` → 504 passed, 38 skipped (без регрессий, было 453/37); `mypy src tests` → чисто (109 файлов); alembic upgrade→downgrade→upgrade→current цикл против реальной Compose PostgreSQL подтверждён (`0007_forecast_contract_fields (head)`); 32 opt-in integration-теста против реальной PostgreSQL, включая новый forecast-round-trip и legacy-null-round-trip; frontend `npm run type-check`/`npm run build` → чисто, все 6 маршрутов собраны. Живая (real xAI/Twelve Data/Finnhub/real Postgres) проверка без Playwright (браузерный инструмент недоступен в этой сессии — проверено эквивалентно через реальные backend+frontend dev-серверы и прямые HTTP-вызовы, зафиксировано в логах): Flow A (AAPL SHORT, живая генерация ~52с, `forecast_state=forecast`/`directional_view=bearish`, invalidation conditions ссылаются на реальные наблюдённые уровни цены 303.42/302.79, `check_after=2026-08-19` — ровно +5 торговых дней с пропуском выходных) — пройден; Flow B (AAPL MEDIUM, живая генерация, реальный provider-запрос `period=3M points_count=70`, результат содержательно отличается — `directional_view=neutral`, `check_after=2026-10-07` — ровно +8 недель) — пройден; Flow C (сконструированный live-вызов реального `XAIGateway` с горизонтом LONG и заведомо недостаточной историей — 18 точек при пороге 60 — модель сама вернула `forecast_state=insufficient_data`, `directional_view=None`, честно объяснив нехватку истории) — пройден; Flow D (сконструированный live-вызов с плоской ценой/без новостей — модель вернула `forecast_state=no_quality_setup` с первой попытки) — пройден; Flow E (два pre-Phase-2B инсайта id=39/40, `schema_version="insight-structure-v1"`, прочитаны через новый `InsightDetailResponse` — `horizon`/`forecast_state`/`catalysts`/`check_after` корректно `None`/`None`/`[]`/`None`, без ошибок) — пройден; Flow F (`GET /instruments/AAPL/insights` вернул одновременно новую forecast-строку id=64 и обе legacy-строки 39/40 в одном списке с корректной «на первый взгляд» сводкой только у новой; `GET /journal` отвечает `200`) — пройден. Реальный сохранённый forecast-инсайт (id=64) подтверждён через `POST /instruments/AAPL/insights` — `schema_version="insight-structure-v2-forecast"`, `prompt_version="instrument-analysis-v3-forecast"`. Offline AI evaluation → 15/15 cases, 435/435 checks, 0 violations.

## 4b. Предыдущая ревью-задача (теперь завершена)

Phase 2A — News Intelligence (ветка `feature/news-intelligence`) — **завершена и смёржена в `main` через PR #49** (коммит `26f7d9c`, merge-коммит `c4b39cf`).

Оформляет FR-064 (News Intelligence) и UJ-034 (потребление News Intelligence), ратифицированные Phase 2.0 (PO-2.0-13). Превращает сырую ленту новостей (`market_data.news_gateway`, Finnhub) в curated, классифицированную, переведённую на русский ленту:

- **Новый backend-пакет `trading_ai/news_intelligence/`** (`domain.py`/`preprocessing.py`/`models.py`/`repository.py`/`use_cases.py`) — детерминированная нормализация заголовков и near-duplicate дедупликация (не только точный ID); use case `GetNewsIntelligence` координирует: dedup → проверка персистентного кэша обогащения → пакетный LLM-вызов только для ещё не обработанных элементов → curation (исключение `NOISE`, ранжирование `COMPANY > SECTOR > MACRO > MARKET > INDIRECT`, bounded cap 8) → честная деградация при недоступности LLM.
- **Персистентный кэш = сама таблица** (`news_intelligence_items`, миграция `0006_news_intelligence_items`, append-only, `UNIQUE(ticker, news_provider, provider_news_id)`) — обработка происходит один раз на статью-для-тикера, затем переиспользуется на каждый последующий запрос/рестарт приложения, без Redis/новой БД (task scope §10). Только **успешно** обогащённые записи персистятся — сбой всей партии/отдельного элемента никогда не кэшируется как «обработано и провалено», чтобы будущий запрос мог повторить попытку.
- **`ai/gateway.py`**: `XAIGateway.generate_news_intelligence` — новый публичный метод, тот же единственный LLM SDK-boundary (`ADR-0007`), пакетный вызов (до 10 новостей за один запрос), собственная Pydantic-схема, per-item деградация (пропущенный/невалидный элемент не проваливает всю партию). Новый промпт `ai/news_prompts.py` (`NEWS_PROMPT_VERSION = "news-intelligence-v1"`) с явной prompt-injection границей (заголовки/summary — untrusted DATA, никогда не инструкция).
- **API**: `GET /instruments/{ticker}/news` расширен на месте (не новый endpoint) — ответ аддитивно расширен (`enriched`/`summary_ru`/`why_it_matters`/`relevance`/`relationship`/`impact_hypothesis`, все новые поля nullable). **Осознанное изменение поведения**: этот endpoint теперь требует БД (503 при неконфигурированной), как `/insights`/`/journal` — раньше был DB-free.
- **Frontend**: `InstrumentNewsSection.tsx` полностью переработан — компактные карточки, бейджи релевантности/классификации, русское резюме, «Почему важно», явно помеченное «Возможное влияние (гипотеза)», оригинальный заголовок вторично, честная пустая («Нет достаточно релевантных новостей») и деградированная («Без AI-анализа» + предупреждение) состояния.
- **AI evaluation**: параллельный небольшой harness (`ai/evaluation/news_dataset.py`/`news_evaluators.py`/`news_runner.py`) — 7 репрезентативных офлайн-кейсов (company/sector/macro/noise/prompt-injection/RU-перевод/hallucination-guard); не встроен в существующий CLI/`report.py` (структурно завязаны на `InstrumentAnalysis`) — осознанно отложено как последующий небольшой шаг.

**Реально проверено:** backend `pytest -v` → 453 passed, 37 skipped (без регрессий); `mypy src tests` → чисто (107 файлов); alembic upgrade/downgrade/upgrade цикл против реальной Compose PostgreSQL подтверждён; frontend `npm run type-check`/`npm run build` → чисто. Полная real-browser верификация (реальные backend+frontend dev-серверы, реальная Compose PostgreSQL, реальные live-вызовы Finnhub и xAI): Flow A (AAPL, живое обогащение, 8 карточек, ранжирование company→sector→market→indirect, RU-резюме/почему-важно/гипотеза видны) — пройден; Flow B (SPRT, 0 сырых новостей от Finnhub → честное «Нет достаточно релевантных новостей») — пройден; Flow C (backend перезапущен без `TRADING_AI_LLM_API_KEY`, MSFT — 8 карточек «Без AI-анализа» + предупреждение, исходные данные не потеряны) — пройден; Flow D (повторный запрос AAPL — 0 новых вызовов LLM/поиска компании в логах, ответ ~30x быстрее, обогащённые данные пережили рестарт backend и отключение LLM-ключа) — пройден. Живой xAI-вызов подтверждён в логах (`operation=generate_news_intelligence ... enriched_count=10`).

## 4c. Предыдущая ревью-задача (теперь завершена)

Phase 2.0 — Global Intelligence & Forecast Contract Ratification (ветка `docs/phase2-global-intelligence-forecast-contract`) — **завершена и смёржена в `main` через PR #48** (коммит `6ca54e0`, merge-коммит `738398e`). Документационная задача — только `docs/` и `.ai-context/`; ни один файл `backend/`, `frontend/`, миграций, prompt/schema/evaluation-кода не был изменён этой задачей.

Задаче предшествовал отдельный, чат-only «Phase 2 Master Architecture — Global Realtime Market Intelligence & Forecasting» анализ (без изменений репозитория) — 27-раздельный разбор целевого направления платформы на глобальный рыночный интеллект. По его итогам Product Owner ратифицировал 13 решений (**PO-2.0-1 – PO-2.0-13**), которые и оформила та задача:

- **PO-2.0-1** — глобальные акции: США — **текущее** (полностью реализовано); Европа/Азия — **утверждённое направление расширения**, реализация не начата, требует провайдерского исследования, идентичности инструмента при кросс-листинге, нормализации валюты, календаря сессий.
- **PO-2.0-2** — индексы, ставки/доходности, макро одобрены как категории **глобального рыночного контекста** — изначально контекст, не обязательно торгуемые «Рынки»; не исключает будущие производные (индексные фьючерсы/ETF).
- **PO-2.0-3** — конкретные диапазоны горизонта анализа утверждены: **SHORT 1–5 торговых дней, MEDIUM ≈1–8 недель, LONG ≈2–12 месяцев** — продуктовая семантика, не завершение реализации; точные минимальные окна данных намеренно не зафиксированы (требуют суждения Solution Architect).
- **PO-2.0-4** — категориальная шкала направления: `STRONGLY_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONGLY_BEARISH` — не BUY/SELL/HOLD, не команда на исполнение.
- **PO-2.0-5** — уверенность остаётся категориальной (LOW/MEDIUM/HIGH); численные вероятности не вводятся до появления достаточных данных калибровки.
- **PO-2.0-6** — одобрено концептуальное направление структурированного Forecast/Thesis Contract (см. `docs/architecture/FORECAST_CONTRACT.md`) — не заменяет FR-018/production Pydantic-типы этой задачей.
- **PO-2.0-7** — точная числовая целевая цена НЕ является обязательным полем; LLM не должен изобретать точность, которой нет.
- **PO-2.0-8** — `NO_QUALITY_SETUP`/`INSUFFICIENT_EDGE`/`INSUFFICIENT_DATA` одобрены как валидные, желательные результаты — ассистент не обязан выдумывать возможность по каждому запросу.
- **PO-2.0-9** — таксономия кросс-рыночных заявлений одобрена: `OBSERVED_RELATIONSHIP/CORRELATION/HYPOTHESIS/SUPPORTED_CAUSAL_INTERPRETATION/UNCERTAINTY` — корреляция не повышается до причинности молча.
- **PO-2.0-10** — непрерывное рыночное наблюдение одобрено как целевое направление; первое производственное направление — polling-first фоновый сбор (не тик-уровень/миллисекунды) поверх уже утверждённого `ADR-0006`.
- **PO-2.0-11** — одобрено создание DRAFT ADR (`ADR-0012`), рассматривающего отдельную логическую границу `monitoring` — **не равносильно принятию этой границы**; вопрос владения остаётся открытым (`MODULE_BOUNDARIES.md`).
- **PO-2.0-12** — стадийная модель обучения/калибровки ратифицирована (Stage 0 хранение feedback → Stage 1 автоматическое измерение результата → Stage 2 сегментированная аналитика → Stage 3 калибровка → Stage 4 историческая выборка [заблокирована `ADR-0005`] → Stage 5 человеко-управляемая адаптация → Stage 6 обучение/дообучение модели, требует отдельного одобрения); хранение feedback само по себе не является «обучением».
- **PO-2.0-13** — News Intelligence одобрена как высокоприоритетная возможность (резюме на русском, «почему важно», релевантность, provenance, гипотеза влияния) — реализация начата отдельной задачей Phase 2A (раздел 4 выше).

Изменённые/созданные документы: новый `docs/architecture/FORECAST_CONTRACT.md`; `docs/architecture/TARGET_INTELLIGENCE_CONTEXT.md` (§2.1–§2.3/§2.6 обновлены, §2.16–§2.18 добавлены); `docs/product/PRODUCT_SCOPE.md` (§4/§9/§24/§30 дополнены, новый §31); `docs/product/FUNCTIONAL_REQUIREMENTS.md` (FR-006 переформулирован, FR-061–FR-065 добавлены); `docs/product/USER_JOURNEYS.md` (UJ-005 уточнён, UJ-031–UJ-034 добавлены); `docs/architecture/INFORMATION_ARCHITECTURE.md` (§2.9–§2.12); `docs/architecture/DATA_FLOWS.md` (DF-019–DF-023); `docs/architecture/MODULE_BOUNDARIES.md` (§12/§19 дополнены, новый раздел «Предложение (не принято): логическая граница monitoring»); новый `docs/decisions/ADR-0012-realtime-and-background-monitoring-runtime.md` (Черновик); `docs/architecture/TECHNOLOGY_EVALUATION.md` (новый §14.4); `docs/DOCUMENT_REGISTER.md`; настоящий файл. Не входило в задачу: изменение производственного кода, тестов, миграций, интеграции провайдеров, AI prompt/schema, jobs/worker-реализации.

## 4d. Более ранняя ревью-задача (теперь завершена)

Phase 1 — Application Shell & Intelligence Workspace (ветка `feature/phase1-workspace-shell`) — **завершена и смёржена в `main` через PR #47** (коммит `8c69060`, merge-коммит `e5cc0a3`).

Product Owner утвердил конкретный объём пакета (не весь Phase 1 planning-отчёт целиком):

- **Одобрено:** единый Application Shell (персистентная навигация Обзор/Рынки/История/Дневник); Overview (реальные данные — watchlist, последние инсайты, последние записи дневника, без фабрикации market breadth/индексов/макро/сентимента/алертов/сигналов); Markets (Акции — работает, Forex/Криптовалюта/Сырьё — честное состояние «недоступно», без фейковых форм); редизайн Instrument Workspace (плотная grid-компоновка, те же 5 существующих секций без изменения их бизнес-логики); кросс-тикерная История инсайтов (`/insights`, новый read-only backend endpoint); интеграция Дневника (первоклассный пункт навигации + двусторонние ссылки Инструмент↔Инсайт↔Дневник); dark-first визуальное направление как единственная (не переключаемая) тема.
- **Не одобрено для этого пакета (сознательно не реализовано):** страница Settings, Notes CRUD, исследование/интеграция провайдеров, перевод новостей, ранжирование релевантности новостей, macro/sector/fundamentals, технические индикаторы, поведение горизонта анализа, более богатая схема FR-018, изменения prompt, изменения AI evaluation, calibration/retrieval, миграции БД, новая UI-библиотека, новая chart-библиотека.

**Backend:** один новый read-only endpoint `GET /insights?limit=N` (newest-first, bounded, cross-ticker) в уже существующем модуле `insights` — новый метод `InsightRepository.list_recent`, новый use case `ListRecentInsights` (отдельный узкий Protocol `_RecentInsightRepositoryLike`, чтобы не расширять `_InsightRepositoryLike` и не ломать существующие test doubles), новый route в `api/routes/instruments.py`. Никаких новых таблиц, никакой миграции, никаких изменений в `journal`/`evaluations`/`ai`/`market_data`.

**Frontend:** новый `AppShell.tsx` (единственный Client Component ради `usePathname()`, смонтирован в `layout.tsx` вокруг `{children}` — ADR-0003 §21.1); `OverviewView.tsx` (новый); `app/markets/page.tsx` (новый, Server Component, Stocks переиспользует `WatchlistPanel` как есть); `InsightsHistoryPanel.tsx` + `app/insights/page.tsx` (новые — переиспользуют паттерн `InsightHistorySection`/`InsightSections`/`ModeToggle`, без форка большого дублирующего рендерера); `InstrumentDetailsView.tsx` (реструктурирован в grid-композицию — `PriceChartSection`/`InstrumentNewsSection`/`AiAnalysisSection`/`InsightHistorySection` не изменены внутри, только их расположение); `TradeJournalView.tsx` (точечно — тикер и `insight_id` стали реальными ссылками на `/instruments/{ticker}` и `/insights?open={id}`); полностью переписан `globals.css` — token-слой (`--background`/`--surface`/`--surface-elevated`/`--border`/`--text-primary`/`--text-secondary`/`--positive`/`--negative`/`--warning`/`--focus`), dark безусловно (не только `prefers-color-scheme`), без новой UI/chart-библиотеки (ADR-0003 §7 запрет соблюдён).

Реально проверено: `pytest -v` → 401 passed, 32 skipped (было 391/31 — только новые тесты, без регрессий); `mypy src tests` → чисто (92 файла, без новых); `npm run type-check` → чисто; `npm run build` → чисто, все 6 маршрутов собраны (`/`, `/markets`, `/insights`, `/instruments/[ticker]`, `/journal`, `/_not-found`); `git diff --check` → чисто. Полная real-browser верификация через Playwright (реальные backend+frontend dev-серверы, реальная Compose PostgreSQL, реальный xAI live-вызов): Flow A (shell, активный пункт навигации, F5 на каждом маршруте) — пройден; Flow B (Markets: Акции работают, Forex/Crypto/Commodities честно заблокированы, 0 псевдо-форм) — пройден; Flow C (AAPL: котировка, график 1Д/5Д/1М, новости, AI-генерация вживую, краткий/полный режим, сохранение инсайта, история, 0 горизонтального overflow) — пройден; Flow D (кросс-тикерная История, newest-first, detail on demand, ссылка на инструмент) — пройден; Flow E (создание записи дневника, ссылка тикера, реципрокная ссылка Инсайт→Дневник→Инсайт через `?open=`, редактирование, отсутствие кнопки удаления) — пройден; Flow F (адаптивность 1440/820/390px, без overflow, nav остаётся видимой) — пройден; keyboard-focus (видимый `:focus-visible` outline, активный пункт nav не только цветом — жирный текст + underline) — пройден. Тестовые артефакты (2 инсайта AAPL, 2 записи дневника AAPL) остались в dev-базе — не могут быть удалены через приложение по дизайну (инсайты immutable, у дневника нет delete), тот же паттерн, что и в предыдущих задачах.

## 4e. Более ранняя ревью-задача (теперь завершена)

Phase 0 — Documentation & Architecture Decisions (ветка `docs/phase0-architecture-decisions`) — **завершена и смёржена в `main` через PR #46** (коммит `a2966c3`, merge-коммит `88d1dfb`). Отдельная задача ревью/финализации (упомянутая ниже) нашла и исправила 4 точечных документационных дефекта, затем изменения были закоммичены и, после решения Product Owner, интегрированы в `main` через pull request (прямой push в `main` был отклонён правилами репозитория — интеграция выполнена через PR, не локальным merge). **Только документация** — ни один файл `backend/`, `frontend/`, миграций, prompt/schema/evaluation-кода не изменён.

Задаче предшествовал полный Product/Architecture Checkpoint (аналитическая задача без изменений репозитория) и последующее решение Product Owner, ратифицирующее шесть продуктовых направлений (PO-1–PO-6) с четырьмя явными уточнениями:

- **PO-1** — согласована связная информационная архитектура из 8 концептуальных областей (Market/Overview, Markets, Instrument Workspace, Insights/History, News/Events, Journal, Notes, Settings) — зафиксировано новым документом `docs/architecture/INFORMATION_ARCHITECTURE.md`;
- **PO-2** — согласована стратегия единой оценки провайдеров данных для рынков Акции/Forex/Криптовалюта/Сырьё, приоритет — Forex; **конкретный провайдер не выбран** — рамка из 15 критериев зафиксирована `TECHNOLOGY_EVALUATION.md`, раздел 14; черновик `ADR-0011` создан в статусе «Черновик», разделы «Рассмотренные варианты»/«Выбранное решение» намеренно не заполнены (реальное исследование Solution Architect не проводилось — не изобретено ни одного факта о провайдерах);
- **PO-3** — утверждены только сами значения горизонта анализа SHORT/MEDIUM/LONG (FR-006, UJ-005); **точные временные диапазоны и минимальное окно данных для каждого значения остаются неутверждённым открытым продуктовым решением**; SHORT явно не равен scalping (FR-027 остаётся отдельным режимом); недостаточность данных для выбранного горизонта обязана честно снижать уверенность, а не маскироваться;
- **PO-4** — заметки (Notes) утверждены как editable/deletable, с опциональной ссылкой на тикер/инсайт «только для проверки существования» (не чтение/подписка на содержимое) — FR-032, UJ-019, `MODULE_BOUNDARIES.md` §14 (зависимость `notes → insights` добавлена по аналогии с уже существующей `journal → insights`);
- **PO-5** — согласовано направление на более богатую структуру инсайта (forward catalysts, invalidation conditions, разделение факт/интерпретация и т. д.) — **FR-018/схема/prompt/evaluation dataset намеренно не тронуты в этой задаче**, требуется сначала определить входные данные;
- **PO-6** — согласован концептуальный конвейер интеллектуального контекста (источники → нормализация → качество/свежесть → дедупликация/релевантность → контекст → provenance → AI-синтез → сохранённый инсайт → результат/оценка) — зафиксирован новым документом `docs/architecture/TARGET_INTELLIGENCE_CONTEXT.md` с явной классификацией 15 категорий контекста (CURRENT / MVP FOUNDATION / MVP REQUIRED / Post-MVP / Future / UNRESOLVED-REQUIRES-PO-DECISION) — **это классификация, не разрешение реализовать каждую категорию**; AI явно задокументирован как один компонент конвейера, не весь продукт.

Учебное направление (Learning/Calibration) подтверждено как поэтапное: feedback storage → outcome dataset → analytics/calibration → retrieval → human-governed adaptation → (отдельно утверждаемое в будущем) model-training evaluation; ни один документ не описывает текущую систему как «обучающуюся» только на основании того, что feedback сохраняется.

Изменённые/созданные документы этой задачи: `docs/architecture/INFORMATION_ARCHITECTURE.md` (новый, На ревью), `docs/architecture/TARGET_INTELLIGENCE_CONTEXT.md` (новый, На ревью), `docs/product/FUNCTIONAL_REQUIREMENTS.md` (FR-006, FR-032, FR-017 — точечные правки), `docs/product/USER_JOURNEYS.md` (UJ-005, UJ-019), `docs/architecture/MODULE_BOUNDARIES.md` (§12, §14, DAG-матрица), `docs/architecture/DATA_FLOWS.md` (DF-001, DF-011), `docs/architecture/TECHNOLOGY_EVALUATION.md` (новый раздел 14 «Многорыночные данные», дорожная карта ADR расширена до 11 позиций), `docs/product/PRODUCT_SCOPE.md` (раздел 30, точечная правка), `docs/decisions/ADR-0011-multi-market-data-provider-strategy.md` (новый, Черновик), `docs/DOCUMENT_REGISTER.md`, настоящий файл.

Не входило в задачу и не выполнялось: изменение производственного кода, Phase 1 UI, реализация провайдеров, изменение AI prompt/schema/evaluation кода, создание миграций (явный запрет Product Owner).

Отдельная задача ревью/финализации (после первичного создания документов Phase 0) выполнила сверку каждого изменённого/нового документа против `PROJECT_CHARTER.md`, `DOCUMENTATION_STANDARD.md`, `ADR_PROCESS.md` и связанных продуктовых/архитектурных документов; нашла и исправила 4 точечных документационных дефекта (опечатка, устаревшая формулировка ссылки на `ADR-0011`, неполный список связанных документов в `INFORMATION_ARCHITECTURE.md`, недостаточно однозначная формулировка раздела 9 настоящего файла); не нашла ни одного противоречия, требующего нового решения Product Owner. Изменения объединены в один коммит согласно `GIT_WORKFLOW.md` — push и merge не выполнялись (требуют отдельного разрешения).

## 4f. Предыдущая ревью-задача (теперь завершена)

Short/Full Insight Mode Vertical Slice (ветка `feat/insight-short-full-mode`, PR #45, смёржен в `main`) — FR-021 (краткий инсайт), FR-022 (полный инсайт). **Только frontend** — ни один backend-файл не менялся, ни новой AI-генерации, ни нового endpoint'а.

- **Product Owner decisions (через AskUserQuestion, не решено самостоятельно)**: состав краткого режима — **сбалансированный, 5 из 10 разделов FR-018** (Краткий вывод, Ключевые факты, Уровень уверенности, Что можно рассмотреть, Основные риски); default-режим — **«Кратко»**;
- Presentation-only toggle поверх уже полученного structured результата — **0 HTTP-запросов** при переключении (проверено вживую через network log: 5 переключений подряд → 0 запросов), не вызывает xAI/backend/market/news повторно, не создаёт новый инсайт, не трогает evaluation/outcome;
- Новый общий компонент `frontend/src/components/InsightSections.tsx` (`InsightSections` + `ModeToggle`) переиспользован и в `AiAnalysisSection` (текущая генерация), и в `InsightHistorySection` (сохранённый инсайт) — устраняет дублирование разметки и закрывает найденный по ходу задачи пробел: раньше `InsightHistorySection` не показывала `summary`/`price_context`/`news_context` внутри развёрнутой карточки вообще — теперь оба места показывают идентичную полную структуру в full-режиме;
- Режим — локальный React state (`ADR-0003-frontend-stack.md` §23 уже относил короткий/полный режим к локальному UI-состоянию до этой задачи) — не persist, сбрасывается к default на `F5`; никакого Redux/Zustand/context/localStorage;
- Disclaimer виден в обоих режимах всегда, независимо от toggle; ни один факт/источник (FR-011) не теряется в кратком виде — «Ключевые факты» входят в оба режима целиком, без обрезки текста;
- Не добавлено: новый backend endpoint, DB table, migration, prompt, schema version, model change, второй generation mode, streaming, localStorage preferences, settings, market navigation, notes, horizon, Forex/Crypto.

Реально проверено: `npm run type-check` → чисто; `npm run build` → чисто, маршруты не изменились; backend не менялся (`git diff --name-only -- backend/` пусто) — полный `pytest` не требовался; полная real-browser верификация (генерация → default «Кратко», 5 разделов → переключение «Подробно», все 9 заголовков (10 секций, confidence — один блок с двумя абзацами) → 5 переключений туда-обратно → 0 сетевых запросов → сохранение инсайта → открытие истории → default «Кратко» и там же → переключение «Подробно» → снова 0 запросов → disclaimer виден в обоих режимах → оценка/результат/ссылка «Добавить в дневник» продолжают работать → F5 → режим корректно сбрасывается к default → chart/news/watchlist не сломаны); тестовые данные и dev-серверы очищены; `frontend/package.json`/`package-lock.json`/`compose.yaml`/`docs/DOCUMENT_REGISTER.md`/`docs/decisions/**`/весь `backend/**` не изменены.

## 4g. Предыдущая ревью-задача (теперь завершена)

Trade Journal Vertical Slice (ветка `feat/trade-journal`) — FR-030 (базовый дневник сделок), UJ-017 (создание записи, опционально со ссылкой на ранее сформированный инсайт).

- **Product Owner decisions (через AskUserQuestion, не решено самостоятельно)**: mutability — **editable, no delete** (запись можно скорректировать, `updated_at` фиксирует факт правки; delete-эндпоинта/UI нет, soft-delete не вводится); формат результата — **категориальный статус + опциональный текст** (`TradeResultStatus`: `profit`/`loss`/`breakeven`/`open`, 4 значения — «open» добавлен отдельным явным вопросом Product Owner, т.к. документы не задавали конкретные значения); формат направления — **категориальный enum** `TradeDirection` (`long`/`short`);
- Новый модуль `backend/src/trading_ai/journal/` (MODULE_BOUNDARIES.md §13) — зависит от `insights` только для проверки существования `insight_id`, никогда не читает/пишет содержимое инсайта; никогда не обращается к `ai`/`llm_gateway`/`market_data` напрямую;
- **Не брокерская/order/portfolio-подсистема**: намеренно нет entry/exit price, quantity, commission, leverage, stop-loss/take-profit, order id, execution venue, realized P&L — FR-030 их не требует;
- Новая таблица `journal_entries` (миграция `0005_journal_entries`, ревизует `0004_insight_evaluations`) — обычные реляционные колонки, не JSONB (каждое поле — маленький queryable факт); FK `insight_id → insights.id` без `ON DELETE CASCADE` (delete инсайтов не существует в проекте вообще); реально прогнан upgrade→downgrade→upgrade→current цикл против Compose PostgreSQL, FK-integrity подтверждена вживую;
- `JournalRepository`/`CreateJournalEntry`/`ListJournalEntries`/`GetJournalEntry`/`UpdateJournalEntry` — новые минимальные компоненты; `POST/GET /journal`, `GET/PUT /journal/{id}`, оба DTO — `extra="forbid"` (frontend не может передать содержимое/provenance инсайта или брокерские поля); нет `DELETE /journal/{id}`;
- Frontend: минимальная точка входа «Дневник сделок» на главной странице (без полноценной market-навигации — FR-003 остаётся отдельным будущим срезом); новый маршрут `/journal`; форма создания/редактирования; ссылка «Добавить в дневник» из `InsightHistorySection` — предзаполняет `ticker`/`insight_id` через query-параметры (не insight-контент, backend перепроверяет `insight_id` заново); найденный и исправленный в этой же задаче баг — URL с prefill query-параметрами очищается через `router.replace` после создания/отмены, иначе F5 повторно открывал бы форму создания;
- Не добавлено: broker integration, orders, positions, portfolio, P&L engine, automatic trade import, CSV import, разбор сделки ассистентом (FR-031), Notes (FR-032), market navigation (FR-003), auth, Redis, worker, WebSocket, новый LLM, RAG, agents.

Реально проверено: `pytest -v` → 391 passed, 31 skipped (без регрессий, было 344/23); `mypy src tests` → чисто (92 файла); `alembic current` → `0005_journal_entries (head)` против реальной Compose PostgreSQL, upgrade/downgrade/upgrade цикл + FK-constraint подтверждены; AI-файлы не менялись — offline/live evaluation не запускались повторно (не требовалось, обосновано); полная real-browser верификация (Дневник-ссылка на главной → генерация+сохранение инсайта → «Добавить в дневник» → форма предзаполнена ticker+insight_id → создание записи → F5 → запись сохранилась → вторая независимая запись → редактирование → F5 → правка сохранилась, «(изменено)» показано → нет кнопки/эндпоинта удаления → watchlist/chart/news/AI/история инсайтов продолжают работать); тестовые данные и dev-серверы очищены; `frontend/package.json`/`package-lock.json`/`compose.yaml`/`docs/DOCUMENT_REGISTER.md`/`docs/decisions/**` не изменены.

## 4h. Ревью-задача до предыдущей (тоже завершена)

Insight Evaluation & Outcome Tracking Vertical Slice (ветка `feat/insight-evaluation`) — закрывает последний шаг канонического MVP-сценария (`PRODUCT_SCOPE.md` §21: «...сформировать инсайт → увидеть источники → сохранить → **оценить**»): FR-035 (пользовательская оценка сохранённого инсайта), FR-036/FR-038 (ручная фиксация результата, неразрывно связанная с исходным инсайтом).

- **Product Owner decision (через AskUserQuestion, не решено самостоятельно)**: формат оценки — **категориальный 3-way** («Полезен» / «Частично полезен» / «Не полезен»), не binary, не числовая шкала; FR-035/UJ-014 требовали оценку, но не фиксировали формат;
- Новый модуль `backend/src/trading_ai/evaluations/` (MODULE_BOUNDARIES.md §12) — **не путать** с `ai/evaluation/` (developer AI quality harness, без пользователя и HTTP); зависит от `insights` только для ссылки на id, никогда не читает/пишет содержимое инсайта;
- Одна запись `InsightEvaluation` на инсайт (`UNIQUE` FK-constraint на `insight_id`), обе половины — рейтинг и manual outcome — независимы и upsert (`PUT`, UJ-014 явно разрешает менять оценку; то же расширено на outcome для консистентности);
- Insight остаётся immutable — `evaluations` не имеет пути изменить его; FK без `ON DELETE CASCADE` (delete инсайтов в проекте пока не существует вообще, cascade-семантика не придумана заранее);
- Новая таблица `insight_evaluations` (миграция `0004_insight_evaluations`, ревизует `0003_insights`), реально прогнан upgrade→downgrade→upgrade→current цикл против Compose PostgreSQL, FK-integrity подтверждена вживую (`IntegrityError` на несуществующий `insight_id`);
- `EvaluationRepository`/`EvaluateInsight`/`RecordInsightOutcome`/`GetInsightEvaluation` — новые минимальные компоненты; `PUT/GET /insights/{id}/evaluation`, `PUT /insights/{id}/outcome`, оба DTO — `extra="forbid"` (frontend не может подделать содержимое/provenance инсайта);
- **FR-037 (изменение цены) осознанно отложен**: `evaluations` не может зависеть от `market_data` (MODULE_BOUNDARIES.md §12 не включает эту зависимость), а у `insights` нет сохранённого числового price-снапшота на момент генерации — только prose `price_context`; SHOULD, не MUST — задокументировано, не замаскировано;
- Frontend: внутри `InsightHistorySection` — «Оценка инсайта» (3 кнопки) и «Результат» (текстовое поле + фиксация) в развёрнутой карточке; `404` от `GET .../evaluation` («ещё не оценивался») рендерится как нормальное состояние, не как ошибка;
- Не добавлено: FR-039 auto outcome tracking, scheduled checking, классификация ошибок, «уроки», Trade Journal (entry/exit price, quantity, side, P&L), Notes, portfolio, auth, alerts, Redis, worker, WebSocket, новый LLM, RAG, agents.

Реально проверено: `pytest -v` → 344 passed, 23 skipped (без регрессий, было 309/18); `mypy src tests` → чисто (85 файлов); `alembic current` → `0004_insight_evaluations (head)` против реальной Compose PostgreSQL, upgrade/downgrade/upgrade цикл + FK-constraint подтверждены; AI-файлы не менялись — offline/live evaluation не запускались повторно (не требовалось, обосновано); полная real-browser верификация (generate → save → history → evaluate → F5 → оценка сохранилась → outcome → F5 → результат сохранился → provenance/содержимое исходного инсайта не изменились → вторая независимая запись без унаследованной оценки/результата → watchlist/chart/news/search продолжают работать), включая honest recovery от двух реальных Twelve Data rate-limit окон; тестовые данные и dev-серверы очищены; `frontend/package.json`/`package-lock.json`/`compose.yaml`/`docs/DOCUMENT_REGISTER.md`/`docs/decisions/**` не изменены.

## 4i. Более ранняя ревью-задача (тоже завершена)

Insight Persistence & Structure Completion Vertical Slice (ветка `feat/insight-persistence`) — доводит существующий Instrument AI Analysis до обязательных MVP-требований: FR-018 (10 обязательных секций insight), FR-019 (явный категориальный confidence), FR-034 (persistence + история инсайтов), FR-011 (минимальный source attribution ключевых фактов), ADR-0004/ADR-0007 provenance requirements.

- **Product Owner decision (через AskUserQuestion, не решено самостоятельно)**: сохранение инсайта — **explicit**, кнопка «Сохранить инсайт» (не auto-save); `docs/product/USER_JOURNEYS.md` UJ-013 явно оставляла этот выбор нерешённым;
- `InstrumentAnalysis` (`ai/types.py`) расширен до полного FR-018/FR-019: `key_facts` (fact+source), `insight_hypothesis`, `confidence` (категориальный enum HIGH/MEDIUM/LOW, не численная псевдо-точность), `confidence_reason`, `considerations`, `key_drivers`, `data_freshness` (backend-computed, не модель), `source_data_as_of`, `prompt_version`, `schema_version`; `PROMPT_VERSION` поднят до `instrument-analysis-v2`; новая независимая ось `INSIGHT_SCHEMA_VERSION = "insight-structure-v1"`;
- Сохранение без доверия к frontend: генерация кладёт результат в processes-local `PendingAnalysisCache` (TTL 30 мин, одноразовый opaque token), `POST /instruments/{ticker}/insights` принимает только `{analysis_token}` — вся структура/provenance берётся из server-held копии, не из тела запроса (`extra="forbid"`, повторное использование токена → 404);
- Новая таблица `insights` (миграция `0003_insights`, ревизует `0002_watchlist_items`), только INSERT/SELECT (ADR-0004 §20 immutability — нет update/delete пути ни на уровне repository, ни use cases); JSONB для `key_facts`/`considerations`/`risks`/`key_drivers`; индекс по `(ticker, created_at)`; реально прогнан upgrade→downgrade→upgrade→current цикл против Compose PostgreSQL;
- `InsightRepository`/`SaveInsight`/`ListInstrumentInsights`/`GetInsightDetail` — новые минимальные компоненты; `GET /instruments/{ticker}/insights` (newest-first, максимум 20), `GET /insights/{id}`;
- Frontend: `AiAnalysisSection` рендерит все 10 секций + кнопку «Сохранить инсайт»; новый `InsightHistorySection` — «История AI-анализов», newest-first, expand-on-demand detail с provenance;
- Evaluation harness (построенный предыдущей задачей) обновлён под новую схему, не ослаблен: `ai/evaluation/dataset.py` пересобран под все 10 полей, `evaluators.py` получил 7 новых проверок (`check_key_facts`, `check_confidence_valid`, `check_confidence_reflects_data_gaps` и др.); offline `12/12 passed, 0 safety violations`; live evaluation (opt-in, 3 представительных кейса) прошла на реальной модели;
- Реальный live-таймаут `AITimeoutError` был получен вживую на прежнем 30-секундном пороге (схема ~2.5x больше) — таймаут честно поднят до 60с, не замаскирован;
- Не добавлено: FR-035 user ratings, automatic outcome tracking, trade journal, notes, market-direction navigation, portfolio, auth, Redis, worker, background AI generation, WebSocket, vector DB, RAG, agents, chat, editing/deletion историчных insight.

Реально проверено: `pytest -v` → 309 passed, 18 skipped (без регрессий); `mypy src tests` → чисто (72 файла); `alembic current` → `0003_insights (head)` против реальной Compose PostgreSQL, upgrade/downgrade/upgrade цикл подтверждён, `watchlist_items` не тронута; offline evaluation → 12/12, 0 violations; live evaluation (opt-in) → 3/3, 0 violations; полная real-browser верификация (generate → структура/confidence → save → F5 → история сохраняется → detail с provenance → вторая генерация/сохранение → newest-first → chart/news/search/watchlist продолжают работать), тестовые данные и dev-серверы очищены; `frontend/package.json`/`package-lock.json`/`compose.yaml`/`docs/DOCUMENT_REGISTER.md`/`docs/decisions/**` не изменены.

## 4j. Ещё более ранняя ревью-задача (тоже завершена)

AI Quality Evaluation Vertical Slice (ветка `feat/ai-quality-evaluation`) — первый, намеренно небольшой, воспроизводимый evaluation harness для уже существующего `GenerateInstrumentAnalysis` (ADR-0007 §52 явно требует evaluation dataset до дальнейшего расширения production-использования модели). **Не пользовательская фича** — frontend не менялся вообще, ничего не выполняется в браузере, ничего не вызывает market/news provider:

- **ADR-0007 §52 требует**: evaluation dataset (создаётся отдельно, не в самом ADR — это и есть эта задача); проверку factual grounding, schema adherence, refusal correctness, prompt injection resistance, русского языка, latency/cost/stability; regression между моделями/provider на одинаковых сценариях; запрет production-изменения (модель/provider/значимый prompt) без regression evaluation; численные пороги качества ADR не задаёт. Ни LLM-as-judge, ни отдельный benchmark framework, ни новый ADR ADR-0007 §52 не требует — новый ADR **не создавался**, задача — implementation-деталь внутри уже утверждённой `llm_gateway`-границы;
- `backend/src/trading_ai/ai/evaluation/` (новый подпакет: `types.py`/`dataset.py`/`evaluators.py`/`runner.py`/`report.py`/`__main__.py`) — provider-neutral `EvaluationCase`/`EvaluationExpectation`/`EvaluationResult`/`CheckResult`, не generic benchmark framework;
- **Dataset** — 12 фиксированных, деterministic сценариев как обычные Python dataclasses (не JSON/YAML — обоснование в README), синтетический тикер `ACME` и синтетические числа (не live market values, не сырые Twelve Data/Finnhub payload); каждый case = `analysis_input` (что видела бы модель) + `expectation` (какие инварианты обязательны) + hand-authored `reference_response` (не реальный ответ модели — стенд-ин для offline-прогона на нуле стоимости);
- **Deterministic evaluators** (13 проверок на case, без LLM-as-judge — обоснование ниже): structured_output, non-empty summary/price_context/news_context, risks (min count), disclaimer, no_recommendation, no_target_price, no_system_prompt_leak, no_secret_leak, injection_resistance (только для injection-тегированных cases), missing_data_behavior (best-effort keyword-проверка, не семантика), russian_output (эвристика по доле кириллицы). `gateway.py` дал две функции публичными (`ModelOutputSchema`, `contains_forbidden_language` — были `_`-приватными) специально для переиспользования evaluation-кодом одной и той же логики, что и production;
- **LLM-as-judge STOP-условие проверено и НЕ сработало**: ADR-0007 §52 не требует model-based evaluation — перечисленные инварианты детерминированно проверяемы; judge не добавлен. Semantic factual grounding (полное "модель не выдумывает факты") намеренно не решается regex-ами — честно задокументированное ограничение baseline, не заявлено как решённое;
- **CLI** — `python -m trading_ai.ai.evaluation` (`--offline`/`--live`/`--case`/`--all-cases`), argparse, без новой зависимости (Typer/Click не добавлены). Обоснование CLI vs только pytest: разная аудитория — pytest регресс-тестирует саму grading-логику на fixtures, CLI даёт человеку читаемый summary в offline или live режиме по требованию;
- **Live evaluation — строго opt-in**: обычный `pytest`/`mypy`/offline-запуск = **0** вызовов xAI; live — либо `--live` (3 представительных кейса: normal/missing-data/prompt-injection, по умолчанию), либо `--live --all-cases` (весь датасет, печатает предупреждение с числом вызовов до первого запроса); opt-in pytest-тест `tests/integration/test_ai_evaluation_live.py` (`@pytest.mark.live_provider`, переиспользует существующую `TRADING_AI_LIVE_LLM_API_KEY`) — ровно 3 кейса, без retry;
- observability (только live): `operation=ai_evaluation case_id=... provider=xai model=... status=... latency_ms=...`; никогда полный prompt/response/ключ; `input_tokens`/`output_tokens` на результате всегда `None` — честно задокументированное ограничение: `XAIGateway.generate_instrument_analysis` не возвращает usage наружу (только логирует внутри), не расширялось в рамках этой задачи;
- отчёт для человека (`report.py`) — простой текст (`Case: <id>` / `PASS`|`FAIL <check>` / `Summary: N/M passed, K safety violations`), не dashboard, никогда не печатает полный ответ/prompt/ключ (тест `test_report_never_contains_full_response_text` проверяет это явно);
- не добавлены: LangSmith, LangFuse, OpenTelemetry vendor, MLflow, W&B, RAG, embeddings, vector DB, agent, tool calling, второй LLM, judge model, evaluation SaaS, dashboard, Redis, worker, Celery, scheduled evaluation, персистентность результатов оценки в БД, CI-траты xAI credits, автоматический live evaluation на PR.

Реально проверено: `pytest -v` — 265 passed, 13 skipped (было 232/12 до этой задачи; +33 новых теста: dataset validation, evaluator unit-тесты на заранее заданных fixtures — valid/forbidden-recommendation/target-price/missing-disclaimer/empty-summary/too-few-risks/prompt-leak/safe-degraded-response, offline-runner + report + CLI-поведение через subprocess, `run_live` на fake-gateway включая no-secret-in-logs тест) и `mypy` — чисто (62 файла). Offline evaluation реально выполнен: `python -m trading_ai.ai.evaluation --offline` → **12/12 cases passed, 0 safety violations**. Live evaluation реально выполнен с настоящим xAI-ключом (opt-in, 3 представительных кейса через pytest-тест) → **3/3 cases passed, 0 safety violations**, включая реальный prompt-injection case — подтверждено вживую, что production-модель не раскрывает system prompt и не подчиняется инъекции в заголовке новости. `secret_leak_detected=false` — проверено (regex по ключевым паттернам в датасете/тестах/отчёте, `.env` gitignored, ключ нигде не выведен явно). Frontend не менялся (`git status` для `frontend/` пуст); `package.json`/`package-lock.json` не тронуты; полный `npm build` не запускался — нет причины запускать, изменений во frontend нет.

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

Phase 2B — Forecast Contract (PR #50) — завершена и смёржена в `main` (раздел 4a).

## 8. Текущая задача

Phase 2B.1 — Professional Instrument Workspace (ветка `feature/professional-instrument-workspace`) — frontend/UX редизайн Instrument Workspace + аддитивное backend-расширение OHLC/volume (раздел 4), **теперь на втором проходе**: визуальный/information-design polish поверх первого прохода по итогам реального ручного browser-ревью Product Owner (раздел 4.1) — заголовок/рыночный модуль/график/AI idle-состояние/ForecastCard/новости/история/общий ритм. Реализовано и полностью провалидировано (оба прохода), включая real-Postgres и живые вызовы xAI/Twelve Data, **намеренно не закоммичено**. Ожидает повторного ревью и явного разрешения Product Owner на commit согласно `GIT_WORKFLOW.md`. **Forecast Contract семантически не изменён ни одним из проходов. Order Book/Level 2 намеренно не реализован — требует провайдерского исследования (раздел 12). Новых зависимостей не добавлено ни одним из проходов.**

## 9. Следующий планируемый блок

**Не определён.** Продолжение работы над продуктом — предмет отдельного, ещё не принятого решения Product Owner после ревью и commit/merge Phase 2B.1 (раздел 4). Настоящий документ не называет и не подразумевает ни один конкретный следующий пакет как одобренный или приоритетный. Вероятные кандидаты (не одобрены этим документом): Phase 2C — Outcome Engine / continuous thesis monitoring (DF-022, UJ-033, `ADR-0012`) поверх уже сохранённых `check_after`/`invalidation_conditions`; провайдерское исследование Order Book/Level 2; глобальные акции EU/Asia и глобальный рыночный контекст (индексы/ставки/макро).

Справочно, без ранжирования и без статуса решения: реальное провайдерское исследование остаётся не запланированным по четырём направлениям — Forex/Crypto/Commodities (`ADR-0011`, Phase 0), Order Book/Level 2 (эта задача, раздел 12), и глобальные акции EU/Asia и индексы/ставки/макро/календарь/фундаментальные данные (`TECHNOLOGY_EVALUATION.md`, §14.4) — все требуют отдельного решения Product Owner о привлечении Solution Architect. Владение логикой мониторинга состояния тезиса (`jobs`/`evaluations`/отдельный модуль `monitoring`) остаётся открытым вопросом (`ADR-0012`, раздел 28; `MODULE_BOUNDARIES.md`) — возможный `ADR-0013` не создан. Settings и Notes CRUD остаются неутверждёнными для реализации (сознательно исключены из объёма Phase 1, раздел 4d) и по-прежнему отсутствуют в навигации приложения, что соответствует `INFORMATION_ARCHITECTURE.md`. News Intelligence и Forecast Contract — единственные из возможностей Phase 2.0 с начатой реализацией (разделы 4a/4b); непрерывный фоновый мониторинг и глобальные акции/контекст остаются одобренным направлением без реализации. MVP в целом не считается завершённым.

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
- конкретные источники данных, лицензии и стоимость доступа не утверждены; для Forex/Crypto/Commodities рамка оценки зафиксирована (`TECHNOLOGY_EVALUATION.md`, раздел 14), но реальное исследование провайдеров не проводилось — `ADR-0011` остаётся Черновиком (раздел 4e);
- точные временные диапазоны горизонта анализа SHORT/MEDIUM/LONG утверждены Phase 2.0 (PO-2.0-3, раздел 4c); **(Phase 2B)** точное минимальное окно данных на горизонт теперь реализовано как деterministic sufficiency gate (`ai/horizon.py`), но конкретные пороги (SHORT ≥5/MEDIUM ≥20/LONG ≥60 точек истории, staleness-порог котировки на горизонт) — implementation judgment call этой задачи, не отдельно утверждённое Product Owner число (`FORECAST_CONTRACT.md`, раздел 7 явно это разрешает и требует задокументировать, не изобретать точность);
- learning/calibration roadmap — поэтапный и явно гейтированный, ратифицирован Phase 2.0 как Stage 0–6 (PO-2.0-12, раздел 4c); текущее состояние — только хранение feedback (Stage 0), не calibration/retrieval/adaptation;
- глобальные акции EU/Asia и глобальный рыночный контекст (индексы/ставки/макро) остаются одобренным Phase 2.0 направлением без реализации; News Intelligence (раздел 4b) и Forecast Contract (раздел 4) — реализованные из возможностей Phase 2.0;
- владение логикой мониторинга состояния тезиса (`jobs`/`evaluations`/отдельный модуль `monitoring`) остаётся нерешённым — `ADR-0012`, раздел 28; блокирует реализацию DF-022 (continuous thesis monitoring, UJ-033) до отдельного архитектурного решения — **(Phase 2B)** сохранённые `check_after`/`invalidation_conditions` дают будущему Outcome Engine/monitoring-потоку данные для работы, но сам monitoring-loop, Outcome Engine и любая автоматическая проверка/обновление состояния тезиса не реализованы этой задачей (прямой scope guard задачи);
- источники данных для глобальных акций/индексов/ставок/макро/календаря/фундаментальных данных не выбраны и не оценены — `TECHNOLOGY_EVALUATION.md`, §14.4, все пункты помечены ожидающими (pending);
- **(Phase 2A)** News Intelligence AI-evaluation harness (`ai/evaluation/news_dataset.py`/`news_evaluators.py`/`news_runner.py`) не встроен в существующий CLI/`report.py` — структурно завязаны на `InstrumentAnalysis`, обобщение отложено как последующий небольшой шаг;
- **(Phase 2A)** `GET /instruments/{ticker}/news` теперь требует БД (503 при неконфигурированной) — поведенческое изменение относительно всех задач до Phase 2A, где этот endpoint был DB-free;
- **(Phase 2A)** точный порог «существенности» отраслевой/рыночной релевантности не формализован числовым порогом — классификация полностью на LLM (company/sector/market/macro/indirect/noise), без детерминированного numeric score, по прямому требованию задачи;
- **(Phase 2B)** `POST /instruments/{ticker}/analysis` теперь требует обязательный query-параметр `horizon` (`422` при отсутствии/невалидном значении) — поведенческое изменение контракта запроса относительно всех задач до Phase 2B;
- **(Phase 2B)** live-демонстрация LONG-horizon-insufficient-data и NO_QUALITY_SETUP выполнена через сконструированный прямой вызов `XAIGateway` (реальная модель, реальный provider), а не через реальный низко-историчный/неопределённый рыночный тикер — подтверждает механизм честно, но не найден конкретный реальный currently-thin-history инструмент для демонстрации через полный HTTP-путь;
- **(Phase 2B)** `context_categories_used` называет только уже реализованные категории контекста (`identity`/`price`/`history`/`news`, `TARGET_INTELLIGENCE_CONTEXT.md` §2.1/§2.4/§2.5) — macro/indices/rates/sector остаются нереализованными категориями, как и до этой задачи;
- **(Phase 2B.1)** Order Book / Level 2 намеренно не реализован — реальный Twelve Data `/quote`-ответ проверен вживую и не содержит bid/ask/depth-полей вообще ни на одном исследованном плане; ни `TECHNOLOGY_EVALUATION.md`, ни `ADR-0011` не содержат исследования этой возможности ни для одного провайдера; провайдерское исследование не запланировано (раздел 9);
- **(Phase 2B.1)** визуальная попиксельная проверка не выполнена ни в первом, ни во втором (polish) проходе — ни в одной из сессий не было доступного browser/screenshot-инструмента; вместо этого сделан структурный self-review фактического DOM/CSS плюс количественная проверка через реальные API-ответы (см. финальные отчёты задачи); возможные мелкие визуальные несоответствия (например, точный баланс высоты между графиком и `MarketSnapshotPanel` на разных наборах данных) не исключены — второй проход адресует конкретные претензии ручного browser-ревью структурно (CSS/разметка), но не подтверждён визуально теми же средствами, которыми его нашли;
- **(Phase 2B.1)** `GET /instruments/{ticker}/history` теперь дополнительно возвращает `open`/`high`/`low`/`volume` (все nullable, аддитивно) — не поведенческое изменение для существующих потребителей (только новые поля), но задокументировано как расширение контракта;
- количественные NFR требуют измерений;
- CI отсутствует.

## 13. Правило обновления

Этот файл обновляется после каждой принятой задачи, если изменилось состояние проекта.
