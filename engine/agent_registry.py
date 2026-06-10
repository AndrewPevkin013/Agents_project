from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.agent import MockAgent


class AgentRegistry:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self._agents: Dict[str, Dict[str, Any]] = {}

    def load(self) -> None:
        if not self.config_path.exists():
            self.config_path.write_text(
                json.dumps({"agents": []}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        config = json.loads(self.config_path.read_text(encoding="utf-8"))

        self._agents.clear()
        for metadata in config.get("agents", []):
            self.register_from_metadata(metadata, persist=False)

    def save(self) -> None:
        data = {
            "agents": [
                item["metadata"]
                for item in self._agents.values()
            ]
        }
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def register_from_metadata(self, metadata: Dict[str, Any], persist: bool = True) -> None:
        name = metadata.get("name")
        if not name:
            raise ValueError("Agent metadata must contain 'name'")

        if name in self._agents:
            raise ValueError(f"Agent already exists: {name}")

        normalized = {
            "name": name,
            "description": metadata.get("description", ""),
            "system_prompt": metadata.get("system_prompt", ""),
            "tags": list(metadata.get("tags", [])),
        }

        self._agents[name] = {
            "instance": MockAgent(normalized),
            "metadata": normalized,
        }

        if persist:
            self.save()

    def upsert_from_metadata(self, metadata: Dict[str, Any]) -> None:
        name = metadata.get("name")
        if not name:
            raise ValueError("Agent metadata must contain 'name'")

        if name in self._agents:
            self.unregister(name, persist=False)

        self.register_from_metadata(metadata, persist=True)

    def unregister(self, name: str, persist: bool = True) -> None:
        if name not in self._agents:
            raise ValueError(f"Agent not found: {name}")

        del self._agents[name]

        if persist:
            self.save()

    def get(self, name: str) -> MockAgent:
        if name not in self._agents:
            available = ", ".join(self._agents.keys()) or "none"
            raise ValueError(f"Agent not found: {name}. Available agents: {available}")

        return self._agents[name]["instance"]

    def get_metadata(self, name: str) -> Dict[str, Any]:
        if name not in self._agents:
            raise ValueError(f"Agent not found: {name}")
        return self._agents[name]["metadata"]

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: data["metadata"]
            for name, data in self._agents.items()
        }

    def select_agent(self, task: str) -> Optional[str]:
        if not self._agents:
            return None

        task_lower = task.lower()
        best_name = None
        best_score = -1

        for name, data in self._agents.items():
            metadata = data["metadata"]
            searchable = " ".join([
                name,
                metadata.get("description", ""),
                metadata.get("system_prompt", ""),
                " ".join(metadata.get("tags", [])),
            ]).lower()

            score = 0
            for word in task_lower.split():
                if word in searchable:
                    score += 1

            if score > best_score:
                best_score = score
                best_name = name

        return best_name