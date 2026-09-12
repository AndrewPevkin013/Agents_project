from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.engine.agent import LLMAgent
from app.models.model_registry import ModelRegistry


class AgentRegistry:
    def __init__(
        self,
        config_path: str | Path,
        models_dir: str | Path,
    ) -> None:
        self.config_path = Path(config_path)
        self.models_dir = Path(models_dir)

        self.model_registry = ModelRegistry(
            models_dir=self.models_dir,
            policy_path=(
                self.config_path.parent
                / "model_policy.json"
            ),
        )

        self._agents: Dict[
            str,
            Dict[str, Any],
        ] = {}

    def load(self) -> None:
        if not self.config_path.exists():
            self.config_path.write_text(
                json.dumps(
                    {"agents": []},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        config = json.loads(
            self.config_path.read_text(
                encoding="utf-8"
            )
        )

        self._agents.clear()

        for metadata in config.get("agents", []):
            self.register_from_metadata(
                metadata,
                persist=False,
            )

    def save(self) -> None:
        data = {
            "agents": [
                item["metadata"]
                for item in self._agents.values()
            ]
        }

        self.config_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _resolve_model(
        self,
        *,
        model_name: str,
        model_path: str,
    ) -> tuple[str, str, str]:
        selection = self.model_registry.resolve(
            model_name=model_name,
            model_path=model_path,
        )

        if selection is not None:
            return (
                selection.name,
                selection.path,
                selection.source,
            )

        # Keep an explicitly requested model reference even if that model
        # is not present on this machine. This preserves portable agents.json
        # files and lets LLMAgent return a clear runtime error later.
        if model_path:
            path = Path(model_path)
            if not path.is_absolute():
                path = self.models_dir / path

            return (
                model_name or path.name,
                str(path),
                "explicit_unavailable",
            )

        if model_name:
            return (
                model_name,
                str(self.models_dir / model_name),
                "explicit_unavailable",
            )

        return "", "", "unassigned"

    def _normalize_metadata(
        self,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = (
            metadata.get("name")
            or metadata.get("agent")
        )

        if not name:
            raise ValueError(
                "Agent metadata must contain "
                "'name' or 'agent'"
            )

        agent_type = metadata.get(
            "type",
            "llm",
        )

        if agent_type != "llm":
            raise ValueError(
                f"Unsupported agent type: {agent_type}. "
                "Only 'llm' agents are supported."
            )

        normalized: Dict[str, Any] = {
            "name": name,
            "type": "llm",
            "description": metadata.get(
                "description",
                "",
            ),
            "system_prompt": metadata.get(
                "system_prompt",
                "",
            ),
            "tags": list(
                metadata.get("tags", [])
            ),
        }

        requested_model_name = (
            metadata.get("model_name")
            or ""
        )
        requested_model_path = (
            metadata.get("model_path")
            or ""
        )

        (
            model_name,
            model_path,
            assignment_source,
        ) = self._resolve_model(
            model_name=requested_model_name,
            model_path=requested_model_path,
        )

        normalized["model_name"] = model_name
        normalized["model_path"] = model_path
        normalized["model_assignment"] = (
            assignment_source
        )

        normalized["generation"] = metadata.get(
            "generation",
            {
                "max_new_tokens": 256,
                "temperature": 0.7,
                "do_sample": True,
            },
        )

        normalized["device"] = metadata.get(
            "device",
            "auto",
        )

        normalized["torch_dtype"] = metadata.get(
            "torch_dtype",
            "float16",
        )

        return normalized

    def _create_instance(
        self,
        metadata: Dict[str, Any],
    ) -> Any:
        return LLMAgent(metadata)

    def register_from_metadata(
        self,
        metadata: Dict[str, Any],
        persist: bool = True,
    ) -> None:
        normalized = self._normalize_metadata(
            metadata
        )
        name = normalized["name"]

        if name in self._agents:
            raise ValueError(
                f"Agent already exists: {name}"
            )

        self._agents[name] = {
            "instance":
                self._create_instance(normalized),
            "metadata":
                normalized,
        }

        if persist:
            self.save()

    def upsert_from_metadata(
        self,
        metadata: Dict[str, Any],
    ) -> None:
        normalized = self._normalize_metadata(
            metadata
        )
        name = normalized["name"]

        if name in self._agents:
            self.unregister(
                name,
                persist=False,
            )

        self._agents[name] = {
            "instance":
                self._create_instance(normalized),
            "metadata":
                normalized,
        }

        self.save()

    def update_metadata(
        self,
        name: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        old = self.get_metadata(name)

        filtered = {
            key: value
            for key, value in updates.items()
            if value not in (None, "")
        }

        self.upsert_from_metadata(
            {
                **old,
                **filtered,
            }
        )

        return self.get_metadata(name)

    def unregister(
        self,
        name: str,
        persist: bool = True,
    ) -> None:
        if name not in self._agents:
            raise ValueError(
                f"Agent not found: {name}"
            )

        del self._agents[name]

        if persist:
            self.save()

    def get(self, name: str) -> Any:
        if name not in self._agents:
            available = (
                ", ".join(self._agents.keys())
                or "none"
            )
            raise ValueError(
                f"Agent not found: {name}. "
                f"Available agents: {available}"
            )

        return self._agents[name]["instance"]

    def get_metadata(
        self,
        name: str,
    ) -> Dict[str, Any]:
        if name not in self._agents:
            raise ValueError(
                f"Agent not found: {name}"
            )

        return self._agents[name]["metadata"]

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def snapshot(
        self,
    ) -> Dict[str, Dict[str, Any]]:
        return {
            name: data["metadata"]
            for name, data in self._agents.items()
        }

    def as_prompt_registry(
        self,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "agents":
                list(self.snapshot().values())
        }

    def available_models(
        self,
    ) -> List[Dict[str, str]]:
        return [
            {
                "name": item.name,
                "path": item.path,
            }
            for item in self.model_registry.discover()
        ]

    def select_agent(
        self,
        task: str,
    ) -> Optional[str]:
        if not self._agents:
            return None

        task_lower = task.lower()
        best_name = None
        best_score = -1

        for name, data in self._agents.items():
            metadata = data["metadata"]

            searchable = " ".join(
                [
                    name,
                    metadata.get(
                        "description",
                        "",
                    ),
                    metadata.get(
                        "system_prompt",
                        "",
                    ),
                    " ".join(
                        metadata.get(
                            "tags",
                            [],
                        )
                    ),
                ]
            ).lower()

            score = sum(
                1
                for word in task_lower.split()
                if word in searchable
            )

            if score > best_score:
                best_score = score
                best_name = name

        return best_name
