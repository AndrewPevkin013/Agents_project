from pathlib import Path
from engine.agent_executor import AgentExecutor
from engine.agent_registry import AgentRegistry


def test_create_and_run_mock_agent(tmp_path: Path):
    registry = AgentRegistry(tmp_path / "agents.json", tmp_path / "Models")
    registry.load()
    executor = AgentExecutor(registry)
    result = executor.execute({"action": "create_agent", "agent": "SecurityAgent", "type": "mock", "system_prompt": "Ты security-агент.", "tags": ["security"]})
    assert result["status"] == "ok"
    run_result = executor.execute({"type": "agent_call", "agent": "SecurityAgent", "payload": {"prompt": "Проверь API"}})
    assert run_result["status"] == "ok"


def test_document_router_generates_load(tmp_path: Path):
    registry = AgentRegistry(tmp_path / "agents.json", tmp_path / "Models")
    registry.load()
    registry.upsert_from_metadata({"name": "BackendAgent", "type": "mock", "system_prompt": "Ты backend agent", "tags": ["backend", "api"]})
    executor = AgentExecutor(registry)
    result = executor.execute({"action": "route_document", "file_path": "docs/api_report.txt", "document_text": "REST API endpoint database auth", "threshold": 1})
    assert result["status"] == "ok"
    assert result["generated_commands"][0]["action"] == "load"
