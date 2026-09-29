# Multi-Agent Corporate Assistant

Прототип корпоративной мультиагентной системы для работы с внутренними
документами через локальные LLM, RAG и специализированных агентов.

Текущая версия соответствует демонстрационному состоянию проекта
(`v0.0-demo`). Следующая цель --- стабилизация `v0.1-pilot` для
ограниченного пилота на некритичных документах.

## Что уже умеет система

-   регистрация и вход пользователей через отдельный Auth Service;
-   JWT access/refresh tokens;
-   Qt desktop-клиент;
-   защищённые Bearer-токеном запросы к основному Backend API;
-   создание, изменение, удаление и запуск специализированных агентов;
-   Handler, который преобразует пользовательские запросы в действия
    системы или отвечает на вопросы о системе;
-   загрузка документов через GUI/API;
-   автоматическая обработка и маршрутизация документов;
-   создание/выбор агента для документа;
-   локальный RAG для памяти каждого агента;
-   embeddings + reranking;
-   обработка изображений технических документов и схем;
-   локальный inference через внешний `llama.cpp` server;
-   логирование и базовые метрики.

## Архитектура верхнего уровня

``` text
Qt Desktop Client
       |
       +------> Auth Service ------> PostgreSQL
       |
       +------> Multi-Agent Backend
                         |
                         +--> Handler
                         +--> Agent Registry / Executor
                         +--> Document Pipeline
                         +--> Semantic Routing
                         +--> RAG
                         +--> Drawing/Vision Pipeline
                         |
                         +------> llama.cpp server
```

Подробности: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Структура репозитория

``` text
.
├── auth_service/        # отдельный сервис авторизации
├── backend/             # основной Multi-Agent Backend
├── gui_qt/              # desktop-клиент Qt/C++
├── Docs/                # тестовые документы
├── models/              # локальные модели; не хранятся в Git
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

Подробное назначение директорий и ключевых файлов:
[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Основные сервисы

  -------------------------------------------------------------------------
  Сервис                  Адрес по умолчанию        Назначение
  ----------------------- ------------------------- -----------------------
  Auth Service            `http://127.0.0.1:8080`   пользователи, login,
                                                    refresh, logout

  Multi-Agent Backend     `http://127.0.0.1:8000`   агенты, Handler,
                                                    документы, RAG

  llama.cpp               `http://127.0.0.1:8081`   LLM inference
                          на host                   

  PostgreSQL              `localhost:5432`          данные Auth Service
  -------------------------------------------------------------------------

Backend из Docker обращается к llama.cpp через
`http://host.docker.internal:8081`.

## Быстрый запуск

### 1. Подготовить конфигурацию

Скопировать:

``` powershell
Copy-Item .env.example .env
```

Сгенерировать JWT secret:

``` powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Записать значение в `JWT_SECRET_KEY` файла `.env`.

Не коммитить `.env`.

### 2. Подготовить локальные модели

Каталог `models/` намеренно не хранится в Git.

Текущая конфигурация ожидает как минимум локальные модели для:

-   embeddings (`bge-m3`);
-   reranker (`reranker`);
-   complexity router, если он включён;
-   legacy/local Transformers paths, если выбран соответствующий
    provider.

Основной Handler и агенты могут работать через внешний `llama.cpp`
server согласно `LLAMACPP_*` в `.env`.

### 3. Запустить llama.cpp

Текущая конфигурация Backend ожидает OpenAI-compatible API на порту
`8081`.

Пример для текущего Qwen3 runtime:

``` powershell
llama-server `
    -hf Qwen/Qwen3-4B-GGUF:Q4_K_M `
    --host 0.0.0.0 `
    --port 8081 `
    -c 8192
```

Проверка:

``` powershell
Invoke-WebRequest http://127.0.0.1:8081/health
```

### 4. Запустить Docker-сервисы

``` powershell
docker compose up --build
```

После запуска:

-   Auth Service: `http://127.0.0.1:8080`
-   Auth Swagger: `http://127.0.0.1:8080/docs`
-   Backend: `http://127.0.0.1:8000`
-   Backend Swagger: `http://127.0.0.1:8000/docs`

### 5. Собрать Qt-клиент

Из `gui_qt/`:

``` bat
cmake -S . -B build ^
  -G "Visual Studio 17 2022" ^
  -A x64 ^
  -DCMAKE_PREFIX_PATH="<PATH_TO_QT>"

cmake --build build --config Release
```

Для Windows deployment Qt DLL может потребоваться `windeployqt`.

Подробнее: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Основной пользовательский сценарий

1.  Пользователь запускает Qt-клиент.
2.  Регистрируется или входит.
3.  Qt получает access/refresh tokens.
4.  Пользователь загружает документ.
5.  Backend сохраняет upload и запускает document pipeline.
6.  Документ анализируется и маршрутизируется.
7.  Система выбирает существующего агента или формирует предложение
    нового.
8.  Содержимое индексируется в памяти/RAG агента.
9.  Пользователь задаёт вопрос через Handler или конкретному агенту.
10. Агент извлекает релевантные chunks, выполняет reranking и формирует
    ответ через LLM.

## Важные ограничения текущей версии

Это демонстрационный прототип, а не production-ready система.

В частности:

-   `models/` распространяется отдельно от Git;
-   runtime-данные `backend/server_storage/` не должны считаться частью
    исходного кода;
-   конфигурация содержит legacy-пути для Transformers/Qwen2.5 наряду с
    новым llama.cpp runtime;
-   обработка недоступного inference server требует дальнейшей
    унификации ошибок;
-   полноценная ACL-фильтрация RAG ещё не является границей
    безопасности;
-   первый пилот следует проводить только на некритичных документах;
-   deployment и health/readiness проверки ещё требуют стабилизации.

## Документация

-   [Architecture](ARCHITECTURE.md)
-   [Project structure](PROJECT_STRUCTURE.md)
-   [Development](DEVELOPMENT.md)
-   [Roadmap](ROADMAP.md)
