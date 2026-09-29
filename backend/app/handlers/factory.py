from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.base import BaseHandler
from app.handlers.llamacpp import LlamaCppHandler
from app.handlers.gigachat import GigaChatHandler
from app.handlers.local_llm import LocalLLMHandler
from app.handlers.rule_based import RuleBasedHandler


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_handler(registry: AgentRegistry, command_store: CommandStore, config: Dict[str, Any], models_dir: str | Path) -> BaseHandler:
    provider = os.getenv(
        "HANDLER_PROVIDER",
        config.get("handler", {}).get("provider", "rules"),
    ).strip().lower()

    providers = config.get("providers", {})

    if provider == "local":
        local_config = dict(providers.get("local", {}))
        generation = dict(local_config.get("generation", {}))

        local_config["model_name"] = os.getenv(
            "HANDLER_MODEL",
            local_config.get("model_name", "Qwen2.5-7B-Instruct"),
        )
        local_config["device"] = os.getenv(
            "HANDLER_DEVICE",
            local_config.get("device", "auto"),
        )
        local_config["torch_dtype"] = os.getenv(
            "HANDLER_TORCH_DTYPE",
            local_config.get("torch_dtype", "auto"),
        )

        if os.getenv("HANDLER_OFFLOAD_DIR"):
            local_config["offload_folder"] = os.getenv("HANDLER_OFFLOAD_DIR")

        generation["max_new_tokens"] = int(os.getenv(
            "HANDLER_MAX_NEW_TOKENS",
            generation.get("max_new_tokens", 256),
        ))
        generation["temperature"] = float(os.getenv(
            "HANDLER_TEMPERATURE",
            generation.get("temperature", 0.2),
        ))
        generation["do_sample"] = _env_bool(
            "HANDLER_DO_SAMPLE",
            bool(generation.get("do_sample", False)),
        )
        local_config["generation"] = generation

        return LocalLLMHandler(
            registry=registry,
            command_store=command_store,
            config=local_config,
            models_dir=models_dir,
        )

    if provider == "llamacpp":
        llamacpp_config = {
            "base_url": os.getenv(
                "LLAMACPP_BASE_URL",
                "http://host.docker.internal:8081",
            ),
            "model": os.getenv(
                "LLAMACPP_MODEL",
                "Qwen3-4B",
            ),
            "max_new_tokens": int(
                os.getenv(
                    "LLAMACPP_MAX_NEW_TOKENS",
                    "128",
                )
            ),
            "temperature": float(
                os.getenv(
                    "LLAMACPP_TEMPERATURE",
                    "0.0",
                )
            ),
            "timeout": float(
                os.getenv(
                    "LLAMACPP_TIMEOUT",
                    "120",
                )
            ),
        }

        return LlamaCppHandler(
            registry=registry,
            command_store=command_store,
            config=llamacpp_config,
        )

    if provider == "gigachat":
        return GigaChatHandler(
            registry=registry,
            command_store=command_store,
            config=providers.get("gigachat", {}),
        )

    if provider == "rules":
        return RuleBasedHandler(
            registry=registry,
            command_store=command_store,
        )

    raise ValueError(f"Unknown Handler provider: {provider}")
