from __future__ import annotations

from typing import Any, Dict

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.base import BaseHandler, HandlerOutput
from app.handlers.output_parser import parse_handler_output
from app.handlers.prompt import build_handler_system_prompt


class GigaChatHandler(BaseHandler):
    def __init__(
        self,
        registry: AgentRegistry,
        command_store: CommandStore,
        config: Dict[str, Any],
    ) -> None:

        self.registry = registry
        self.command_store = command_store

        self.model = config.get(
            "model",
            "GigaChat-2-Pro"
        )

        self.client = None

    def _ensure_client(self) -> None:
        if self.client is not None:
            return

        from gigachat import GigaChat

        self.client = GigaChat(
            model=self.model
        )

    def _build_system_prompt(
        self,
        user_request: str,
    ) -> str:

        return build_handler_system_prompt(
            user_request,
            self.registry.as_prompt_registry(),
            self.command_store.retrieve,
        )

    def handle(
        self,
        user_request: str,
    ) -> HandlerOutput:

        self._ensure_client()

        system_prompt = (
            self._build_system_prompt(
                user_request
            )
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_request,
            },
        ]

        response = self.client.chat(
            {
                "messages": messages,
                "model": self.model,
            }
        )

        answer = (
            response.choices[0]
            .message.content
            .strip()
        )

        print("GIGACHAT HANDLER raw answer:")
        print(answer)

        return parse_handler_output(answer)