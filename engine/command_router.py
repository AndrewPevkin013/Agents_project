from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from engine.agent_executor import AgentExecutor
from engine.handler import RuleBasedHandler


class CommandRouter:
    def __init__(self, executor: AgentExecutor, handler: RuleBasedHandler | None = None) -> None:
        self.executor = executor
        self.handler = handler

    def route(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return self.executor.execute(command)

    def route_many(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.executor.execute_many(commands)

    def route_file(self, command_path: str | Path) -> Dict[str, Any]:
        with Path(command_path).open("r", encoding="utf-8") as file:
            command = json.load(file)
        return self.route(command)

    def route_by_agent_name(self, agent_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        command = {
            "type": "agent_call",
            "agent": agent_name,
            "payload": payload
        }
        return self.route(command)

    def handle_user_request(self, user_request: str) -> Dict[str, Any]:
        if self.handler is None:
            raise RuntimeError("Handler is not configured")

        commands = self.handler.handle(user_request)
        engine_response = self.route_many(commands)

        return {
            "user_request": user_request,
            "commands": commands,
            "engine_response": engine_response,
            "final_answer": self._compile_answer(commands, engine_response)
        }

    @staticmethod
    def _compile_answer(commands: List[Dict[str, Any]], engine_response: List[Dict[str, Any]]) -> str:
        # MVP-компилятор вместо LLM compile_answer из notebook.
        if not engine_response:
            return "Команды выполнены, но ответ движка пуст."

        return "Выполнено команд: " + str(len(commands)) + ". Результат: " + json.dumps(
            engine_response,
            ensure_ascii=False
        )