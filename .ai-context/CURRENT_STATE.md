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

## 4a. Предыдущая ревью-задача (теперь завершена)

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

AI Quality Evaluation Vertical Slice — завершён.

## 8. Текущая задача

Insight Persistence & Structure Completion Vertical Slice — на ревью.

## 9. Следующий планируемый блок

Вероятно insight evaluation / journal / market navigation — только согласно roadmap после merge Insight Persistence & Structure Completion Vertical Slice; не предопределено этой записью, MVP в целом не считается завершённым.

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
