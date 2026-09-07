from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.engine.agent_executor import AgentExecutor
from app.engine.response_compiler import ResponseCompiler
from app.handlers.base import HandlerOutput


class CommandRouter:
    def __init__(self, executor: AgentExecutor, handler=None) -> None:
        self.executor = executor
        self.handler = handler

    def route(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return self.executor.execute(command)

    def route_many(
        self,
        commands: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.executor.execute_many(commands)

    def route_file(
        self,
        command_path: str | Path,
    ) -> Dict[str, Any]:
        with Path(command_path).open(
            "r",
            encoding="utf-8",
        ) as file:
            return self.route(json.load(file))

    def route_by_agent_name(
        self,
        agent_name: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.route({
            "type": "agent_call",
            "agent": agent_name,
            "payload": payload,
        })

    def handle_user_request(
        self,
        user_request: str,
    ) -> Dict[str, Any]:
        if self.handler is None:
            raise RuntimeError("Handler is not configured")

        handler_output: HandlerOutput = self.handler.handle(
            user_request
        )

        if isinstance(handler_output, str):
            return {
                "user_request": user_request,
                "mode": "system_qa",
                "commands": [],
                "engine_response": [],
                "final_answer": handler_output,
            }

        commands = handler_output
        engine_response = self.route_many(commands)

        return {
            "user_request": user_request,
            "mode": "command",
            "commands": commands,
            "engine_response": engine_response,
            "final_answer": ResponseCompiler.compile(
                commands,
                engine_response,
            ),
        }