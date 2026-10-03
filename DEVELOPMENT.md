# Development Guide

## 1. Предварительные требования

Для текущего Windows-oriented development setup потребуются:

-   Git;
-   Docker Desktop / Docker Compose;
-   Python при локальном запуске отдельных компонентов;
-   llama.cpp с `llama-server`;
-   CMake;
-   Visual Studio C++ toolchain;
-   Qt 6 с компонентами Core, Widgets, Network;
-   локальные model assets.

Точные версии окружения пока не зафиксированы единым lockfile для всей
системы. Backend Dockerfile использует Python 3.12.

## 2. Clone и environment

``` powershell
git clone <repository>
cd Agents_project
Copy-Item .env.example .env
```


Сгенерировать JWT secret:

``` powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Записать результат:

``` text
JWT_SECRET_KEY=<generated value>
```

`.env` не коммитить.

## 3. Модели

`/models` исключён из Git.

Текущий `.env.example` ожидает:

``` text
EMBEDDING_MODEL_PATH=/project/models/bge-m3
RERANKER_MODEL_PATH=/project/models/reranker
COMPLEXITY_ROUTER_PATH=/project/models/complexity_router
```

Если `COMPLEXITY_ROUTER_ENABLED=true`, его model assets также должны
присутствовать.

Legacy/local Transformers configuration всё ещё присутствует для
Handler/agents/agent proposer. Перед запуском конкретного сценария
проверяйте выбранные providers.

## 4. llama.cpp

Текущая основная конфигурация:

``` text
HANDLER_PROVIDER=llamacpp
AGENT_INFERENCE_PROVIDER=llamacpp

LLAMACPP_BASE_URL=http://host.docker.internal:8081
LLAMACPP_MODEL=Qwen3-4B
LLAMACPP_MAX_NEW_TOKENS=128
LLAMACPP_TEMPERATURE=0.0
LLAMACPP_TIMEOUT=120
```

Пример запуска текущего Qwen3 runtime:

``` powershell
llama-server `
    -hf Qwen/Qwen3-4B-GGUF:Q4_K_M `
    --host 0.0.0.0 `
    --port 8081 `
    -c 8192
```

Проверка с host:

``` powershell
Invoke-WebRequest http://127.0.0.1:8081/health
```

Проверка из backend container после запуска Compose:

``` powershell
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8081/health').read().decode())"
```

Если эта команда не работает, Handler/agents с llama.cpp provider также
не смогут выполнить inference.

## 5. Docker stack

Запуск:

``` powershell
docker compose up --build
```

В фоне:

``` powershell
docker compose up -d --build
```

Статус:

``` powershell
docker compose ps
```

Логи:

``` powershell
docker compose logs -f backend
docker compose logs -f auth-service
docker compose logs -f postgres
```

Остановка:

``` powershell
docker compose down
```

Не использовать `docker compose down -v`, если нужно сохранить Auth
PostgreSQL volume.

## 6. Проверка сервисов

Auth:

``` powershell
Invoke-WebRequest http://127.0.0.1:8080/health
```

Backend:

``` powershell
Invoke-WebRequest http://127.0.0.1:8000/
```

Swagger:

``` text
http://127.0.0.1:8080/docs
http://127.0.0.1:8000/docs
```

Важно: root endpoint Backend подтверждает работу FastAPI, но пока не
является полноценным readiness check для llama.cpp, embeddings и
остальных runtime dependencies.

## 7. Auth flow

Типовой flow:

``` text
register/login
     |
     v
access token + refresh token
     |
     v
Authorization: Bearer <access token>
     |
     v
Multi-Agent Backend
```

Auth endpoints:

``` text
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
```

Access token по умолчанию:

``` text
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Refresh token:

``` text
REFRESH_TOKEN_EXPIRE_DAYS=14
```

Auth Service хранит hash refresh token, а не исходный token.

## 8. Qt build

Из `gui_qt/`.

Пример Visual Studio generator:

``` bat
rmdir /s /q build

cmake -S . -B build ^
  -G "Visual Studio 17 2022" ^
  -A x64 ^
  -DCMAKE_PREFIX_PATH="<PATH_TO_QT>"

cmake --build build --config Release
```

Путь Qt зависит от машины разработчика и не должен хардкодиться в Git.

После сборки executable находится в build tree, обычно в `Release/`.

Для переносимой Windows-сборки:

``` bat
windeployqt <path-to-MultiAgentChat.exe>
```

## 9. GUI endpoints

По умолчанию:

``` text
Auth Service:  http://127.0.0.1:8080
Agent Service: http://127.0.0.1:8000
```

Auth URL можно менять в login flow.

Agent Service URL меняется через Settings.

## 10. Smoke test после запуска

Минимальный ручной тест:

1.  Проверить `/health` Auth Service.
2.  Проверить `/` Backend.
3.  Проверить llama.cpp `/health`.
4.  Запустить Qt.
5.  Зарегистрировать тестового пользователя.
6.  Войти.
7.  Открыть основной интерфейс.
8.  Проверить запрос Handler.
9.  Загрузить небольшой тестовый документ.
10. Убедиться, что документ назначен агенту.
11. Задать вопрос по документу.
12. Проверить наличие source/RAG результата.
13. Выйти и войти снова.

## 11. Regression scenarios для demo baseline

Перед изменениями в routing/RAG/model layer рекомендуется вручную
проверять как минимум:

### Incident document

Загрузить incident document.

Ожидание: создаётся/выбирается Incident Response specialization и
документ доступен через RAG.

### Второй документ того же домена

Загрузить operations runbook близкого домена.

Ожидание: существующий подходящий агент переиспользуется, а не создаётся
лишний агент.

### Medical document

Загрузить maintenance document.

Ожидание: специализированный агент отвечает по фактам документа.

### Drawing

Загрузить тестовую block diagram.

Ожидание: drawing pipeline извлекает структурированную информацию, после
чего System Architecture specialization может отвечать по схеме.

Эти сценарии необходимо постепенно перенести из ручных проверок в
automated regression tests.

## 12. Tests

Существующие backend tests:

``` text
backend/tests/test_document_processor_smoke.py
backend/tests/test_engine.py
backend/tests/test_integrated_mvp.py
backend/tests/test_mvp.py
backend/tests/test_semantic_router.py
```

Запуск из подходящего Python environment:

``` powershell
pytest backend/tests
```

Тесты, требующие моделей или внешнего inference runtime, должны явно
отделяться от unit tests.

## 13. Runtime directories

Не коммитить:

``` text
backend/server_storage/
backend/logs/
models/
model_offload/
gui_qt/build/
gui_qt/build*/
__pycache__/
.env
```

`Docs/` --- отдельный набор тестовых fixtures и не должен смешиваться с
`server_storage`.

## 14. Config changes

Перед изменением model/runtime поведения проверять одновременно:

``` text
.env / .env.example
backend/config/core_config.json
backend/config/model_policy.json
backend/config/agents.json
```

Сейчас в проекте присутствует переходное состояние: Qwen3/llama.cpp
используется как основной inference path, но часть metadata/config всё
ещё относится к Qwen2.5/local Transformers.

Не следует исправлять только один config file и предполагать, что вся
система автоматически переключилась.

## 15. Типичные проблемы

### Backend работает, но Handler возвращает 500

Сначала проверить llama.cpp:

``` powershell
Invoke-WebRequest http://127.0.0.1:8081/health
```

Затем проверить доступ из container.

Типовая причина --- Backend запущен, а внешний inference server нет.

### Модель загружается очень долго

Проверить, какой provider реально используется.

Часть legacy paths может загрузить Transformers model в Backend process
вместо обращения к llama.cpp.

### Документ маршрутизируется неожиданно

Проверять:

``` text
documents/processor.py
documents/agent_proposer.py
engine/document_router.py
routing/semantic_router.py
```

а также текущие `agents.json`.

### После restart пропали данные

Определить тип данных:

-   users -\> PostgreSQL volume;
-   agents -\> `backend/config/agents.json`;
-   documents/RAG -\> `backend/server_storage/`.

Для `v0.1-pilot` полный destructive restart test является обязательной
задачей.

## 16. Git workflow

Рекомендуемый flow:

``` text
Issue
  -> branch
  -> implementation
  -> tests
  -> review
  -> merge
  -> pilot build
```

Не коммитить непосредственно runtime state и model weights.

Для исправлений:

``` text
fix/<short-name>
```

Для функциональности:

``` text
feature/<short-name>
```

Для инфраструктуры:

``` text
infra/<short-name>
```

## 17. Definition of Done для pilot-задачи

Минимально:

-   изменение работает в clean startup;
-   существующий demo scenario не сломан;
-   ошибки не приводят к необъяснимому crash;
-   config/documentation обновлены, если поведение изменилось;
-   secrets/runtime data не попали в commit;
-   изменения можно воспроизвести на машине второго разработчика.
