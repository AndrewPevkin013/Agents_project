from typing import Any, Dict, List


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, instance: Any, metadata: Dict[str, Any]) -> None:
        if not name:
            raise ValueError("Agent name must not be empty")
        if name in self._agents:
            raise ValueError(f"Agent already registered: {name}")
        self._agents[name] = {"instance": instance, "metadata": metadata}

    def get(self, name: str) -> Any:
        try:
            return self._agents[name]["instance"]
        except KeyError as exc:
            available = ", ".join(self._agents.keys()) or "none"
            raise ValueError(f"Agent not found: {name}. Available agents: {available}") from exc

    def get_metadata(self, name: str) -> Dict[str, Any]:
        try:
            return self._agents[name]["metadata"]
        except KeyError as exc:
            raise ValueError(f"Agent metadata not found: {name}") from exc

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: data["metadata"]
            for name, data in self._agents.items()
        }
