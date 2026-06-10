import json
from pathlib import Path

from engine.agent_registry import AgentRegistry


class AgentLoader:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)

    def load_all(self, registry: AgentRegistry) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Agents config not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)

        for metadata in config.get("agents", []):
            registry.register_from_metadata(metadata)