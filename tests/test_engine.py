from pathlib import Path

from engine.agent_executor import AgentExecutor
from engine.agent_loader import AgentLoader
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter


BASE_DIR = Path(__file__).resolve().parents[1]


def test_engine_loads_and_executes_agent():
    registry = AgentRegistry()
    AgentLoader(BASE_DIR / "agents").load_all(registry)

    assert "AnalystAgent" in registry.list_agents()
    assert "RetrieverAgent" in registry.list_agents()

    router = CommandRouter(AgentExecutor(registry))
    result = router.route({
        "type": "agent_call",
        "agent": "AnalystAgent",
        "payload": {"task": "test", "context": {"x": 1}}
    })

    assert result["status"] == "ok"
    assert result["agent"] == "AnalystAgent"


def test_angle_command_conversion():
    command = CommandRouter.from_angle_command("<AnalystAgent, Do something>")
    assert command["type"] == "agent_call"
    assert command["agent"] == "AnalystAgent"
    assert command["payload"]["prompt"] == "Do something"
