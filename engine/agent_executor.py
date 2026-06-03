from typing import Any, Dict

from engine.agent_registry import AgentRegistry


class AgentExecutor:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        command_type = command.get("type")

        if command_type != "agent_call":
            raise ValueError(f"Unsupported command type: {command_type}")

        agent_name = command.get("agent")
        if not agent_name:
            raise ValueError("Command must contain 'agent'")

        payload = command.get("payload", {})
        if not isinstance(payload, dict):
            raise TypeError("Command payload must be a JSON object")

        agent = self.registry.get(agent_name)
        return agent.run(payload)
