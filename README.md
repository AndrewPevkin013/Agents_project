# Multi-Agent MVP integrated update

Run console demo:

```bash
python main.py
```

Run server without reload when using local LLMs:

```bash
python -m uvicorn api_server:app
```

Open:

```text
http://127.0.0.1:8000/
```

Handler create LLM agent example:

```text
Создай агента AnalystAgent на модели Qwen2.5-3B-Instruct. Роль: аналитический агент для анализа архитектуры проекта. Теги: analysis, summary.
```

Manual link:

```text
http://127.0.0.1:8000/link/add/AnalystAgent?type=llm&model=Qwen2.5-3B-Instruct&role=Ты аналитический агент&tags=analysis,summary
```

Route document:

```text
http://127.0.0.1:8000/link/route_document?file_path=docs/api_report.txt&document_text=REST API auth database
```
