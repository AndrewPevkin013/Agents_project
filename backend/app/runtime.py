from __future__ import annotations

from dataclasses import dataclass

from app.engine.agent_executor import AgentExecutor
from app.engine.agent_registry import AgentRegistry
from app.engine.command_router import CommandRouter
from app.engine.command_store import CommandStore


@dataclass(slots=True)
class ApplicationRuntime:
    registry: AgentRegistry
    command_store: CommandStore
    executor: AgentExecutor
    router: CommandRouter