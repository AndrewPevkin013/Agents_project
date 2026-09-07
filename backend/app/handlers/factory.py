from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.base import BaseHandler
from app.handlers.gigachat import GigaChatHandler
from app.handlers.local_llm import LocalLLMHandler
from app.handlers.rule_based import RuleBasedHandler


def create_handler(
    registry: AgentRegistry,
    command_store: CommandStore,
    config: Dict[str, Any],
    models_dir: str | Path,
) -> BaseHandler:

    provider = os.getenv(
        "HANDLER_PROVIDER",
        config
        .get("handler", {})
        .get("provider", "rules")
    ).lower()

    providers = config.get(
        "providers",
        {}
    )

    if provider == "local":
        return LocalLLMHandler(
            registry=registry,
            command_store=command_store,
            config=providers.get(
                "local",
                {}
            ),
            models_dir=models_dir,
        )

    if provider == "gigachat":
        return GigaChatHandler(
            registry=registry,
            command_store=command_store,
            config=providers.get(
                "gigachat",
                {}
            ),
        )

    if provider == "rules":
        return RuleBasedHandler(
            registry=registry,
            command_store=command_store,
        )

    raise ValueError(
        f"Unknown Handler provider: {provider}"
    )