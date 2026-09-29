# Roadmap

## Текущее состояние

``` text
v0.0-demo
   |
   v
v0.1-pilot
   |
   v
v0.2-product-pilot
   |
   v
future production architecture
```

`v0.0-demo` --- зафиксированная демонстрационная версия.

Главная текущая задача --- не расширять архитектуру, а сделать
существующий end-to-end flow достаточно воспроизводимым для первого
контролируемого пилота.

------------------------------------------------------------------------

# v0.1-pilot --- Stabilization

## Цель

Развернуть текущую систему в ограниченной тестовой среде и получить
реальные результаты использования на некритичных документах.

## Что сохраняем

Не переписываем перед первым пилотом:

-   Qt client;
-   Auth Service;
-   Handler;
-   Agent Registry/Executor;
-   document upload;
-   automatic agent selection/creation;
-   RAG;
-   embeddings/reranking;
-   drawing pipeline;
-   llama.cpp inference.

## P0 --- обязательно до пилота

### Runtime stability

-   корректно обрабатывать недоступный llama.cpp server;
-   вместо необработанного internal error возвращать понятную ошибку;
-   исправить известные проблемы чтения config/JSON, включая BOM;
-   проверить startup с чистого состояния;
-   проверить restart всей системы.

### Persistence

Провести сценарий:

``` text
create user
-> create/load agents
-> upload documents
-> ask questions
-> stop services
-> start services
-> login
-> verify agents
-> verify documents
-> verify RAG
```

Зафиксировать, какие данные являются persistent, а какие runtime-only.

### Security hygiene

-   secrets только через environment;
-   `.env` не хранится в Git;
-   рабочий `.env.example`;
-   не публиковать PostgreSQL/llama.cpp наружу без необходимости;
-   первый pilot только на некритичных документах;
-   проверить отсутствие секретов в logs/repository.

### Regression

Зафиксировать автоматическими или воспроизводимыми тестами основные demo
scenarios:

-   Incident Response;
-   повторное использование агента для второго документа домена;
-   Medical Device RAG;
-   technical drawing;
-   legal/document wording regression.

### Deployment

Подготовить воспроизводимый порядок запуска:

``` text
llama.cpp
-> docker compose
-> health checks
-> Qt client
```

Подготовить Windows release Qt client.

## P1 --- желательно до/в начале пилота

-   backend readiness endpoint;
-   проверка inference runtime в health/readiness;
-   унифицированные API errors;
-   startup scripts;
-   pilot dataset;
-   краткая installation guide;
-   логирование ошибок без утечки содержимого документов/secrets;
-   базовый checklist для пилотной машины.

## Не входит в v0.1

Не блокировать первый pilot следующими задачами:

-   VLM;
-   streaming generation;
-   новый OIDC provider;
-   полная переработка Auth Service;
-   новый orchestrator;
-   полная ACL-aware RAG архитектура;
-   переписывание backend на C++/Rust/Go;
-   масштабный redesign GUI;
-   полный model gateway rewrite.

------------------------------------------------------------------------

# v0.2-product-pilot

Функциональность определяется в том числе результатами первого пилота.

Предварительные направления:

## Conversations

-   persistent conversation history;
-   список диалогов;
-   восстановление контекста;
-   удаление/архивация.

## Document Manager

-   список документов;
-   статус обработки;
-   владелец/источник;
-   повторная индексация;
-   удаление;
-   понятная связь document -\> agent.

## Streaming UX

-   streaming ответа;
-   Stop generation;
-   состояние inference;
-   progress для долгой обработки документа.

## Roles and groups

-   user groups;
-   roles;
-   resource ownership;
-   административные операции.

## ACL-aware RAG

Retrieval должен учитывать права пользователя до передачи context в LLM.

Цель:

``` text
User permissions
      |
      v
Allowed documents/chunks
      |
      v
Retrieval
      |
      v
LLM
```

Нельзя полагаться на prompt как на security boundary.

## Multi-user runtime

-   изоляция пользовательского состояния;
-   concurrent requests;
-   ограничения ресурсов;
-   model queue/backpressure;
-   безопасные shared agents.

## Deployment

-   более простой installer/startup;
-   configuration validation;
-   readiness/liveness;
-   backup/restore;
-   controlled updates.

## Model layer

-   единый provider interface;
-   убрать рассинхронизацию legacy Transformers и llama.cpp;
-   единая модель ошибок;
-   provider health;
-   model metadata, соответствующая реальному runtime.

## Quality

-   integration test suite;
-   restart tests;
-   document corpus regression;
-   latency metrics;
-   retrieval quality checks.

------------------------------------------------------------------------

# Future / Research

Эти направления не являются обязательствами ближайшего pilot release.

## VLM

Добавить настоящий vision-language provider для случаев, где CV/OCR
pipeline недостаточен.

Текущий drawing pipeline продолжает быть полезным для детерминированного
извлечения геометрии/OCR.

## Orchestration

Более сложное взаимодействие нескольких агентов, если реальные use cases
покажут необходимость.

Не добавлять orchestration только ради количества агентов.

## External identity / OIDC

Возможная интеграция с корпоративным Identity Provider.

AuthN и AuthZ должны оставаться разделёнными концепциями.

## Native core

В перспективе deterministic/product logic может быть вынесена в compiled
service (C++/Rust/Go), а Python сохранён для AI/RAG experimentation.

Это не является задачей ближайшего rewrite.

## Observability

-   structured logs;
-   traces;
-   metrics;
-   model latency;
-   retrieval latency;
-   error rates;
-   privacy-aware audit events.

## Model serving

Возможный отдельный model gateway/runtime management layer:

``` text
Backend
   |
Model Provider API
   |
   +--> llama.cpp
   +--> other local runtime
   +--> approved remote provider
```

------------------------------------------------------------------------

# Принцип планирования

Новые функции добавляются после ответа на вопрос:

> Какую проблему пилотного пользователя это решает?

До первого пилота приоритет:

``` text
reproducibility
> stability
> persistence
> security hygiene
> observability
> new features
```

После первого пилота roadmap пересматривается на основании фактических
сценариев, ошибок и обратной связи.
