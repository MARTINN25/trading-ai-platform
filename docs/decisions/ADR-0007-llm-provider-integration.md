# ADR-0007 — LLM Provider Integration Strategy

**Статус:** На ревью
**Владелец решения:** Product Owner
**Автор предложения:** Solution Architect
**Дата:** 2026-08-05
**Назначение:** определить выбор начального LLM-провайдера и provider-neutral стратегию интеграции через llm_gateway.

---

## 1. Номер ADR

ADR-0007

## 2. Название

LLM Provider Integration Strategy

## 3. Статус

На ревью

## 4. Дата

2026-08-05

## 5. Владелец решения

Product Owner

## 6. Автор предложения

Solution Architect

## 7. Связанные документы

- [`PROJECT_CHARTER.md`](../../PROJECT_CHARTER.md)
- [`docs/architecture/ENGINEERING_PRINCIPLES.md`](../architecture/ENGINEERING_PRINCIPLES.md)
- [`docs/architecture/LOGICAL_ARCHITECTURE.md`](../architecture/LOGICAL_ARCHITECTURE.md)
- [`docs/architecture/MODULE_BOUNDARIES.md`](../architecture/MODULE_BOUNDARIES.md)
- [`docs/architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md)
- [`docs/architecture/FAILURE_MODEL.md`](../architecture/FAILURE_MODEL.md)
- [`docs/architecture/TECHNOLOGY_EVALUATION.md`](../architecture/TECHNOLOGY_EVALUATION.md)
- [`docs/product/PRODUCT_SCOPE.md`](../product/PRODUCT_SCOPE.md)
- [`docs/product/FUNCTIONAL_REQUIREMENTS.md`](../product/FUNCTIONAL_REQUIREMENTS.md)
- [`docs/product/NON_FUNCTIONAL_REQUIREMENTS.md`](../product/NON_FUNCTIONAL_REQUIREMENTS.md)

## 8. Связанные ADR

- `ADR-0001` — Backend Language and Runtime (утверждён).
- `ADR-0002` — Backend API Adapter (утверждён; transport-слой не владеет бизнес-логикой; критичные фоновые задачи не выполняются через `BackgroundTasks`).
- `ADR-0003` — Frontend Stack (утверждён; frontend не обращается к LLM напрямую, только к FastAPI Application API).
- `ADR-0004` — Primary Data Store (утверждён; PostgreSQL — transactional system of record; секреты не хранятся как обычные бизнес-данные).
- `ADR-0005` — Vector Search Strategy (утверждён; retrieved context не является фактом; prompt injection из retrieved documents должен учитываться).
- `ADR-0006` — Background Jobs and Queue (утверждён; критичные и долговечные фоновые задачи — отдельный worker-процесс; PostgreSQL-backed durable queue без отдельного broker в MVP; exactly-once не обещается).

## 9. Заменяет

Не применимо.

## 10. Заменён документом

Не применимо.

## 11. Контекст

`MODULE_BOUNDARIES.md` и `LOGICAL_ARCHITECTURE.md` определяют `llm_gateway` как отдельную архитектурную границу, через которую `analysis` обращается к LLM, а `application` оркестрирует use cases. `ADR-0005` установило, что retrieved context не является фактом и что prompt injection из retrieved документов должен явно учитываться. `ADR-0006` установило, что долгие или повторяемые задачи (включая LLM-задачи) выполняются отдельным worker-процессом без блокировки HTTP-запроса, а exactly-once не обещается ни для одного механизма платформы. `ENGINEERING_PRINCIPLES.md` требует, чтобы LLM не считался источником фактов, чтобы provenance сохранялся, недостоверность отражалась явно, стоимость измерялась, секреты не попадали в код и логи, а абсолютная безошибочность не обещалась.

Ни провайдер, ни модель, ни способ интеграции LLM ещё не выбраны — это предмет настоящего ADR.

Дата проверки данных, использованных в настоящем ADR: 2026-08-05 (раздел 66 «Источники исследования»). Цены, модели, лимиты и SDK являются изменяемыми данными и не считаются действительными бессрочно.

## 12. Проблема

Как платформа интегрируется с внешним LLM-провайдером; какой провайдер является первым кандидатом для MVP; как SDK и API конкретного провайдера изолируются внутри `llm_gateway`; какие данные разрешено передавать провайдеру; как выбираются модель и её версия; как контролируются prompts, structured output, tool calling, retries, timeouts, rate limits, стоимость, аудит и наблюдаемость; как происходит замена провайдера; допускается ли fallback между провайдерами; какие гарантии платформа не должна обещать.

Настоящий ADR не выбирает: конкретный model ID навсегда, конкретную версию SDK, конкретные temperature/top_p значения, конкретный reasoning level, конкретный token budget, конкретные числовые rate limits, конкретные timeout/retry значения, embedding model, reranker, speech/image/video model, provider-specific search tools как обязательную часть архитектуры, автоматический multi-provider fallback, OpenAI-compatible API как единственный внутренний контракт, LangChain/LlamaIndex/Semantic Kernel или иной orchestration framework.

## 13. Ограничения

- решение принимается до появления provider adapter кода — миграционная стоимость минимальна;
- `llm_gateway` уже утверждён архитектурно как единственная граница обращения к LLM (`MODULE_BOUNDARIES.md`) — эта граница принимается как данность, не пересматривается;
- долгие/повторяемые LLM-вызовы используют worker-процесс, установленный `ADR-0006`, — не пересматривается;
- retrieved context и LLM output не являются источником фактов (`ADR-0005`, `ENGINEERING_PRINCIPLES.md`) — не пересматривается;
- один разработчик отвечает за эксплуатацию — множественные заранее реализованные provider adapters не вводятся без доказанной необходимости;
- MVP разворачивается на одном сервере (`PRODUCT_SCOPE.md`, раздел 22);
- решение не выбирает конкретный model ID навсегда, конкретную версию SDK или числовые параметры — это выходит за рамки задачи;
- официальные источники (раздел 66) не подтверждают безусловную exactly-once или 100%-ную безошибочность ни для одного провайдера — это утверждение не используется как основание решения.

## 14. Движущие факторы решения

Критерии сравнения (раздел 17) выведены из `ENGINEERING_PRINCIPLES.md`, `MODULE_BOUNDARIES.md`, `ADR-0005`, `ADR-0006` и контекста задачи: соответствие продуктовым сценариям, structured output, tool calling, streaming, usage metadata, rate-limit visibility, cost visibility, batch/asynchronous requests, model lifecycle, официальный Python SDK, error taxonomy, retry guidance, data/privacy controls, vendor lock-in, provider-neutral adaptation, наблюдаемость, auditability, reproducibility, эксплуатационная сложность, обратимость, будущий рост.

## 15. Термины

**Provider** — внешняя организация и API, предоставляющие модель.

**Model** — конкретная модель или model ID внутри provider.

**llm_gateway** — единственная внутренняя архитектурная граница для вызовов LLM.

**Provider adapter** — инфраструктурная реализация контракта `llm_gateway` для конкретного provider.

**Prompt template** — версионируемое описание instruction/context structure.

**Structured output** — ответ, который должен соответствовать определённой внутренней схеме.

**Tool call** — предложение модели вызвать разрешённый инструмент. Модель не исполняет инструмент самостоятельно.

**Usage** — provider-reported или локально измеренные input/output/cached/reasoning tokens и другие единицы биллинга.

**Fallback** — повтор запроса через другую модель или provider. Не равен retry того же provider.

**Retry** — повтор вызова при временной ошибке по той же утверждённой политике.

## 16. Рассмотренные варианты

Рассмотрены ровно четыре варианта:

- **Вариант A — xAI** (предварительный первый provider).
- **Вариант B — OpenAI.**
- **Вариант C — Anthropic.**
- **Вариант D — Google Gemini.**

Local/self-hosted model не рассматривается как пятый равноправный вариант — это возможный будущий сценарий пересмотра (раздел 63), не выбираемый настоящим ADR.

## 17. Критерии сравнения

Все качественные выводы — архитектурная оценка на основании официальной документации, не измерена в рамках ADR и не является benchmark. Ни один provider не объявляется «лучшим вообще».

| № | Критерий | A. xAI | B. OpenAI | C. Anthropic | D. Google Gemini |
|---|---|---|---|---|---|
| 1 | Соответствие продуктовым сценариям | архитектурная оценка: покрывает text analysis, structured output, tool calling — достаточно для сценариев `analysis`/`insights`; не измерено в рамках ADR | аналогично, дополнительно официально «guaranteed» structured output | аналогично, дополнительно официально «guaranteed» strict tool-input/structured output | аналогично, с дополнительным батч/кэш инструментарием |
| 2 | Text analysis | поддерживается Responses API | поддерживается Responses API | поддерживается Messages API | поддерживается Interactions API |
| 3 | Русский язык | официально не подтверждено отдельным документом ни для одного provider в рамках этого исследования — открытый вопрос (раздел 63), проверяется quality evaluation (раздел 52) | то же | то же | то же |
| 4 | Structured output | `response_format` json_schema (strict) / json_object (раздел 66) | Structured Outputs — официально гарантированное соответствие схеме, ограничения по числу полей/уровней вложенности, только на определённых моделях | `output_config.format` (constrained decoding) или `strict: true` на tool — официально гарантировано, ограниченное подмножество JSON Schema (без min/maxLength, без рекурсии) | JSON-структурированный вывод официально поддержан |
| 5 | Tool calling | поддерживается, JSON-schema object type обязателен, parallel по умолчанию | поддерживается, модель только предлагает вызов | поддерживается, включая server-side tools (web_search/web_fetch/code_execution), выполняемые на инфраструктуре Anthropic | поддерживается, режимы auto/any/none, parallel и последовательные вызовы |
| 6 | Streaming | SSE, `stream: true`, официально рекомендовано увеличивать client timeout при streaming+reasoning | SSE через Responses endpoint, типизированные lifecycle-события | SSE, SDK даёт accumulated-helper поверх потока | `stream=True`, `step.delta` события |
| 7 | Usage metadata | `input_tokens`/`output_tokens`/`output_tokens_details.reasoning_tokens` | usage объект подтверждён документацией по pricing (cached input отдельно); точные имена полей reasoning/cached в Responses API usage не подтверждены официальной документацией в рамках этого исследования | `input_tokens`/`output_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens`, server tool usage отдельно | `total_input_tokens`/`total_output_tokens`/`total_cached_tokens`/`total_thought_tokens`/`total_tool_use_tokens`/`total_tokens` |
| 8 | Rate-limit visibility | RPS+TPM, тиры по spend; официально нет rate-limit-status заголовков — проверяется через Console UI (документационный пробел) | RPM/RPD/TPM/TPD/IPM, 6 тиров, официально документированы | RPM/ITPM/OTPM по tier, token-bucket, живые заголовки `anthropic-ratelimit-*`, отдельный Rate Limits API | RPM/TPM/RPD по tier + отдельный spend-based rate limit (429 RESOURCE_EXHAUSTED независимо от RPM/TPM/RPD) |
| 9 | Cost visibility | официальная pricing-страница, по токенам, с порогом >200k токенов для части моделей | официальная pricing-страница, cached input ~90% скидка (пример), batch ~50% | официальная pricing-страница по моделям, prompt caching с явными коэффициентами (1.25x/2x/0.1x) | официальная pricing-страница по тирам, context caching биллится отдельно |
| 10 | Batch/asynchronous requests | Batch API есть; официально исключает новейшую на дату исследования модель (grok-4.5) из batch | Batch API, .jsonl, ~24ч цель, ~50% скидка | Message Batches API, custom_id, собственные rate limits | Batch API, inline/JSONL, ~24ч цель («часто быстрее»), ~50% скидка, хранение результатов 6 недель |
| 11 | Model lifecycle | alias `<model>`/`<model>-latest`/`<model>-<date>`; retirement с авто-редиректом (биллинг может измениться незаметно) | tiered deprecation notice (GA ≥6мес, специализир. ≥3мес, preview ~2нед); отдельный статус Legacy | Active→Legacy→Deprecated→Retired, ≥60 дней уведомления | 4 стадии: Stable/Preview/Latest/Experimental, ≥2 недели уведомления; Latest — динамический alias, «hot-swapped» при новых релизах |
| 12 | Stable vs preview models | датированные pinned-модели официально доступны как практика фиксации | preview официально не рекомендован для business-critical production | явного отдельного «preview»-статуса в исследованных источниках не выявлено, только полный lifecycle Active→Retired | явно формализовано: Stable/Preview/Latest/Experimental с разными гарантиями |
| 13 | Официальный Python SDK | `xai-sdk` (нативный) + официально документированная OpenAI-совместимость | `openai` | `anthropic` (sync+async, опционально `aiohttp`) | `google-genai` |
| 14 | API maturity | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR |
| 15 | Error taxonomy | документированные HTTP-коды (400/401/403/404/405/415/422/429/202) | документированные HTTP-коды + SDK exception-классы | SDK exception-классы на каждый HTTP-статус (400/401/403/404/409/422/429/5xx) + connection/timeout errors | явное разделение retryable (429/503/5xx/408) и non-retryable (400/403) |
| 16 | Retry guidance | официально тонкая — нет документированного `Retry-After`, нет нормативного backoff-алгоритма (документационный пробел) | honour `Retry-After`, backoff+jitter при отсутствии; SDK auto-retry; отдельная документированная политика для «Slow Down» (удержание 15 мин, затем плавный рост) | SDK auto-retry по умолчанию (2 попытки, короткий exponential backoff) на connection/408/409/429/5xx | SDK auto-retry по умолчанию (~4 попытки, ~1с начальная задержка, до 60с) на 429/503/5xx/408 |
| 17 | Data/privacy controls | по умолчанию не используется для обучения; 30-дневное шифрованное хранение для abuse detection; опциональный ZDR (сам provider не рекомендует его большинству клиентов, отключает часть функций) | не используется для обучения с 2023-03-01 без явного opt-in; 30-дневное abuse-monitoring хранение; ZDR доступен по заявке | по умолчанию не используется для обучения; обучение только через явный opt-in (feedback); feedback-помеченные данные — до 5 лет хранения | явное разделение по тиру: free — используется для улучшения продукта; paid — не используется |
| 18 | Regional/availability constraints | не подтверждено отдельным исследованием в рамках ADR — открытый вопрос (раздел 63) | документирован код 403 «geographic restriction»; детальный региональный охват не подтверждён отдельно | не подтверждено отдельным исследованием в рамках ADR — открытый вопрос | не подтверждено отдельным исследованием в рамках ADR — открытый вопрос |
| 19 | Provider-specific search tools | официально документирован web/X search как opt-in инструмент (не обязательная часть архитектуры) | не подтверждено отдельным исследованием в рамках ADR | официально документированы server-side tools (web_search/web_fetch/code_execution), выполняемые на инфраструктуре provider | не подтверждено отдельным исследованием в рамках ADR |
| 20 | Vendor lock-in | снижается архитектурной границей `llm_gateway` (раздел 20), одинаково для всех четырёх | то же | то же | то же |
| 21 | Provider-neutral adaptation | достижима через provider adapter (раздел 22); нативный SDK + OpenAI-совместимый режим дают два пути адаптации | достижима через provider adapter | достижима через provider adapter | достижима через provider adapter |
| 22 | Windows development | архитектурная оценка: HTTP/SDK-based, ОС-независимо; не измерено в рамках ADR | то же | то же | то же |
| 23 | Linux production | архитектурная оценка: HTTP/SDK-based, ОС-независимо; не измерено в рамках ADR | то же | то же | то же |
| 24 | Observability | usage/latency/finish-reason доступны через API-ответ | usage через pricing-подтверждённые механизмы; полный набор полей Responses usage не подтверждён официально в рамках этого исследования | usage + живые rate-limit заголовки дают дополнительную наблюдаемость | usage объект с детализацией (input/output/cached/thought/tool) — наиболее детализированный из четырёх по числу официально подтверждённых полей |
| 25 | Auditability | request id/usage доступны в ответе; provider request ID для всех четырёх отдельно не подтверждён этим исследованием — открытый вопрос | то же | то же | то же |
| 26 | Reproducibility | model pinning через `<model>-<date>` официально документирован | model pinning через конкретный snapshot ID | model pinning через конкретный model ID/версию | model pinning через дата-стемпированные идентификаторы; official-предупреждение не использовать alias «Latest» для воспроизводимости |
| 27 | Latency | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR | архитектурная оценка: не измерено в рамках ADR |
| 28 | Context limits | не зафиксированы как постоянное число в рамках этого ADR — зависят от конкретной модели, проверяются на этапе выбора модели (раздел 63) | то же | то же | то же |
| 29 | Output limits | то же | то же | то же | то же |
| 30 | Cost | снимок 2026-08-05, per-1M-token; grok-4.5: $2/$0.30(cached)/$6; grok-4.3: $1.25/$0.20/$2.50 | снимок 2026-08-05; cached input ~90% скидка (пример), batch ~50% | снимок 2026-08-05; Opus 5 $5/$25, Sonnet 5 $2/$10 (интро-цена до 2026-08-31), Haiku 4.5 $1/$5; batch 50% | снимок 2026-08-05; напр. Flash-класс $1.50/$7.50 и $0.10/$0.40 в зависимости от модели; batch ~50% |
| 31 | Operational complexity | архитектурная оценка: сопоставимая интеграционная сложность через единый gateway; не измерено в рамках ADR | то же | то же | то же |
| 32 | Reversibility | высокая на этапе до появления накопленных provenance-данных о конкретном provider; после — требует нового ADR/изменения (раздел 60) | то же | то же | то же |
| 33 | Future growth | путь роста существует через дополнительные provider adapters за той же границей `llm_gateway`, без структурных изменений | то же | то же | то же |

## 18. Выбранная стратегия

Исследование (раздел 66) не выявило блокирующего факта против xAI как начального provider MVP — у всех четырёх провайдеров обнаружены только рабочие, неблокирующие ограничения (раздел 19). Поэтому фиксируется:

- **xAI — основной начальный provider MVP.**
- интеграция выполняется только через `llm_gateway` (раздел 20);
- используется официальный Python SDK или прямой документированный API внутри provider adapter (раздел 22);
- конкретная модель выбирается конфигурацией из allowlist (раздел 23);
- preview/beta модель не используется в production без отдельного явно принятого решения;
- provider-specific функции (например, web/X search) не входят во внутренний контракт автоматически;
- остальные три provider (OpenAI, Anthropic, Google Gemini) не реализуются заранее;
- возможность их подключения сохраняется архитектурной границей `llm_gateway`, а не четырьмя заранее написанными adapter'ами;
- автоматический fallback на другой provider отсутствует (раздел 40);
- смена provider требует отдельного ADR или изменения настоящего ADR по установленному процессу (раздел 60).

## 19. Начальный provider

**Выбор: xAI.**

**Основания:** официальный нативный Python SDK (`xai-sdk`) существует и дополнительно документирована OpenAI-совместимая интеграция как второй путь адаптации; structured output поддержан в строгом (`json_schema`) и нестрогом (`json_object`) режимах; tool calling документирован с parallel-вызовами по умолчанию; данные по умолчанию не используются для обучения моделей; retirement моделей сопровождается soft-redirect, а не жёстким обрывом (раздел 66).

**Неблокирующие ограничения, зафиксированные честно:**

- Batch API официально исключает новейшую на момент исследования модель (grok-4.5) — учитывается при выборе конкретной модели для batch-сценариев (раздел 23, 32);
- официальная retry-документация тоньше, чем у трёх других исследованных provider — отсутствует документированный заголовок `Retry-After` и нормативный backoff-алгоритм; платформа реализует собственную консервативную retry-политику независимо от provider (раздел 34), что уже требуется общей архитектурой независимо от выбора;
- программная видимость статуса rate limit ограничена (нет заголовков), требуется мониторинг через Console UI или собственный учёт (раздел 35, 48).

Ни одно из этих ограничений не является блокирующим для MVP-сценариев платформы (text analysis, structured output, tool calling внутри allowlist).

## 20. Граница llm_gateway

- `application`/`analysis` зависят от внутреннего интерфейса, а не SDK конкретного provider;
- provider adapter зависит от provider SDK/API;
- FastAPI route handler не вызывает provider напрямую (`ADR-0002`);
- frontend не вызывает provider (`ADR-0003`);
- `domain` не знает model IDs;
- `insights` не знает SDK-типы;
- worker (`ADR-0006`) использует тот же application use case и `llm_gateway`, что и синхронный путь;
- `llm_gateway` не владеет бизнес-решением;
- `llm_gateway` не сохраняет insight самостоятельно;
- `llm_gateway` не выбирает authorization;
- `llm_gateway` не превращается в универсальный orchestration framework;
- provider-specific response преобразуется во внутренний DTO adapter'ом;
- provider-specific errors преобразуются во внутреннюю error taxonomy (раздел 39) adapter'ом.

## 21. Внутренний provider-neutral контракт

Концептуальный контракт, без кода.

**Request:**

- operation/use-case identifier;
- prompt template version;
- system instructions reference;
- user content;
- validated context;
- source references;
- requested internal output schema;
- tool allowlist;
- model policy;
- timeout class;
- correlation ID;
- user/tenant scope, если применимо;
- data classification;
- idempotency/reference key, если применимо.

**Response:**

- normalized content;
- validated structured data;
- provider;
- model identifier;
- provider request ID, если доступен;
- usage;
- finish/stop reason;
- tool requests;
- safety/refusal information;
- latency;
- retry count;
- timestamps;
- warnings;
- provenance references;
- raw provider payload reference только при разрешённой политике, без обязательного бессрочного хранения полного payload.

## 22. Provider adapters

- provider adapter — единственное место, куда допускается импорт SDK конкретного provider;
- adapter реализует internal contract (раздел 21), а не наоборот;
- adapter переводит provider-specific ошибки (раздел 66: коды xAI/OpenAI/Anthropic/Gemini) во внутреннюю error taxonomy (раздел 39);
- adapter переводит provider-specific usage-поля (например, `output_tokens_details.reasoning_tokens` у xAI, `cache_read_input_tokens` у Anthropic, `total_thought_tokens` у Gemini) в единую внутреннюю usage-модель;
- для MVP реализуется только xAI adapter; остальные три provider не реализуются заранее (раздел 18);
- adapter не содержит бизнес-правил `analysis`/`insights`;
- adapter не решает authorization;
- OpenAI-совместимый режим xAI (если используется как путь интеграции) остаётся внутри adapter-слоя и не проникает как «универсальный» контракт наружу (запрет из раздела 11 — OpenAI-compatible API не становится единственным внутренним контрактом).

## 23. Model policy

- архитектура выбирает provider strategy, а не вечный model ID;
- production-модели находятся в allowlist;
- stable/GA модель предпочтительнее preview/experimental (для xAI — предпочтение датированного pinned-идентификатора над «-latest» alias; аналогичный принцип распространяется на любой будущий provider, например официально документированный «Latest» hot-swap alias Gemini, раздел 66);
- exact model snapshot/version используется, если provider это поддерживает и если это необходимо для воспроизводимости (раздел 47);
- aliases могут изменяться и требуют контроля — включая honest учёт того, что retirement у xAI сопровождается авто-редиректом, который может незаметно изменить биллинг (раздел 66, риск 18/38);
- смена модели проходит evaluation (раздел 52);
- модель не обновляется автоматически только потому, что вышла новая;
- downgrade/rollback возможен;
- capability проверяется, а не предполагается (например, исключение grok-4.5 из Batch API у xAI — раздел 66);
- context/output limits берутся из актуальной документации или API на момент выбора конкретной модели, а не фиксируются в этом ADR (раздел 17, критерии 28–29);
- модель для каждого use case выбирается по утверждённой policy;
- более дорогая модель не считается автоматически более качественной;
- reasoning mode и budget (например, документированный `reasoning_effort` у xAI) выбираются отдельно, не этим ADR.

## 24. Model lifecycle и deprecation

- lifecycle конкретного provider отслеживается по его официальной документации (раздел 17, критерий 11–12; раздел 66);
- для xAI: учитывается alias-паттерн (`<model>`, `<model>-latest`, `<model>-<date>`) и практика авто-редиректа при retirement;
- deprecation любого provider обрабатывается как планируемое событие, а не аварийное — минимальный срок уведомления и точная модель замены фиксируются на момент конкретного deprecation, а не в этом ADR;
- production не переключается на новую модель автоматически;
- rollback на предыдущую pinned-модель остаётся возможным до подтверждения evaluation новой;
- смена provider (в отличие от смены модели внутри provider) требует отдельного ADR или изменения настоящего ADR (раздел 60).

## 25. Prompt management

- prompts являются управляемыми артефактами;
- prompt имеет идентификатор и версию;
- system instructions отделены от пользовательского ввода;
- retrieved context отделён от instructions (согласуется с `ADR-0005`: retrieved context не является фактом и не становится instructions);
- динамическая конкатенация не должна размывать границы instructions/context/user input;
- изменение prompt проходит review;
- секреты не помещаются в prompt (раздел 45);
- персональные и чувствительные данные минимизируются;
- prompt не хранится только в истории чата — версия prompt является управляемым артефактом отдельно;
- provider-specific prompt syntax (если используется) изолируется adapter-слоем (раздел 22);
- production prompt не создаётся в рамках настоящего ADR.

## 26. Prompt versioning

- prompt version сохраняется вместе с insight как часть provenance (раздел 46);
- изменение версии prompt для production use case проходит regression evaluation (раздел 52) до включения;
- откат к предыдущей версии prompt технически возможен;
- версия prompt однозначно связывается с конкретным вызовом через internal contract (раздел 21).

## 27. Input context

- validated context (раздел 21) передаётся отдельно от system instructions и от retrieved documents;
- source references сохраняются вместе с запросом для последующей проверки provenance (раздел 46);
- input context не включает секреты (раздел 45) и не включает необязательные персональные данные (раздел 41–42);
- размер входного контекста учитывает документированные context limits конкретной выбранной модели (раздел 23) — не фиксируется числом в этом ADR;
- instructions, обнаруженные внутри retrieved документов, не становятся системными инструкциями (раздел 44).

## 28. Structured output

- provider structured-output feature (json_schema у xAI; Structured Outputs у OpenAI; `output_config.format`/`strict` tool у Anthropic; JSON-режим у Gemini — раздел 66) не заменяет локальную validation;
- внутренняя schema является source of truth для `application`;
- provider-specific schema преобразуется adapter'ом (раздел 22) в формат, поддерживаемый конкретным provider (учитывая документированные ограничения — например, отсутствие поддержки `allOf`/`not` у xAI и OpenAI, отсутствие рекурсивных схем и length-constraints у Anthropic);
- ответ валидируется локально независимо от provider-side гарантии;
- invalid response не сохраняется как успешный insight;
- repair/retry ограничен и наблюдаем (раздел 34, 48);
- модель не может добавлять произвольные поля без политики (`additionalProperties: false`, где поддерживается provider'ом);
- partial response отражается явно, не выдаётся за полный;
- schema version сохраняется как часть provenance (раздел 46);
- свободный текст может храниться отдельно от проверенных структурированных данных;
- отсутствие provider-native strict mode (если модель/provider его не поддерживает) не должно проникать в domain как исключение из правила локальной валидации.

## 29. Schema validation

- каждый structured response проходит валидацию против внутренней схемы до использования `application`/`analysis`;
- ошибка валидации классифицируется как `invalid structured output` (раздел 39), не как успех;
- ограниченный repair/retry допустим только по установленной политике (раздел 34), не бесконечно;
- schema, принципиально несовместимая с возможностями provider (например, `allOf`/`not`, рекурсивные схемы — раздел 66), не переносится на provider-side валидацию без учёта этого ограничения в adapter'е;
- версия внутренней схемы фиксируется независимо от provider capability.

## 30. Tool calling

- модель только предлагает tool call (подтверждено официально для всех четырёх исследованных provider — раздел 66: xAI, OpenAI, Anthropic, Gemini единообразно документируют, что исполнение остаётся на стороне вызывающего приложения);
- `application` проверяет разрешение перед исполнением;
- tool name выбирается из allowlist;
- аргументы валидируются;
- authorization проверяется независимо от факта наличия tool call;
- tool side effect не выполняется автоматически;
- торговые операции запрещены (раздел 31 — LLM не исполняет сделки);
- секреты не передаются модели (раздел 45);
- recursive/unbounded tool loops запрещены;
- максимум шагов определяется конфигурацией, не этим ADR;
- tool result считается недоверенным внешним input;
- каждый вызов коррелируется и наблюдается (раздел 48);
- provider-specific tool formats нормализуются adapter'ом (раздел 22);
- web/X search (xAI) и server-side tools (web_search/web_fetch/code_execution у Anthropic) не являются источником истины без provenance и проверки — используются, только если явно разрешены политикой use case, и не считаются обязательной частью архитектуры (раздел 11).

## 31. Streaming

- streaming — транспортная оптимизация, а не изменение бизнес-контракта;
- частичный stream не считается завершённым insight;
- финальная валидация structured output выполняется после завершения потока, а не по частичным данным;
- usage/finish-reason считаются доступными по завершении потока (согласуется с наблюдением по OpenAI, раздел 66: usage-подобные сигналы документированы как доступные после полного вывода);
- streaming timeout учитывает официальные рекомендации provider (например, xAI официально рекомендует увеличивать client timeout при streaming в сочетании с reasoning-моделями — раздел 66);
- streaming не используется как замена durable job для долгих операций (раздел 32).

## 32. Synchronous и background execution

**Синхронный вызов.** Допустим, если пользователь ожидает результат и вызов укладывается в user-facing timeout policy (раздел 33).

**Streaming.** Транспортная оптимизация (раздел 31), не отдельный бизнес-режим.

**Durable background job.** Используется для долгих, batch, повторных evaluation или иных долговечных LLM-операций согласно `ADR-0006`. Внешний LLM-вызов не выполняется внутри открытой PostgreSQL-транзакции (`ADR-0006`, раздел 38). Batch API конкретного provider (если используется) рассматривается как оптимизация durable background job, а не как отдельный режим исполнения вне модели `ADR-0006` — при этом учитываются provider-specific ограничения batch (например, официальное исключение отдельных моделей из batch у xAI — раздел 66).

## 33. Timeouts

Категории (числовые значения не задаются этим ADR):

- user-facing wait timeout — для синхронных вызовов (раздел 32);
- streaming connection timeout — с учётом provider-specific рекомендаций (например, xAI, раздел 66);
- background job execution timeout — согласуется с `ADR-0006`, раздел 30;
- provider request timeout на уровне adapter/SDK;
- batch job polling/completion timeout — с учётом best-effort характера сроков batch (все четыре provider документируют цель ~24 часа как best-effort, не гарантию — раздел 66).

Истечение timeout не означает, что provider не завершил вызов фактически — трактуется согласно `ADR-0006`, раздел 30 (локальный timeout не отменяет уже произошедший внешний side effect).

## 34. Retry

Internal error taxonomy (раздел 39) определяет, что подлежит retry.

Retry допустим только для временных ошибок: rate limited, timeout, network error, provider unavailable, некоторые 5xx.

Retry не выполняется автоматически для: configuration error, authentication error, authorization/policy error, invalid request, unsupported capability, content/safety refusal без изменённого запроса, invalid structured output без стратегии исправления, превышение контекста без стратегии сокращения.

`Retry-After` учитывается, если предоставлен provider'ом (документировано OpenAI, Anthropic, Gemini — раздел 66). Для xAI, где официальная retry-документация не подтверждает `Retry-After` явно (раздел 66), платформа применяет собственную консервативную политику backoff+jitter независимо от provider-специфичной документации — это общее архитектурное решение, а не provider-specific обход.

Каждая попытка наблюдаема (раздел 48). Числовые значения количества попыток/задержек не задаются этим ADR.

## 35. Rate limits

- rate limit — ожидаемое, а не аварийное состояние;
- у каждого исследованного provider — собственная модель измерения (xAI: RPS+TPM по тиру spend; OpenAI: RPM/RPD/TPM/TPD/IPM по тиру; Anthropic: RPM/ITPM/OTPM token-bucket по тиру + живые заголовки; Gemini: RPM/TPM/RPD по тиру + отдельный spend-based лимит — раздел 66, 17);
- adapter нормализует rate-limit сигнал (где он документирован) во внутреннее наблюдаемое событие (раздел 48);
- для provider без документированных rate-limit-статус-заголовков (xAI, раздел 66) платформа не предполагает наличие такого сигнала и полагается на обработку 429 и собственный учёт;
- конкретные числовые лимиты не фиксируются этим ADR — они определяются тиром аккаунта и провайдером, изменяются во времени.

## 36. Concurrency

- несколько одновременных вызовов к provider допустимы в рамках rate limit;
- worker-процессы (`ADR-0006`) могут инициировать конкурентные LLM-вызовы для разных jobs;
- concurrency не должна систематически исчерпывать rate limit без наблюдаемости (раздел 35, 48);
- конкретный уровень параллелизма определяется конфигурацией, не этим ADR.

## 37. Idempotency

- LLM-вызов сам по себе не идемпотентен (повторный вызов может дать другой ответ) — это отличается от идемпотентности durable job, установленной `ADR-0006`;
- идемпотентность на уровне job (создание/повторное исполнение конкретной LLM-задачи) обеспечивается механизмом `ADR-0006`, раздел 26 — idempotency key на уровне бизнес-операции;
- повторный вызов после сбоя не обязан давать идентичный текстовый результат (раздел 47 — воспроизводимость касается контекста и конфигурации, не побитового текста);
- side effect, инициированный через tool call (раздел 30), подчиняется тем же правилам идемпотентности, что и остальные внешние side effects (`ADR-0006`, раздел 26).

## 38. Cancellation

- пользовательская отмена долгой/durable LLM-задачи следует кооперативной модели `ADR-0006`, раздел 33;
- streaming-вызов может быть прерван клиентом на транспортном уровне; прерванный stream не считается завершённым insight (раздел 31);
- отмена не гарантирует, что provider не завершил генерацию на своей стороне — provider billing может уже учитывать частично сгенерированный ответ;
- отменённый LLM-вызов не создаёт insight, помеченный как успешный.

## 39. Error taxonomy

Внутренняя taxonomy (минимум):

- configuration error;
- authentication error;
- authorization/policy error;
- invalid request;
- unsupported capability;
- rate limited;
- timeout;
- network error;
- provider unavailable;
- model unavailable;
- context/input too large;
- output limit reached;
- content/safety refusal;
- invalid structured output;
- tool-call validation failure;
- cancelled;
- unknown provider error.

Adapter (раздел 22) обязан отображать provider-specific коды в эту таксономию — например: xAI 400/401/403/404/405/415/422/429/202 (раздел 66); OpenAI 401/403(geo)/429/500/503 плюс SDK-исключения (раздел 66); Anthropic 400/401/403/404/409/422/429/5xx через SDK exception-классы (раздел 66); Gemini явное разделение retryable (429/503/5xx/408) и non-retryable (400/403) (раздел 66). Отображение конкретных кодов на внутренние категории — предмет реализации adapter'а, не фиксируется числами в этом ADR.

## 40. Fallback policy

- автоматический cross-provider fallback по умолчанию **запрещён**;
- другой provider может иметь иные безопасность, данные, стоимость, качество и семантику (раздел 17, критерий 17 — например, документированное различие в data/privacy policy между xAI/OpenAI/Anthropic/Gemini);
- fallback не должен менять результат незаметно;
- fallback требует: утверждённого use case; совместимого внутреннего контракта; evaluation (раздел 52); data/privacy review (раздел 42); cost policy (раздел 50); provenance (раздел 46); user-visible или audit-visible marker, где требуется; отдельного решения;
- retry той же модели не является provider fallback (раздел 15, 34);
- смена на другую модель того же provider также подчиняется model policy (раздел 23), не fallback policy;
- при отсутствии разрешённого fallback возвращается честная ошибка или partial result, а не выдуманный результат другого provider.

## 41. Data handling

- минимизация передаваемых данных — только необходимый context передаётся provider'у;
- классификация данных выполняется до вызова (раздел 21 — data classification в internal contract);
- user isolation — данные одного пользователя не смешиваются с контекстом другого при формировании запроса;
- retention учитывает документированную политику каждого provider (раздел 17, критерий 17; раздел 66): xAI — 30 дней шифрованного хранения для abuse detection, автоудаление; OpenAI — до 30 дней abuse-monitoring; Anthropic — по умолчанию без специального упоминания retention вне feedback-механизма (до 5 лет только для feedback-помеченных данных); Gemini — тарифицируется по тиру (раздел 42);
- raw prompts/responses не логируются бесконтрольно (раздел 48).

## 42. Privacy

- provider training-policy проверяется до production use для каждого выбранного provider (раздел 66): xAI и OpenAI и Anthropic официально не используют commercial/API-данные для обучения по умолчанию (без явного opt-in); Gemini документирует явное различие по тиру — free tier используется для улучшения продукта, paid tier — нет;
- платформа использует только paid/commercial-tier доступ там, где это влияет на data-usage policy (в частности, критично для Gemini, если он будет когда-либо подключён — раздел 63);
- региональные требования проверяются отдельно при необходимости — не подтверждены исчерпывающе этим исследованием для всех четырёх provider (раздел 17, критерий 18 — открытый вопрос, раздел 63);
- zero data retention (ZDR), где доступен (xAI, OpenAI), рассматривается только при обоснованной необходимости — xAI официально не рекомендует ZDR большинству клиентов, так как он отключает часть функций (раздел 66);
- provider logging/training policy переоценивается при смене provider или тира (раздел 24, 60).

## 43. Security

- worker и web-процесс обращаются к provider через adapter с минимально необходимыми правами (учётные данные API);
- provider API keys не встраиваются в код, prompt или логи (раздел 45);
- ответ provider проходит ту же валидацию/санитизацию перед использованием в UI, что и любой недоверенный внешний ввод;
- tool execution подчиняется правилам раздела 30 — авторизация проверяется независимо от предложения модели;
- server-side tools provider'а (например, Anthropic web_search/web_fetch/code_execution, исполняемые на инфраструктуре provider — раздел 66) рассматриваются как дополнительная поверхность атаки и не включаются без явной политики (раздел 11, 30);
- утечка ключа обрабатывается по общему плану ротации (раздел 45).

## 44. Prompt injection

- retrieved документы и любой внешний контент считаются недоверенными (согласуется с `ADR-0005`);
- instructions, обнаруженные внутри retrieved документов или tool results, не становятся system instructions (раздел 25, 27);
- tool result считается недоверенным внешним input (раздел 30);
- provider-specific web/X search результаты (xAI) и server-side web tools (Anthropic) — при использовании — также считаются недоверенным внешним содержимым, а не фактом (раздел 30, 42);
- модель не определяет authorization на основании содержимого документа или tool result;
- prompt injection рассматривается как ожидаемый класс атаки, а не исключительный случай, и учитывается в quality evaluation (раздел 52).

## 45. Secrets

- API keys и credentials provider'а не передаются модели как часть содержимого запроса;
- секреты не помещаются в prompt (раздел 25);
- секреты не логируются (раздел 48);
- ключи хранятся во внешней конфигурации, не в коде и не в PostgreSQL как обычные бизнес-данные (`ADR-0004`);
- ключи разделяются по окружениям;
- ключи имеют минимально необходимые права;
- утечка ключа имеет план ротации (раздел 43).

## 46. Provenance

Сохраняются или связываются с insight:

- provider;
- model ID;
- model version/snapshot, если доступно;
- operation ID;
- prompt template version;
- input/context references;
- source versions;
- schema version;
- tool definitions version;
- параметры вызова;
- timestamps;
- provider request ID, если доступен (раздел 17, критерий 25 — подтверждённая доступность не для всех четырёх provider в рамках этого исследования; фиксируется, если предоставлен);
- usage;
- finish reason;
- retries;
- gateway/adapter version;
- configuration version;
- warnings/refusal;
- retrieval context references.

## 47. Reproducibility

- побитовая идентичность повторного ответа **не обещается** ни для одного provider;
- воспроизводимость означает воспроизводимость контекста и конфигурации (prompt version, model ID/snapshot, параметры, source references — раздел 46), а не гарантированно тот же текст ответа;
- pinning на датированный/конкретный model ID (документировано для всех четырёх provider — раздел 17, критерий 26) используется там, где воспроизводимость критична;
- alias, который может «hot-swap» модель без явного версионирования (например, официально документированный Gemini «Latest» alias — раздел 66), не используется в production именно из соображений воспроизводимости (раздел 23).

## 48. Observability

Минимум наблюдаемых полей на вызов:

- request count;
- success/failure;
- provider/model;
- latency;
- time to first token, если streaming;
- input/output/cached/reasoning usage, если provider сообщает (раздел 17, критерий 7);
- estimated или reported cost;
- rate-limit события (раздел 35);
- timeout;
- retry;
- refusal;
- invalid schema;
- cancellation;
- queue wait для background jobs (`ADR-0006`, раздел 43);
- correlation ID.

Полный чувствительный prompt не записывается в метрики или обычные логи (раздел 41, 45).

## 49. Audit

- критичная пользовательская операция, инициировавшая LLM-вызов с бизнес-значимым эффектом, аудируется (согласуется с `ADR-0006`, раздел 44);
- provider/model/prompt version связываются с audit-записью через provenance (раздел 46);
- разрешённый fallback (раздел 40), если когда-либо активирован, аудируется отдельно как significant event;
- аудит не заменяется обычными observability-логами (раздел 48), аналогично принципу `ADR-0006`, раздел 44.

## 50. Cost control

Категории (без выдуманных сумм, снимок на 2026-08-05, раздел 66):

- input/output/cached tokens по каждому вызову;
- reasoning/thinking tokens, если модель их использует и provider их выставляет отдельно (документировано для xAI и Gemini — раздел 66);
- batch-скидка, если используется (документирована у всех четырёх provider как ~50%, раздел 66);
- prompt caching, если используется (Anthropic — явные коэффициенты 1.25x/2x/0.1x; Gemini — отдельная тарификация хранения контекстного кэша; раздел 66);
- server-side tool charges (например, web_search у Anthropic/xAI), если используются;
- retry — потенциально повторная стоимость вызова;
- региональная надбавка, если применимо (документирована у OpenAI как ~10% за data-residency обработку — раздел 66);
- fallback (если когда-либо разрешён) — отдельная стоимость другого provider.

## 51. Usage accounting

- usage учитывается по фактическому ответу provider, когда эти данные доступны в ответе (раздел 17, критерий 7);
- при недоступности части полей (например, неподтверждённые reasoning/cached поля в OpenAI Responses API usage — раздел 66) фиксируется факт отсутствия данных, а не предполагаемое значение;
- usage агрегируется по: provider; model; use case; user/request; background job; retries; cached tokens; tool/search charges; batch requests;
- usage связывается с provenance (раздел 46) для последующего cost-анализа.

## 52. Quality evaluation

- provider/model выбираются не по субъективному впечатлению;
- нужен evaluation dataset (создаётся отдельно, не в рамках этого ADR);
- проверяется русский язык — официальными источниками эта характеристика не была отдельно подтверждена ни для одного из четырёх provider в рамках проведённого исследования (раздел 17, критерий 3) — проверка выполняется на этапе evaluation, а не декларируется этим ADR;
- проверяется factual grounding, schema adherence, refusal correctness, prompt injection resistance, latency, cost, stability, tool-call correctness, incomplete/partial behavior;
- регрессия между моделями/provider сравнивается на одинаковых сценариях;
- production change (модель, provider, существенный prompt) не проводится без regression evaluation;
- LLM output оценивается отдельно от retrieval quality (`ADR-0005`);
- user feedback не является единственной метрикой качества.

Числовые пороги качества не задаются этим ADR.

## 53. Human-in-the-loop

- trading insight не является торговой командой;
- пользователь принимает решение самостоятельно;
- сомнительный результат отражается явно, не маскируется;
- отсутствие данных не выдаётся за полный ответ;
- критичные действия требуют явного подтверждения пользователя;
- LLM не исполняет сделки (раздел 30);
- модель не изменяет собственные prompts или веса;
- автоматическое самообучение платформы на основании LLM-ответов не утверждается этим ADR;
- feedback хранится как пользовательская оценка, а не как автоматическая истина.

## 54. Положительные последствия

- единая архитектурная граница `llm_gateway` изолирует platform от provider-specific деталей, подтверждённых исследованием как существенно различающихся (usage-поля, rate-limit модели, lifecycle-политики — раздел 17, 66);
- xAI как единственный реализуемый adapter в MVP снижает интеграционную сложность без потери возможности добавить другие provider позже;
- structured output и tool calling официально документированы у всех четырёх provider — выбор не ограничивает будущую гибкость;
- честная фиксация неблокирующих ограничений xAI (batch-исключение модели, тонкая retry-документация) снижает риск скрытых сюрпризов при реализации;
- provenance и usage accounting заложены архитектурно с самого начала, а не добавляются постфактум.

## 55. Отрицательные последствия

- официальная retry/rate-limit-visibility документация xAI слабее, чем у трёх альтернатив — платформа берёт на себя больше собственной инженерной работы по устойчивости, чем могла бы при выборе provider с более полной документацией;
- реализация только одного adapter в MVP означает, что смена provider в будущем потребует полноценной новой adapter-реализации, а не простого переключения конфигурации;
- ни один provider не подтверждён отдельным исследованием по качеству русского языка — остаётся риском до проведения evaluation (раздел 52);
- региональные/availability ограничения не исследованы исчерпывающе ни для одного provider — остаётся открытым вопросом (раздел 63).

## 56. Риски

1. Provider outage.
2. Model unavailable.
3. Rate limit.
4. Cost growth.
5. Token usage spike.
6. Prompt injection.
7. Data leakage.
8. Secret leakage.
9. Cross-user context.
10. Hallucinated facts.
11. Unsupported structured output.
12. Invalid schema.
13. Tool-call abuse.
14. Authorization bypass.
15. Recursive tool loop.
16. Provider-specific SDK leakage (за пределы adapter-слоя).
17. Vendor lock-in.
18. Model alias changed.
19. Preview model removed.
20. Model behavior regression.
21. Silent fallback.
22. Incompatible fallback.
23. Retry storm.
24. Duplicate background execution.
25. Timeout after provider completed.
26. Response lost before local commit.
27. Context too large.
28. Output truncated.
29. Refusal misclassified.
30. Raw prompts logged.
31. Inaccurate cost calculation.
32. Usage metadata absent.
33. Provider terms changed.
34. Data-retention policy changed.
35. Evaluation dataset missing.
36. Russian quality insufficient.
37. Prompt version not saved.
38. Provenance missing.
39. SDK breaking change.
40. Provider search result treated as fact.

## 57. Меры снижения рисков

1. Provider outage → внутренняя error taxonomy (`provider unavailable`, раздел 39), durable job переживает недоступность provider через retry/backoff (`ADR-0006`).
2. Model unavailable → model policy с allowlist и rollback на предыдущий pinned ID (раздел 23–24).
3. Rate limit → внутренняя классификация `rate limited`, backoff, наблюдаемость (раздел 35, 48); честный учёт отсутствия rate-limit заголовков у xAI.
4. Cost growth → usage accounting и cost control по use case/провайдеру (раздел 50–51).
5. Token usage spike → наблюдаемость usage и алертинг вне рамок этого ADR, но заложена структура данных для него (раздел 48).
6. Prompt injection → retrieved content и tool results считаются недоверенными, instructions не переопределяются документами (раздел 44).
7. Data leakage → минимизация данных, классификация до вызова, provider data-usage policy проверяется до production (раздел 41–42).
8. Secret leakage → секреты не передаются модели и не логируются (раздел 45, 48).
9. Cross-user context → user isolation на уровне internal contract (раздел 21, 41).
10. Hallucinated facts → LLM не считается источником фактов (`ENGINEERING_PRINCIPLES.md`), локальная validation обязательна (раздел 28–29).
11. Unsupported structured output → adapter учитывает документированные ограничения provider (например, отсутствие `allOf`/`not` у xAI/OpenAI — раздел 28, 66).
12. Invalid schema → локальная валидация обязательна независимо от provider-side гарантии (раздел 29).
13. Tool-call abuse → allowlist, authorization проверяется независимо (раздел 30).
14. Authorization bypass → authorization не делегируется модели никогда (раздел 30, 53).
15. Recursive tool loop → максимум шагов по конфигурации (раздел 30).
16. Provider-specific SDK leakage → SDK импортируется только внутри adapter (раздел 20, 22).
17. Vendor lock-in → provider-neutral internal contract и `llm_gateway` граница (раздел 20–21).
18. Model alias changed → pinning на датированный/snapshot ID, избегание нестабильных alias (раздел 23, 47).
19. Preview model removed → preview/experimental не используется в production без отдельного решения (раздел 18, 23–24).
20. Model behavior regression → regression evaluation перед сменой модели (раздел 52).
21. Silent fallback → автоматический fallback запрещён архитектурно (раздел 40).
22. Incompatible fallback → fallback требует evaluation и совместимого контракта перед активацией (раздел 40).
23. Retry storm → backoff+jitter, ограниченное число попыток (раздел 34).
24. Duplicate background execution → идемпотентность job согласно `ADR-0006`, раздел 26 (раздел 37).
25. Timeout after provider completed → локальный timeout не отменяет уже произошедший вызов; обрабатывается как признанный класс отказа (`ADR-0006`, раздел 26, 38; раздел 33).
26. Response lost before local commit → reconciliation-подход `ADR-0006`, раздел 38, применим и к LLM-вызовам как внешним side effects.
27. Context too large → внутренняя категория ошибки `context/input too large`, контроль размера context на входе (раздел 27, 39).
28. Output truncated → `output limit reached` как отдельная категория, partial response отражается явно (раздел 28, 39).
29. Refusal misclassified → refusal — отдельное, явно наблюдаемое поле ответа, не смешивается с успехом (раздел 21, 48).
30. Raw prompts logged → запрет бесконтрольного логирования полного prompt (раздел 41, 48).
31. Inaccurate cost calculation → usage берётся из фактического ответа provider, где доступно; отсутствие данных фиксируется явно, а не предполагается (раздел 51).
32. Usage metadata absent → adapter документирует и наблюдает случаи отсутствия usage-полей (например, неподтверждённые поля Responses API — раздел 51, 66).
33. Provider terms changed → privacy/data policy переоценивается при значимых изменениях (раздел 24, 42, 60).
34. Data-retention policy changed → входит в условия пересмотра ADR (раздел 63).
35. Evaluation dataset missing → production change не допускается без regression evaluation (раздел 52).
36. Russian quality insufficient → явно отражено как непроверенный факт, проверяется evaluation до production-использования конкретной модели (раздел 52).
37. Prompt version not saved → prompt version — обязательное поле provenance (раздел 26, 46).
38. Provenance missing → полный список обязательных provenance-полей зафиксирован (раздел 46).
39. SDK breaking change → SDK версия фиксируется отдельным implementation-решением, изоляция в adapter снижает blast radius (раздел 22, план внедрения раздел 59, шаг 19).
40. Provider search result treated as fact → provider-specific search результаты считаются недоверенным внешним содержимым, не фактом (раздел 30, 44).

## 58. NFR impact

Числовые NFR, связанные с LLM (latency, context/output limits, конкретные стоимостные пороги), не утверждены `NON_FUNCTIONAL_REQUIREMENTS.md` и не устанавливаются этим ADR — определяются при выборе конкретной модели и последующих измерениях (раздел 17, критерии 27–29; раздел 52). Provenance, наблюдаемость, безопасность и человеческий контроль (разделы 46, 48, 43, 53) закладываются архитектурно с самого начала.

## 59. План внедрения

Без кода на этом этапе:

1. принять ADR-0007;
2. определить внутренние request/response DTO (раздел 21);
3. определить error taxonomy (раздел 39);
4. определить provider adapter interface (раздел 22);
5. определить model policy (раздел 23);
6. определить config/allowlist;
7. определить secret management (раздел 45);
8. определить prompt registry/versioning (раздел 25–26);
9. определить structured schemas (раздел 28–29);
10. определить tool allowlist (раздел 30);
11. определить timeout classes (раздел 33);
12. определить retry classes (раздел 34);
13. определить usage/cost accounting (раздел 50–51);
14. определить logging/redaction (раздел 41, 48);
15. определить evaluation dataset (раздел 52);
16. проверить официальные provider policies xAI непосредственно перед реализацией (данные раздела 66 могли устареть);
17. подтвердить начальный provider (xAI) по актуальным на момент реализации данным;
18. выбрать конкретную stable/pinned model отдельной implementation-задачей;
19. добавить xAI SDK/dependency отдельным изменением;
20. реализовать xAI provider adapter;
21. реализовать один vertical slice (один use case целиком через `llm_gateway`);
22. проверить invalid schema;
23. проверить timeout/rate limit;
24. проверить refusal;
25. проверить prompt injection;
26. проверить background execution через `ADR-0006`;
27. проверить provenance;
28. проверить cost accounting;
29. провести regression evaluation, включая проверку русского языка;
30. только затем разрешить production use.

## 60. План отката

**Если provider (xAI) не используется:**

- остановить новые вызовы;
- отключить provider через конфигурацию;
- сохранить исходные данные и историю insights;
- незавершённые durable jobs перевести в безопасный статус согласно `ADR-0006`;
- не подменять результат другим provider автоматически (раздел 40);
- вернуть пользователю честную ошибку;
- сохранить provenance существующих insights (раздел 46).

**При смене provider:**

- оформить новый ADR или замену ADR-0007;
- реализовать новый adapter (раздел 22);
- провести evaluation (раздел 52);
- проверить privacy/security (раздел 41–43);
- проверить structured schemas (раздел 28–29);
- проверить prompts (раздел 25–27);
- проверить cost (раздел 50–51);
- выполнить контролируемое переключение;
- сохранить provider/model provenance для уже созданных insights (раздел 46);
- оставить rollback window;
- удалить старый adapter только после проверки.

## 61. Критерии проверки

После будущей реализации:

- `application`/`domain` не импортируют provider SDK;
- frontend не вызывает provider;
- все вызовы проходят через `llm_gateway`;
- provider/model записываются;
- prompt version записывается;
- source references сохраняются;
- structured output валидируется локально;
- invalid schema не считается успехом;
- tool calls проходят allowlist и authorization;
- секреты не попадают в prompt/logs;
- timeout и retry разделены;
- permanent errors не retry автоматически;
- rate limit наблюдаем;
- usage и стоимость наблюдаемы;
- background job переживает рестарт (`ADR-0006`);
- внешний вызов не выполняется внутри DB-транзакции;
- отказ provider не создаёт выдуманный insight;
- silent cross-provider fallback отсутствует;
- модель выбирается из allowlist;
- preview/experimental модель не включается автоматически;
- regression evaluation существует;
- русский язык проверен;
- prompt injection протестирован;
- LLM не исполняет сделки;
- отключение provider возможно конфигурацией.

## 62. Условия пересмотра

ADR-0007 пересматривается, если:

- начальный provider (xAI) теряет поддержку;
- provider API существенно меняется;
- pricing становится неприемлемым;
- rate limits не достигают NFR;
- качество русского языка недостаточно (по результатам evaluation, раздел 52);
- structured output недостаточен для продуктовых сценариев;
- privacy/compliance требования меняются;
- provider terms/data policy меняются (раздел 66 фиксирует снимок на 2026-08-05, не постоянное состояние);
- требуется другой регион;
- local/self-hosted model становится обоснованной;
- требуется multi-provider strategy;
- fallback становится продуктовым требованием;
- модель перестаёт быть доступной;
- provider-specific capability становится критичной;
- cost/quality другого provider доказанно лучше по результатам evaluation;
- gateway abstraction создаёт неприемлемые ограничения;
- LLM перестаёт быть частью MVP.

## 63. Открытые вопросы

- качество работы с русским языком не подтверждено официальной документацией ни для одного из четырёх provider — требует evaluation (раздел 52) до production-использования;
- региональные/availability ограничения не исследованы исчерпывающе для всех четырёх provider — требуют проверки при выборе региона развёртывания;
- provider request ID доступность не подтверждена равномерно для всех четырёх provider в рамках этого исследования;
- точные context/output limits конкретной выбранной модели не зафиксированы этим ADR — определяются при выборе модели (раздел 23);
- точные имена части usage-полей OpenAI Responses API (в частности reasoning/cached tokens) не подтверждены официальной документацией в рамках этого исследования и требуют отдельной проверки, если OpenAI когда-либо станет рассматриваемым provider;
- provider-specific search tools (web/X у xAI, server-side tools у Anthropic) не исследованы как отдельный продуктовый сценарий — остаются вне обязательного контракта (раздел 11, 30);
- local/self-hosted model как future-сценарий не проработана этим ADR (раздел 16).

## 64. Решение Product Owner

На ревью.

## 65. История изменений статуса

| Дата | Статус | Кем изменён | Примечание |
|---|---|---|---|
| 2026-08-05 | На ревью | Claude (оформление по предложению Solution Architect) | создано предложение использовать xAI как начального LLM-провайдера MVP через provider-neutral llm_gateway без автоматического cross-provider fallback |

## 66. Источники исследования

Исследование выполнено 2026-08-05 исключительно по официальным первичным источникам, без использования блогов, Reddit, Medium, рейтингов, сторонних сравнительных таблиц, маркетинговых benchmark, неофициальных wrappers.

**xAI** (docs.x.ai):
- [docs.x.ai/overview](https://docs.x.ai/overview) — Responses API как основной интерфейс; base URL `https://api.x.ai/v1`; отдельные Code/Voice/Imagine API.
- [docs.x.ai/developers/quickstart](https://docs.x.ai/developers/quickstart) — официальный SDK `xai-sdk`; OpenAI-совместимый режим документирован как альтернативный путь.
- [docs.x.ai/developers/model-capabilities/text/structured-outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs) — `response_format.type` json_schema (strict)/json_object; ограничения подмножества JSON Schema.
- [docs.x.ai/developers/guides/function-calling](https://docs.x.ai/developers/guides/function-calling) — требования к схеме tool params; parallel tool calls по умолчанию.
- [docs.x.ai/docs/guides/streaming-response](https://docs.x.ai/docs/guides/streaming-response) — SSE, `data: [DONE]`, рекомендация увеличивать timeout при streaming+reasoning.
- [docs.x.ai/developers/model-capabilities/text/multi-agent](https://docs.x.ai/developers/model-capabilities/text/multi-agent) и [docs.x.ai/developers/pricing](https://docs.x.ai/developers/pricing) — usage-поля, биллинг leader+sub-agent.
- [docs.x.ai/developers/rate-limits](https://docs.x.ai/developers/rate-limits) — RPS/TPM, тиры Tier 0–4+Enterprise по кумулятивному spend.
- [docs.x.ai/developers/pricing](https://docs.x.ai/developers/pricing) — снимок цен grok-4.5/grok-4.3.
- [docs.x.ai/developers/advanced-api-usage/batch-api](https://docs.x.ai/developers/advanced-api-usage/batch-api) — Batch API, исключение grok-4.5, лимиты файлов.
- [docs.x.ai/developers/migration/may-15-retirement](https://docs.x.ai/developers/migration/may-15-retirement) — практика retirement с авто-редиректом.
- [docs.x.ai/developers/model-capabilities/text/reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning) — `reasoning_effort`.
- [docs.x.ai/developers/faq/security](https://docs.x.ai/developers/faq/security) — data/privacy policy, 30-дневное хранение, ZDR.
- [docs.x.ai/developers/debugging](https://docs.x.ai/developers/debugging) — HTTP error codes, тонкая retry-документация (документационный пробел).

**OpenAI** (developers.openai.com/api/docs):
- [.../guides/text](https://developers.openai.com/api/docs/guides/text) — Responses API рекомендован над Chat Completions.
- [.../quickstart](https://developers.openai.com/api/docs/quickstart) — SDK `openai`.
- [.../guides/structured-outputs](https://developers.openai.com/api/docs/guides/structured-outputs) — гарантированное соответствие схеме, ограничения, поддерживаемые модели.
- [.../guides/function-calling](https://developers.openai.com/api/docs/guides/function-calling) — модель только предлагает вызов.
- [.../guides/streaming-responses](https://developers.openai.com/api/docs/guides/streaming-responses) — типизированные SSE-события.
- [.../pricing](https://developers.openai.com/api/docs/pricing) — cached input, batch, flex, региональная надбавка.
- [.../guides/rate-limits](https://developers.openai.com/api/docs/guides/rate-limits) — RPM/RPD/TPM/TPD/IPM, 6 тиров.
- [.../guides/batch](https://developers.openai.com/api/docs/guides/batch) — Batch API, ~24ч, ~50% скидка.
- [.../deprecations](https://developers.openai.com/api/docs/deprecations) — tiered deprecation notice, статус Legacy.
- [.../guides/your-data](https://developers.openai.com/api/docs/guides/your-data) — data usage policy с 2023-03-01, retention, ZDR (enterprise-privacy страница вернула 403 и не использовалась как источник).
- [.../guides/error-codes](https://developers.openai.com/api/docs/guides/error-codes) — HTTP-коды, SDK exceptions, «Slow Down» retry guidance.

**Anthropic** (platform.claude.com/docs, privacy.claude.com):
- [.../api/messages](https://platform.claude.com/docs/en/api/messages) — Messages API, content blocks, stop_reason.
- [.../cli-sdks-libraries/sdks/python](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) — SDK `anthropic`, retry/timeout defaults.
- [.../agents-and-tools/tool-use/overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) — tool use, server-side tools.
- [.../build-with-claude/structured-outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) и [.../agents-and-tools/tool-use/strict-tool-use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use) — гарантированное соответствие схеме, ограниченное подмножество JSON Schema.
- [.../api/rate-limits](https://platform.claude.com/docs/en/api/rate-limits) — тиры, token-bucket, живые заголовки, Rate Limits API.
- [.../about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing) — снимок цен Opus 5/Sonnet 5/Haiku 4.5, коэффициенты prompt caching.
- [.../about-claude/model-deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) — Active→Legacy→Deprecated→Retired, ≥60 дней уведомления.
- [.../build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — механика и TTL кэша.
- [privacy.claude.com/en/articles/7996868](https://privacy.claude.com/en/articles/7996868) — data usage/training policy по умолчанию, feedback retention до 5 лет.

**Google Gemini** (ai.google.dev):
- [.../gemini-api/docs](https://ai.google.dev/gemini-api/docs) — Interactions API как рекомендуемая точка входа; SDK `google.genai`.
- [.../gemini-api/docs/function-calling](https://ai.google.dev/gemini-api/docs/function-calling) — модель только предлагает вызов, режимы auto/any/none.
- [.../gemini-api/docs/text-generation](https://ai.google.dev/gemini-api/docs/text-generation) — streaming через `step.delta`.
- [.../gemini-api/docs/tokens](https://ai.google.dev/gemini-api/docs/tokens) — детализированный usage-объект, `count_tokens`.
- [.../gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits) — RPM/TPM/RPD по тиру, отдельный spend-based лимит.
- [.../gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) — снимок цен, тир-based data usage policy (free/paid), context caching billing.
- [.../gemini-api/docs/batch-api](https://ai.google.dev/gemini-api/docs/batch-api) — асинхронный Batch API, ~24ч цель, 50% скидка, хранение результатов 6 недель.
- [.../gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models) — 4-стадийный lifecycle (Stable/Preview/Latest/Experimental), политика уведомлений.
- [.../gemini-api/docs/troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting) — явное разделение retryable/non-retryable ошибок, дефолтный SDK backoff.

Полный официальный `/gemini-api/docs/api-errors` код-референс и страница `/gemini-api/terms` не были независимо получены — соответствующие утверждения ограничены тем, что явно подтверждено через страницы troubleshooting и pricing (см. открытый вопрос, раздел 63, где применимо).

Выводы, использованные в разделах 17–19, 22–24, 28–30, 34–35, 39–40, 42, 46–47, 50–51, 56–57 настоящего ADR, основаны на перечисленных источниках; длинные цитаты в текст ADR намеренно не включены.
