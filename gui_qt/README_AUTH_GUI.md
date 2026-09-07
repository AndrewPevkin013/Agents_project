# Qt GUI + Auth Service integration

## Что добавлено

При запуске приложение теперь сначала показывает `LoginDialog`.

Можно:
- войти по username или email;
- открыть `RegisterDialog`;
- зарегистрировать пользователя через `POST /auth/register`;
- получить access/refresh tokens;
- после входа открыть основной Multi-Agent Chat;
- передавать access token как `Authorization: Bearer ...` во все запросы Agent API;
- выйти через `Logout` в верхней панели;
- при logout вызвать `POST /auth/logout`.

Также удалена дублирующая кнопка Settings из левой панели. Настройки остаются в верхней панели.

## Сервисы

Auth Service:
`http://127.0.0.1:8080`

Agent Service:
`http://127.0.0.1:8000`

Auth URL можно изменить прямо в окне входа.
Agent Service URL меняется в Settings основного окна.

## Сборка

```bat
rmdir /s /q build

cmake -S . -B build ^
  -G "Visual Studio 17 2022" ^
  -A x64 ^
  -DCMAKE_PREFIX_PATH="D:/Programming/Qt/6.6.1/msvc2019_64"

cmake --build build --config Release
```

## Тест

1. Поднять auth_service на `:8080`.
2. Поднять Agents_project API на `:8000`.
3. Запустить `MultiAgentChat.exe`.
4. Нажать Create account.
5. Зарегистрировать нового пользователя.
6. Основной чат должен открыться автоматически.
7. Закрыть приложение и запустить снова.
8. Войти созданным username/password.
9. Проверить Handler.
10. Нажать Logout и убедиться, что снова появляется Login.

## Важно

Текущий Agent Service может ещё не проверять JWT на серверной стороне.
Qt уже добавляет Bearer token к запросам, но для реальной защиты нужно следующим шагом добавить проверку JWT в FastAPI Agent Service.
