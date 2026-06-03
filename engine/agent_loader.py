import importlib.util
import json
from pathlib import Path
from types import ModuleType

from engine.agent_registry import AgentRegistry


class AgentLoader:
    def __init__(self, agents_dir: str | Path) -> None:
        self.agents_dir = Path(agents_dir)

    def load_all(self, registry: AgentRegistry) -> None:
        if not self.agents_dir.exists():
            raise FileNotFoundError(f"Agents directory not found: {self.agents_dir}")

        for agent_dir in sorted(self.agents_dir.iterdir()):
            if agent_dir.is_dir():
                self._load_one(agent_dir, registry)

    def _load_one(self, agent_dir: Path, registry: AgentRegistry) -> None:
        config_path = agent_dir / "agent.json"
        if not config_path.exists():
            return

        with config_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)

        required_fields = ["name", "entrypoint", "class_name"]
        missing = [field for field in required_fields if field not in metadata]
        if missing:
            raise ValueError(f"Invalid agent config {config_path}. Missing: {missing}")

        module_path = agent_dir / metadata["entrypoint"]
        module = self._load_module(metadata["name"], module_path)

        try:
            agent_class = getattr(module, metadata["class_name"])
        except AttributeError as exc:
            raise ValueError(
                f"Class {metadata['class_name']} not found in {module_path}"
            ) from exc

        agent_instance = agent_class()

        if not hasattr(agent_instance, "run"):
            raise TypeError(f"Agent {metadata['name']} must implement run(payload)")

        registry.register(metadata["name"], agent_instance, metadata)

    @staticmethod
    def _load_module(module_name: str, module_path: Path) -> ModuleType:
        if not module_path.exists():
            raise FileNotFoundError(f"Agent entrypoint not found: {module_path}")

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
