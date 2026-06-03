# Agent System MVP

Minimal plugin engine for JSON-based multi-agent execution.

## Run

```bash
python main.py
```

## Test

```bash
pip install pytest
pytest -q
```

## Add a new agent

Create folder:

```text
agents/new_agent/
    agent.json
    main.py
```

`main.py` must contain a class from `agent.json.class_name` and implement:

```python
def run(self, payload: dict) -> dict:
    ...
```
