from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ModelSelection:
    name: str
    path: str
    source: str


class ModelRegistry:
    """
    Discovers local generative (causal-LM) model folders and resolves which
    base model should be assigned to a newly created agent.

    Selection priority:
      1. explicit model_path
      2. explicit model_name
      3. DEFAULT_AGENT_MODEL environment variable
      4. model_policy.json -> default_model
      5. model_policy.json -> preferred_models (first available)
      6. first discovered causal-LM model, deterministically sorted

    If no usable local model exists, resolve() returns None. This keeps the
    backend bootable on machines that do not have the large agent model files.
    """

    def __init__(
        self,
        models_dir: str | Path,
        policy_path: str | Path | None = None,
    ) -> None:
        self.models_dir = Path(models_dir)
        self.policy_path = Path(policy_path) if policy_path else None
        self._policy = self._load_policy()

    def _load_policy(self) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "default_model": "",
            "preferred_models": [],
            "excluded_directories": [
                "complexity_router",
                "bge-m3",
                "bge-reranker-v2-m3",
                "routing",
            ],
            "scan_depth": 2,
        }

        if self.policy_path is None or not self.policy_path.exists():
            return defaults

        try:
            data = json.loads(
                self.policy_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return defaults

        return {**defaults, **data}

    def refresh_policy(self) -> None:
        self._policy = self._load_policy()

    def _is_excluded(self, model_dir: Path) -> bool:
        excluded = {
            str(item).lower()
            for item in self._policy.get(
                "excluded_directories",
                [],
            )
        }

        try:
            relative_parts = model_dir.relative_to(
                self.models_dir
            ).parts
        except ValueError:
            relative_parts = model_dir.parts

        lowered = {part.lower() for part in relative_parts}
        return bool(lowered & excluded)

    @staticmethod
    def _has_model_weights(model_dir: Path) -> bool:
        patterns = (
            "*.safetensors",
            "*.bin",
            "*.pt",
            "*.pth",
        )

        for pattern in patterns:
            if any(model_dir.glob(pattern)):
                return True

        return (
            (model_dir / "model.safetensors.index.json").exists()
            or (model_dir / "pytorch_model.bin.index.json").exists()
        )

    @staticmethod
    def _looks_like_causal_lm(config: Dict[str, Any]) -> bool:
        architectures = config.get("architectures") or []

        if any(
            "causallm" in str(item).lower()
            for item in architectures
        ):
            return True

        auto_map = config.get("auto_map") or {}
        if "AutoModelForCausalLM" in auto_map:
            return True

        return False

    def _candidate_from_dir(
        self,
        model_dir: Path,
    ) -> Optional[ModelSelection]:
        if self._is_excluded(model_dir):
            return None

        config_path = model_dir / "config.json"
        if not config_path.exists():
            return None

        try:
            config = json.loads(
                config_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return None

        if not self._looks_like_causal_lm(config):
            return None

        if not self._has_model_weights(model_dir):
            return None

        return ModelSelection(
            name=model_dir.name,
            path=str(model_dir.resolve()),
            source="discovered",
        )

    def discover(self) -> List[ModelSelection]:
        if not self.models_dir.exists():
            return []

        depth_limit = int(
            self._policy.get("scan_depth", 2)
        )

        candidates: Dict[str, ModelSelection] = {}

        for config_path in self.models_dir.rglob("config.json"):
            model_dir = config_path.parent

            try:
                relative = model_dir.relative_to(
                    self.models_dir
                )
            except ValueError:
                continue

            if len(relative.parts) > depth_limit:
                continue

            candidate = self._candidate_from_dir(model_dir)
            if candidate is None:
                continue

            candidates[candidate.path] = candidate

        return sorted(
            candidates.values(),
            key=lambda item: (
                item.name.lower(),
                item.path.lower(),
            ),
        )

    def _resolve_explicit_path(
        self,
        model_path: str,
    ) -> Optional[ModelSelection]:
        path = Path(model_path).expanduser()

        if not path.is_absolute():
            path = self.models_dir / path

        candidate = self._candidate_from_dir(path)
        if candidate is None:
            return None

        return ModelSelection(
            name=candidate.name,
            path=candidate.path,
            source="explicit_path",
        )

    def _find_by_name(
        self,
        model_name: str,
        candidates: List[ModelSelection],
    ) -> Optional[ModelSelection]:
        target = model_name.strip().lower()

        for candidate in candidates:
            if candidate.name.lower() == target:
                return candidate

        direct = self.models_dir / model_name
        candidate = self._candidate_from_dir(direct)

        if candidate is not None:
            return candidate

        return None

    def resolve(
        self,
        *,
        model_name: str = "",
        model_path: str = "",
    ) -> Optional[ModelSelection]:
        candidates = self.discover()

        if model_path:
            explicit = self._resolve_explicit_path(model_path)
            if explicit is not None:
                return explicit

        if model_name:
            explicit_name = self._find_by_name(
                model_name,
                candidates,
            )
            if explicit_name is not None:
                return ModelSelection(
                    name=explicit_name.name,
                    path=explicit_name.path,
                    source="explicit_name",
                )

        env_default = os.getenv(
            "DEFAULT_AGENT_MODEL",
            "",
        ).strip()

        if env_default:
            selected = self._find_by_name(
                env_default,
                candidates,
            )
            if selected is not None:
                return ModelSelection(
                    name=selected.name,
                    path=selected.path,
                    source="env_default",
                )

        configured_default = str(
            self._policy.get("default_model", "")
        ).strip()

        if configured_default:
            selected = self._find_by_name(
                configured_default,
                candidates,
            )
            if selected is not None:
                return ModelSelection(
                    name=selected.name,
                    path=selected.path,
                    source="policy_default",
                )

        for preferred in self._policy.get(
            "preferred_models",
            [],
        ):
            selected = self._find_by_name(
                str(preferred),
                candidates,
            )
            if selected is not None:
                return ModelSelection(
                    name=selected.name,
                    path=selected.path,
                    source="policy_preferred",
                )

        if candidates:
            selected = candidates[0]
            return ModelSelection(
                name=selected.name,
                path=selected.path,
                source="auto_discovered",
            )

        return None
