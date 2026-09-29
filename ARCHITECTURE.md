# Architecture

## 1. Назначение системы

Проект представляет собой desktop-клиент и набор backend-компонентов для
корпоративной работы с документами через специализированных LLM-агентов.

Основная идея: пользователь не обязан вручную выбирать модель,
RAG-индекс или внутреннюю команду. Handler и routing-слой переводят
запрос пользователя в действия над агентами и документами.

## 2. Компоненты

``` text
+-------------------------+
|      Qt Desktop GUI     |
|                         |
| AuthClient    ApiClient |
+-----|--------------|----+
      |              |
      v              v
+-------------+  +-----------------------------+
| Auth Service|  | Multi-Agent FastAPI Backend |
| FastAPI     |  |                             |
+------|------+  | Handler / CommandRouter     |
       |         | AgentExecutor / Registry    |
       v         | Documents / Routing / RAG   |
+-------------+  | Vision / Metrics            |
| PostgreSQL  |  +--------------|--------------+
+-------------+                 |
                                v
                         +--------------+
                         | llama.cpp API |
                         +--------------+
```

### Qt Desktop Client

`gui_qt/`

C++20 + Qt Widgets + Qt Network.

Основные сетевые клиенты:

-   `AuthClient` --- регистрация, login, refresh, logout, `/auth/me`;
-   `ApiClient` --- запросы к Multi-Agent Backend;
-   Bearer access token добавляется к запросам Agent API.

### Auth Service

`auth_service/`

Отдельное FastAPI-приложение. Отвечает за:

-   пользователей;
-   password hashing;
-   JWT access token;
-   refresh token rotation/revocation;
-   роли;
-   PostgreSQL;
-   Alembic migrations.

Основные endpoints:

``` text
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
GET  /health
```

### Multi-Agent Backend

`backend/app/main.py`

Основное FastAPI-приложение. При старте создаёт:

``` text
AgentRegistry
CommandStore
Handler
AgentExecutor
CommandRouter
```

Большинство рабочих endpoints требует `get_current_user`.

Основные endpoints:

``` text
GET    /agents
POST   /agents
DELETE /agents/{agent_name}

POST   /agents/{agent_name}/run
POST   /agents/{agent_name}/retrieve

POST   /handler

POST   /documents/route
POST   /documents/upload

POST   /logger/resolve
GET    /logs/state
GET    /logs/metrics
```

## 3. Центральный runtime flow

### Запрос через Handler

``` text
User
 |
 v
Qt ApiClient
 |
 v
POST /handler
 |
 v
CommandRouter.handle_user_request()
 |
 v
Handler
 |
 +--> SYSTEM Q&A -> natural-language response
 |
 +--> command JSON
          |
          v
     AgentExecutor
          |
          v
     requested operation
          |
          v
     ResponseCompiler / result
```

Handler имеет несколько provider implementations:

-   `LlamaCppHandler`;
-   `LocalLLMHandler`;
-   `GigaChatHandler`;
-   `RuleBasedHandler`.

Factory выбирает реализацию по конфигурации/environment.

Текущий основной локальный путь --- `LlamaCppHandler`, который
обращается к OpenAI-compatible endpoint:

``` text
POST {LLAMACPP_BASE_URL}/v1/chat/completions
```

Для Qwen3 к пользовательскому сообщению добавляется `/no_think`.

### SYSTEM Q&A и команды

Handler разделяет два типа поведения.

**SYSTEM Q&A** --- пользователь спрашивает о состоянии/устройстве
системы. Handler должен вернуть обычный текст.

**Command mode** --- Handler преобразует запрос в структурированную
команду, которая затем выполняется `AgentExecutor`.

В `LlamaCppHandler` присутствует дополнительная защита: запрос, уже
классифицированный как SYSTEM Q&A, не должен превращаться в исполняемую
JSON-команду.

## 4. Agent subsystem

### AgentRegistry

`backend/app/engine/agent_registry.py`

Registry:

-   загружает metadata агентов из `backend/config/agents.json`;
-   создаёт runtime instances;
-   регистрирует/обновляет/удаляет агентов;
-   сохраняет конфигурацию;
-   предоставляет metadata Handler-у;
-   участвует в выборе агента;
-   разрешает model assignment.

### LLMAgent

`backend/app/engine/agent.py`

Runtime специализированного агента.

Agent содержит:

-   name;
-   description;
-   system prompt;
-   tags;
-   model metadata;
-   generation parameters;
-   RAG memory.

Inference поддерживает внешний llama.cpp и legacy/local model runtime.

Перед генерацией агент может получить RAG context и source metadata.

### AgentExecutor

`backend/app/engine/agent_executor.py`

Исполняет структурированные команды системы.

Среди реализованных действий присутствуют:

-   create/delete/edit agent;
-   list agents;
-   run agent;
-   add/delete/edit/load data;
-   route document;
-   retrieve;
-   logger/system operations;
-   legacy actions.

`AgentExecutor` является важной границей между интерпретацией намерения
Handler-ом и фактическим изменением состояния системы.

## 5. Document pipeline

Высокоуровневый поток:

``` text
Upload
  |
  v
backend/server_storage/uploads/
  |
  v
DocumentRouter
  |
  +--> document parsing/normalization
  |
  +--> drawing analysis when applicable
  |
  +--> agent proposal
  |
  +--> semantic matching with existing agents
  |
  +--> create/reuse agent
  |
  v
AgentMemory.add_document()
  |
  +--> chunking
  +--> embeddings
  +--> persistent index
```

`POST /documents/upload` сохраняет файл в `server_storage/uploads`,
затем передаёт действие `route_document` в `CommandRouter`.

### Documents package

`backend/app/documents/`

-   `processor.py` --- обработка/нормализация документа;
-   `agent_proposer.py` --- предложение специализации агента;
-   `drawing_analyzer.py` --- интеграция анализа изображений/чертежей;
-   `models.py` --- структуры данных document pipeline.

### DocumentRouter

`backend/app/engine/document_router.py`

Связывает обработанный документ с системой агентов.

Его задача --- определить, подходит ли существующий агент, и
организовать дальнейшую загрузку документа.

## 6. RAG

`backend/app/rag/memory.py`

Каждый агент имеет `AgentMemory`.

Persistent layout текущего прототипа:

``` text
backend/server_storage/rag/<AgentName>/
├── index.json
└── embeddings.npy
```

Memory поддерживает:

-   загрузку сохранённого индекса;
-   добавление документа;
-   deduplication/content hash;
-   retrieval;
-   source metadata.

### Embeddings и reranking

`backend/app/routing/embeddings.py`

`EmbeddingService` лениво загружает:

-   embedding model;
-   reranker.

Пути задаются environment variables:

``` text
EMBEDDING_MODEL_PATH
RERANKER_MODEL_PATH
EMBEDDING_DEVICE
```

В текущем `.env.example` embedding model ожидается в
`/project/models/bge-m3`, reranker --- в `/project/models/reranker`.

## 7. Semantic routing

`backend/app/routing/`

-   `agent_profile.py` --- представление профиля агента;
-   `chunker.py` --- разбиение текста;
-   `embeddings.py` --- embeddings/reranking;
-   `semantic_router.py` --- семантическое сопоставление
    документа/запроса;
-   `complexity/` --- оценка сложности и reasoning policy.

Это отдельный слой от Handler: Handler работает с пользовательским
намерением и командами, semantic routing --- с содержимым и
соответствием специализации агента.

## 8. Complexity routing

`backend/app/routing/complexity/`

Содержит:

-   `router.py`;
-   `service.py`;
-   `policy.py`.

Включается через:

``` text
COMPLEXITY_ROUTER_ENABLED=true
COMPLEXITY_ROUTER_PATH=/project/models/complexity_router
```

Результат классификации используется для построения reasoning policy
агента.

Модель complexity router хранится локально и не должна попадать в Git.

## 9. Drawing/Vision pipeline

`backend/app/vision/drawing_pipeline.py`

Текущая реализация не является VLM pipeline.

Она использует классический CV/OCR подход и содержит, среди прочего:

-   scan quality analysis;
-   deskew/rotation;
-   preprocessing;
-   line detection;
-   circle detection;
-   rectangle/contour detection;
-   OCR;
-   language detection;
-   diagram parsing;
-   title-block extraction;
-   structured interpretation.

`DRAWING_CLIP_ENABLED=false` в текущем `.env.example`.

Результат изображения преобразуется в структурированное
текстовое/JSON-представление, которое затем может использоваться RAG и
агентом.

## 10. Persistence

### Auth

PostgreSQL хранится в Docker volume:

``` text
auth_postgres_data
```

### Agent metadata

``` text
backend/config/agents.json
```

### Runtime documents/RAG

``` text
backend/server_storage/
```

Содержимое включает uploads, обработанные документы и RAG indices.

Важно: `server_storage/` --- runtime state и не должен использоваться
как исходный fixture repository.

## 11. Model runtime

В проекте сейчас сосуществуют два поколения model integration.

### Актуальный путь

``` text
Backend -> HTTP -> llama.cpp server -> Qwen3
```

Environment:

``` text
HANDLER_PROVIDER=llamacpp
AGENT_INFERENCE_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://host.docker.internal:8081
LLAMACPP_MODEL=Qwen3-4B
```

### Legacy/local Transformers path

В коде остаются:

-   `ModelManager`;
-   `ModelRegistry`;
-   Qwen2.5-related configuration;
-   local provider;
-   Agent Proposer local model settings.

Это технический долг, а не две полностью независимые
production-архитектуры. Перед дальнейшим развитием model layer
желательно унифицировать provider abstraction.

## 12. Текущие архитектурные ограничения

Для `v0.1-pilot` важно не переписывать систему, а стабилизировать
существующий flow.

Известные зоны развития:

-   единая обработка ошибок model provider;
-   health/readiness для llama.cpp;
-   устранение рассинхронизации Qwen2.5 metadata и Qwen3 runtime;
-   проверка persistence после полного restart;
-   ACL-aware retrieval;
-   conversations/document management;
-   multi-user isolation;
-   production deployment;
-   унификация model provider layer.

Целевая архитектура не должна считаться уже реализованной: этот документ
описывает прежде всего текущее состояние `v0.0-demo`.
