# Document Register

**Статус:** Утверждён
**Владелец:** Product Owner
**Дата последнего изменения:** 2026-08-05
**Назначение:** хранить единый перечень управляемых документов и их актуальный статус.

Правила ведения реестра определены в [`docs/processes/DOCUMENTATION_STANDARD.md`](./processes/DOCUMENTATION_STANDARD.md), раздел 18.

---

## Реестр управляемых документов

| Путь | Название | Категория | Статус | Владелец | Назначение | Последнее изменение | Заменяет / заменён документом | Примечание |
|---|---|---|---|---|---|---|---|---|
| `PROJECT_CHARTER.md` | PROJECT CHARTER | Корневой документ | Утверждён | Product Owner | Определить полномочия, базовые правила и порядок управления проектом. | 2026-08-05 | — | Высший источник истины по ролям и правилам. |
| `README.md` | AI Trading Assistant Platform | Корневой документ | Утверждён | Product Owner | Краткий входной обзор проекта для новых участников. | 2026-08-05 | — | Не заменяет специализированные документы. |
| `docs/processes/GIT_WORKFLOW.md` | Git Workflow | processes | Утверждён | Product Owner | Определить безопасный процесс работы с Git и GitHub. | 2026-08-05 | — | Детализирует раздел 9 устава. |
| `docs/processes/DOCUMENTATION_STANDARD.md` | Documentation Standard | processes | Утверждён | Product Owner | Определить единые правила создания, изменения, хранения и утверждения проектной документации. | 2026-08-05 | — | Детализирует разделы 10 и 16 устава. |
| `docs/DOCUMENT_REGISTER.md` | Document Register | processes | Утверждён | Product Owner | Хранить единый перечень управляемых документов и их актуальный статус. | 2026-08-05 | — | Настоящий документ. |
| `.ai-context/CURRENT_STATE.md` | Current Project State | AI context | Утверждён | Product Owner | Предоставить AI-агентам краткий актуальный контекст перед началом задачи. | 2026-08-05 | — | Оперативный, не архитектурный источник состояния. |
| `templates/CLAUDE_TASK_TEMPLATE.md` | Claude Task Template | templates | Утверждён | Product Owner | Обеспечить единый безопасный формат постановки задач Claude. | 2026-08-05 | — | Не содержит реальных значений задачи. |
| `docs/processes/ADR_PROCESS.md` | ADR Process | processes | Утверждён | Product Owner | Определить порядок работы с архитектурными решениями. | 2026-08-05 | — | Определяет процесс архитектурных решений. |
| `templates/ADR_TEMPLATE.md` | ADR Template | templates | Утверждён | Product Owner | Обеспечить единый формат ADR. | 2026-08-05 | — | Утверждённый шаблон ADR. |
| `docs/architecture/ENGINEERING_PRINCIPLES.md` | Engineering Principles | architecture | Утверждён | Product Owner | Определить общие инженерные принципы платформы. | 2026-08-05 | — | Общие инженерные принципы без выбора стека. |
| `docs/product/PRODUCT_SCOPE.md` | Product Scope | product | Утверждён | Product Owner | Определить назначение, границы, пользователей и этапы развития продукта. | 2026-08-05 | — | Утверждённые границы и этапы продукта. |
| `docs/product/FUNCTIONAL_REQUIREMENTS.md` | Functional Requirements | product | Утверждён | Product Owner | Определить функциональные требования AI Trading Assistant Platform. | 2026-08-05 | — | Утверждённые функциональные требования. |
| `docs/product/NON_FUNCTIONAL_REQUIREMENTS.md` | Non-Functional Requirements | product | Утверждён | Product Owner | Определить измеримые нефункциональные требования платформы и открытые целевые показатели. | 2026-08-05 | — | Утверждённые нефункциональные требования и открытые измеримые показатели. |
| `docs/product/USER_JOURNEYS.md` | User Journeys | product | Утверждён | Product Owner | Определить ключевые пользовательские сценарии платформы. | 2026-08-05 | — | Утверждённые пользовательские сценарии. |
| `docs/architecture/LOGICAL_ARCHITECTURE.md` | Logical Architecture | architecture | Утверждён | Product Owner | Определить логическую архитектуру AI Trading Assistant Platform без привязки к конкретному стеку. | 2026-08-05 | — | Утверждённая логическая архитектура без выбора стека. |
| `docs/architecture/MODULE_BOUNDARIES.md` | Module Boundaries | architecture | Утверждён | Product Owner | Определить логические границы модулей и разрешённые зависимости между ними. | 2026-08-05 | — | Утверждённые границы модулей и зависимостей. |
| `docs/architecture/DATA_FLOWS.md` | Data Flows | architecture | Утверждён | Product Owner | Определить основные логические потоки данных платформы. | 2026-08-05 | — | Утверждённые логические потоки данных. |
| `docs/architecture/FAILURE_MODEL.md` | Failure Model | architecture | Утверждён | Product Owner | Определить классы отказов, ожидаемое поведение и границы деградации платформы. | 2026-08-05 | — | Утверждённая модель отказов и деградации. |
| `docs/architecture/TECHNOLOGY_EVALUATION.md` | Technology Evaluation | architecture | Утверждён | Product Owner | Сравнить технологические варианты для MVP и подготовить основания для отдельных ADR выбора стека. | 2026-08-05 | — | Утверждённое сравнительное основание для отдельных ADR; не является действующим решением о технологическом стеке. |
| `docs/decisions/ADR-0001-backend-language-and-runtime.md` | ADR-0001 — Backend Language and Runtime | decisions | Утверждён | Product Owner | Выбрать язык и runtime backend платформы. | 2026-08-05 | — | Утверждённое архитектурное решение: CPython 3.14 как backend language/runtime для MVP. |
| `docs/decisions/ADR-0002-backend-api-adapter.md` | ADR-0002 — Backend API Adapter | decisions | Утверждён | Product Owner | Выбрать HTTP/ASGI API adapter backend платформы. | 2026-08-05 | — | Утверждённое архитектурное решение: FastAPI как внешний HTTP/ASGI API adapter backend платформы. |
| `docs/decisions/ADR-0003-frontend-stack.md` | ADR-0003 — Frontend Stack | decisions | Утверждён | Product Owner | Выбрать язык, UI-библиотеку и framework первого веб-клиента. | 2026-08-05 | — | Утверждённое архитектурное решение: TypeScript, React и Next.js App Router как frontend stack первого веб-клиента. |
| `docs/decisions/ADR-0004-primary-data-store.md` | ADR-0004 — Primary Data Store | decisions | На ревью | Product Owner | Выбрать основное транзакционное хранилище данных платформы. | 2026-08-05 | — | Ожидает архитектурного ревью и принятия Product Owner. |

---

## Правила

1. Реестр обновляется в той же задаче, в которой документ создаётся, утверждается, заменяется или архивируется.
2. Управляемый документ, отсутствующий в реестре, считается нарушением процесса.
3. `README.md` является входным обзором, но не заменяет специализированные документы (устав, процессы, ADR, архитектурные документы).
4. `CURRENT_STATE.md` не заменяет ADR или архитектурные документы — он лишь указывает на их текущее состояние утверждения.
5. Реестр содержит только управляемые документы по определению `DOCUMENTATION_STANDARD.md` (раздел 2.1) и не является перечнем каждого файла репозитория.
