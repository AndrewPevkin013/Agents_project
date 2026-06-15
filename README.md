# Multi-Agent MVP

MVP без реальных LLM-моделей.

## Запуск через консоль

```bash
python main.py
```

## Запуск сервиса с UI

```bash
pip install -r requirements.txt
python -m uvicorn api_server:app --reload
```

Открыть:

```text
http://127.0.0.1:8000/
```

## Ручные ссылки

Добавить агента:

```text
http://127.0.0.1:8000/link/add/SecurityAgent?role=Ты security-agent&tags=security,api
```

Запустить агента:

```text
http://127.0.0.1:8000/link/run/SecurityAgent?prompt=Проверь API авторизации
```

Удалить агента:

```text
http://127.0.0.1:8000/link/delete/SecurityAgent
```

Handler:

```text
http://127.0.0.1:8000/link/handler?request=Создай агента SecurityAgent для безопасности
```

## Тесты

```bash
pytest -q
```