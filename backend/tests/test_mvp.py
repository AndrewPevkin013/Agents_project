from pathlib import Path

from backend.app.engine.agent_executor import AgentExecutor
from backend.app.engine.agent_registry import AgentRegistry


def test_create_and_run_agent(tmp_path: Path):
    config = tmp_path / "agents.json"
    registry = AgentRegistry(config)
    registry.load()

    executor = AgentExecutor(registry)

    result = executor.execute({
        "action": "create_agent",
        "agent": "SecurityAgent",
        "system_prompt": "Ты security-agent",
        "description": "Security",
        "tags": ["security"]
    })

    assert result["status"] == "ok"
    assert "SecurityAgent" in registry.list_agents()

    answer = executor.execute({
        "type": "agent_call",
        "agent": "SecurityAgent",
        "payload": {"prompt": "Проверь API"}
    })

    assert answer["status"] == "ok"
    assert answer["agent"] == "SecurityAgent"


def test_extract(tmp_path: Path):
    config = tmp_path / "agents.json"
    registry = AgentRegistry(config)
    registry.load()
    registry.upsert_from_metadata({
        "name": "BackendAgent",
        "system_prompt": "Backend",
        "description": "Backend",
        "tags": ["backend"]
    })

    executor = AgentExecutor(registry)
    result = executor.execute({
        "action": "extract",
        "agents": ["BackendAgent"],
        "prompts": {"BackendAgent": "Сделай API"}
    })

    assert result["action"] == "extract"
    assert "BackendAgent" in result["answers"]