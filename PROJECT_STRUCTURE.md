# Project Structure

Этот документ предназначен для быстрого знакомства разработчика с
кодовой базой.

## Корень

``` text
.
├── auth_service/
├── backend/
├── gui_qt/
├── Docs/
├── models/
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

### `docker-compose.yml`

Поднимает:

-   PostgreSQL;
-   Auth Service;
-   Multi-Agent Backend.

llama.cpp в текущем compose не поднимается и запускается отдельно на
host.

Backend монтирует:

``` text
./models                 -> /project/models
./backend/config         -> /project/backend/config
./backend/logs           -> /project/backend/logs
./backend/server_storage -> /project/backend/server_storage
```

### `.env.example`

Общий шаблон environment.

Содержит настройки:

-   PostgreSQL;
-   JWT;
-   Handler provider;
-   Agent inference provider;
-   llama.cpp;
-   legacy local model runtime;
-   GigaChat;
-   embeddings/reranker;
-   agent proposer;
-   complexity router;
-   drawing/OCR.

`.env` содержит локальные secrets/settings и не должен попадать в Git.

------------------------------------------------------------------------

# `auth_service/`

Независимый сервис authentication/authorization.

``` text
auth_service/
├── alembic/
├── app/
│   ├── api/
│   ├── auth/
│   ├── db/
│   └── users/
├── Dockerfile
├── alembic.ini
├── requirements.txt
└── README.md
```

## `app/main.py`

Создаёт FastAPI app, CORS middleware и подключает health/auth routers.

## `app/auth/`

### `router.py`

HTTP endpoints регистрации, login, refresh, logout и получения текущего
пользователя.

### `security.py`

Security primitives: password/token-related операции.

### `schemas.py`

Pydantic API schemas.

### `dependencies.py`

FastAPI dependencies для аутентифицированных запросов.

## `app/db/`

### `models.py`

SQLAlchemy database models.

### `session.py`

Database engine/session setup.

### `base.py`

Base model configuration.

## `app/users/service.py`

Операции с пользователями на уровне service layer.

## `alembic/`

Database migrations. При Docker startup выполняется:

``` text
alembic upgrade head
```

------------------------------------------------------------------------

# `backend/`

Основной сервис мультиагентной системы.

``` text
backend/
├── app/
│   ├── auth/
│   ├── documents/
│   ├── engine/
│   ├── handlers/
│   ├── models/
│   ├── rag/
│   ├── routing/
│   └── vision/
├── config/
├── server_storage/
├── logs/
├── tests/
└── Dockerfile
```

## `backend/app/main.py`

Composition root Backend.

Здесь:

-   создаётся FastAPI;
-   загружаются config files;
-   создаются `AgentRegistry`, `CommandStore`, Handler, `AgentExecutor`,
    `CommandRouter`;
-   объявляются HTTP endpoints.

При поиске точки входа в backend начинать отсюда.

------------------------------------------------------------------------

# `backend/app/auth/`

Интеграция основного Backend с Auth Service/JWT.

### `dependencies.py`

Содержит:

-   `get_current_user`;
-   `require_role`.

Endpoints Backend используют `Depends(get_current_user)`.

------------------------------------------------------------------------

# `backend/app/engine/`

Основная orchestration/business-логика текущего прототипа.

## `agent.py`

`LLMAgent`.

Отвечает за runtime одного специализированного агента:

-   metadata;
-   generation config;
-   model provider;
-   RAG context;
-   generation;
-   операции с данными агента.

Если задача связана с тем, **как конкретный агент отвечает**, начинать
здесь.

## `agent_registry.py`

`AgentRegistry`.

Отвечает за lifecycle агентов:

-   load/save metadata;
-   create/upsert/update/delete;
-   получение runtime instance;
-   model resolution;
-   список агентов;
-   выбор агента;
-   представление registry для Handler.

Если задача связана с тем, **какие агенты существуют**, начинать здесь.

## `agent_executor.py`

`AgentExecutor`.

Исполняет структурированные действия:

``` text
Handler/CommandRouter
        |
        v
   AgentExecutor
        |
        +--> create agent
        +--> delete/edit agent
        +--> run agent
        +--> route document
        +--> retrieve
        +--> logging/state operations
```

Если Handler уже сформировал команду, её фактическое выполнение обычно
находится здесь.

## `command_router.py`

Связывает внешние запросы, Handler и Executor.

Основные entry points:

-   `route`;
-   `route_many`;
-   `route_file`;
-   `route_by_agent_name`;
-   `handle_user_request`.

## `command_store.py`

Загружает описание доступных команд из config и предоставляет retrieval
команд для Handler prompt.

## `document_router.py`

Orchestration маршрутизации документа.

Связывает document processing, agent proposal/selection и дальнейшую
загрузку документа.

## `document_loader.py`

Чтение и сохранение документов для агента.

## `response_compiler.py`

Преобразует результаты внутренних команд в итоговые ответы.

## `metrics_logger.py`

Сбор request metrics и формирование summary.

## `system_logger.py`

Состояние системы и операции разрешения logger conflicts.

------------------------------------------------------------------------

# `backend/app/handlers/`

Интерпретация пользовательского запроса.

## `base.py`

Абстрактный интерфейс Handler.

## `factory.py`

Создаёт конкретный Handler provider на основании config/environment.

Это первая точка при изменении provider selection.

## `llamacpp.py`

Текущий основной Handler для локального inference.

Обращается к:

``` text
/v1/chat/completions
```

внешнего llama.cpp server.

## `local_llm.py`

Legacy/local Transformers Handler.

## `gigachat.py`

GigaChat provider.

## `rule_based.py`

Rule-based fallback/implementation.

## `prompt.py`

Формирование system prompt Handler-а и определение SYSTEM Q&A.

## `output_parser.py`

Преобразование ответа модели в внутренний `HandlerOutput`/commands.

------------------------------------------------------------------------

# `backend/app/documents/`

Подготовка входящих документов.

## `processor.py`

Основной document processing.

## `agent_proposer.py`

Формирует предложение о специализации агента для документа.

В текущей конфигурации эта часть всё ещё может использовать legacy/local
model settings, поэтому её не следует автоматически считать переведённой
на тот же runtime, что Handler.

## `drawing_analyzer.py`

Связь document pipeline с обработкой изображений/схем.

## `models.py`

Структуры данных document pipeline.

------------------------------------------------------------------------

# `backend/app/rag/`

## `memory.py`

Persistent RAG memory конкретного агента.

Ключевые сущности:

-   `MemoryChunk`;
-   `RetrievedChunk`;
-   `AgentMemory`.

Основные операции:

-   load/save index;
-   `add_document`;
-   `retrieve`.

Persistent files:

``` text
backend/server_storage/rag/<AgentName>/index.json
backend/server_storage/rag/<AgentName>/embeddings.npy
```

------------------------------------------------------------------------

# `backend/app/routing/`

Semantic routing и model-assisted routing.

## `agent_profile.py`

Профиль агента для routing.

## `chunker.py`

Разбиение текста на chunks.

## `embeddings.py`

`EmbeddingService`.

Отвечает за:

-   загрузку embedding model;
-   embeddings;
-   загрузку reranker;
-   reranking.

## `semantic_router.py`

Semantic matching между документом/запросом и профилями агентов.

## `complexity/`

``` text
complexity/
├── policy.py
├── router.py
└── service.py
```

Оценка сложности запроса и построение reasoning policy.

------------------------------------------------------------------------

# `backend/app/models/`

Legacy/local model management.

## `model_manager.py`

Кэширование и загрузка физических Transformers runtimes.

## `model_registry.py`

Поиск локальных model directories и model selection policy.

Не путать с `engine/agent_registry.py`:

``` text
AgentRegistry -> управляет агентами
ModelRegistry -> управляет доступными локальными моделями
```

При llama.cpp inference физическая LLM находится во внешнем процессе,
поэтому роль этого пакета должна уменьшаться по мере унификации provider
layer.

------------------------------------------------------------------------

# `backend/app/vision/`

CV/OCR pipeline для изображений и технических документов.

## `drawing_pipeline.py`

Большой procedural pipeline:

-   scan quality;
-   preprocessing;
-   geometry;
-   OCR;
-   language detection;
-   diagram parsing;
-   interpretation.

## `clip_tags.py`

CLIP-related функциональность.

В текущем `.env.example`:

``` text
DRAWING_CLIP_ENABLED=false
```

То есть CLIP нельзя считать обязательной частью текущего рабочего
pipeline.

------------------------------------------------------------------------

# `backend/config/`

Runtime configuration.

``` text
agents.json
commands.json
core_config.json
model_policy.json
```

### `agents.json`

Persistent metadata текущих агентов.

### `commands.json`

Описание команд, доступных Handler/CommandStore.

### `core_config.json`

Базовая Handler/provider configuration.

Часть значений может быть переопределена environment variables.

### `model_policy.json`

Policy поиска/выбора локальных Transformers models.

------------------------------------------------------------------------

# `backend/server_storage/`

Runtime state, а не исходный код.

Содержит:

``` text
uploads/
documents/
processed/
rag/
```

Не использовать содержимое этой директории как обязательную часть Git
checkout.

------------------------------------------------------------------------

# `backend/logs/`

Runtime logs/metrics.

Не являются исходным кодом.

------------------------------------------------------------------------

# `backend/tests/`

Существующие тесты включают:

-   document processor smoke;
-   engine;
-   integrated MVP;
-   MVP;
-   semantic router.

Для `v0.1-pilot` сюда следует добавить regression tests демонстрационных
сценариев и restart/persistence checks.

------------------------------------------------------------------------

# `gui_qt/`

Desktop application на C++20/Qt.

``` text
gui_qt/
├── api_client.*
├── auth_client.*
├── login_dialog.*
├── register_dialog.*
├── main_window.*
├── settings_dialog.*
├── main.cpp
└── CMakeLists.txt
```

## `main.cpp`

Entry point GUI.

## `auth_client.*`

HTTP client Auth Service.

Поддерживает:

-   register;
-   login;
-   refresh;
-   logout;
-   `/auth/me`.

## `api_client.*`

HTTP client Multi-Agent Backend.

Работает с:

-   `/agents`;
-   `/handler`;
-   `/agents/{name}/run`;
-   `/documents/route`;
-   `/documents/upload`.

Добавляет Bearer token к запросам.

## `login_dialog.*`

Login UI.

## `register_dialog.*`

Registration UI.

## `main_window.*`

Основной интерфейс Multi-Agent Chat.

## `settings_dialog.*`

Настройка адреса Agent Service и связанных параметров GUI.

## `CMakeLists.txt`

Qt Core + Widgets + Network, C++20.

`build/`, `build2/` и `CMakeLists.txt.user` являются локальными
build/IDE artifacts и не должны использоваться как часть архитектуры
проекта.

------------------------------------------------------------------------

# `Docs/`

Тестовые документы для ручной проверки document/RAG/vision pipeline.

Это fixtures/demo data, а не runtime storage.

Следует отдельно следить за лицензированием сторонних PDF/изображений
перед публичным распространением репозитория.

------------------------------------------------------------------------

# `models/`

Локальные model weights.

Не хранится в Git.

Текущий рабочий проект использует эту директорию для
embeddings/reranker/complexity и legacy model paths.

Разработчик должен получить необходимые модели отдельным способом,
описанным командой проекта.

------------------------------------------------------------------------

# Куда идти с типовой задачей

  -----------------------------------------------------------------------
  Задача                              Начать с
  ----------------------------------- -----------------------------------
  Новый Backend endpoint              `backend/app/main.py`

  Handler неправильно понимает запрос `handlers/prompt.py`,
                                      `handlers/llamacpp.py`,
                                      `handlers/output_parser.py`

  Команда понимается, но выполняется  `engine/agent_executor.py`
  неправильно                         

  Агент отвечает неправильно          `engine/agent.py`

  Агент не создаётся/не               `engine/agent_registry.py`
  восстанавливается                   

  Документ попал не к тому агенту     `engine/document_router.py`,
                                      `routing/semantic_router.py`

  Плохой retrieval                    `rag/memory.py`,
                                      `routing/embeddings.py`

  Проблема OCR/схемы                  `vision/drawing_pipeline.py`

  Проблема login/token                `auth_service/app/auth/`,
                                      `gui_qt/auth_client.*`

  GUI/API интеграция                  `gui_qt/api_client.*`

  Модель llama.cpp недоступна         `handlers/llamacpp.py`,
                                      `engine/agent.py`, `.env`
  -----------------------------------------------------------------------
