from typing import Any, Dict, List, Optional


class MockAgent:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.name = metadata["name"]
        self.description = metadata.get("description", "")
        self.system_prompt = metadata.get("system_prompt", "")
        self.tags = metadata.get("tags", [])

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            payload.get("prompt")
            or payload.get("task")
            or payload.get("query")
            or ""
        )

        return {
            "agent": self.name,
            "status": "ok",
            "role": self.system_prompt,
            "result": f"[{self.name}] получил задачу: {prompt}"
        }


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}

    def register_from_metadata(self, metadata: Dict[str, Any]) -> None:
        name = metadata["name"]

        if name in self._agents:
            raise ValueError(f"Agent already registered: {name}")

        agent = MockAgent(metadata)

        self._agents[name] = {
            "instance": agent,
            "metadata": metadata
        }

    def unregister(self, name: str) -> None:
        if name not in self._agents:
            raise ValueError(f"Agent not found: {name}")

        del self._agents[name]

    def get(self, name: str) -> Any:
        if name not in self._agents:
            available = ", ".join(self._agents.keys()) or "none"
            raise ValueError(f"Agent not found: {name}. Available: {available}")

        return self._agents[name]["instance"]

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: data["metadata"]
            for name, data in self._agents.items()
        }

    def select_agent(self, task: str) -> Optional[str]:
        task_lower = task.lower()

        for name, data in self._agents.items():
            metadata = data["metadata"]
            searchable = " ".join([
                name,
                metadata.get("description", ""),
                " ".join(metadata.get("tags", []))
            ]).lower()

            for word in task_lower.split():
                if word in searchable:
                    return name

        return next(iter(self._agents.keys()), None)