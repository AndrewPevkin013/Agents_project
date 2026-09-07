from __future__ import annotations

import re
from typing import List

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.base import BaseHandler, HandlerOutput


class RuleBasedHandler(BaseHandler):
    def __init__(
        self,
        registry: AgentRegistry,
        command_store: CommandStore,
    ) -> None:

        self.registry = registry
        self.command_store = command_store

    def handle(
        self,
        user_request: str,
    ) -> HandlerOutput:

        text = user_request.strip()
        lower = text.lower()

        if any(
            x in lower
            for x in [
                "какие агенты",
                "список агентов",
                "list agents",
                "what agents",
            ]
        ):
            return (
                "Доступные агенты: "
                + ", ".join(
                    self.registry.list_agents()
                )
                + ". Можно запустить агента "
                  "или создать нового."
            )

        if any(
            x in lower
            for x in [
                "какие команды",
                "список команд",
                "list commands",
                "what commands",
            ]
        ):
            return (
                "Доступные команды: "
                + ", ".join(
                    command["name"]
                    for command
                    in self.command_store.list_commands()
                )
                + ". Можно выполнить команду "
                  "через Handler."
            )

        if any(
            x in lower
            for x in [
                "отмени",
                "cancel",
            ]
        ):
            return [
                {
                    "action": "cancel",
                    "reason": text,
                }
            ]

        if any(
            x in lower
            for x in [
                "разреши конфликты",
                "logger",
                "логгер",
                "resolve conflicts",
            ]
        ):
            return [
                {
                    "action":
                        "resolve_logger_conflicts"
                }
            ]

        if any(
            x in lower
            for x in [
                "загрузи документ",
                "route document",
                "load document",
                "подходящего агента",
            ]
        ):
            return [
                {
                    "action": "route_document",
                    "file_path":
                        self._extract_file_path(text),
                    "threshold": 1,
                }
            ]

        if (
            ("создай" in lower and "агент" in lower)
            or
            ("create" in lower and "agent" in lower)
        ):
            name = (
                self._extract_agent_name(text)
                or "NewAgent"
            )

            model_name = (
                self._extract_model_name(text)
            )

            command = {
                "action": "create_agent",
                "agent": name,
                "type":
                    "llm",
                "description":
                    f"Agent created from request: {text}",
                "system_prompt":
                    f"Ты агент {name}. "
                    f"Твоя роль сформирована "
                    f"из запроса пользователя: {text}",
                "tags":
                    self._guess_tags(text),
            }

            if model_name:
                command["model_name"] = model_name

            return [command]

        if any(
            x in lower
            for x in [
                "удали агента",
                "delete agent",
                "remove agent",
            ]
        ):
            name = (
                self._extract_agent_name(text)
                or self.registry.select_agent(text)
                or ""
            )

            return [
                {
                    "action": "delete_agent",
                    "agent": name,
                }
            ]

        selected = (
            self.registry.select_agent(text)
        )

        if selected is None:
            return (
                "В системе нет доступных агентов. "
                "Можно создать нового агента."
            )

        return [
            {
                "action": "extract",
                "agents": [selected],
                "prompts": {
                    selected: text
                },
            }
        ]

    @staticmethod
    def _extract_agent_name(
        text: str
    ) -> str | None:

        for token in (
            text
            .replace(",", " ")
            .replace(".", " ")
            .split()
        ):
            cleaned = token.strip()

            if (
                cleaned.endswith("Agent")
                and cleaned
                and cleaned[0].isupper()
            ):
                return cleaned

        return None

    @staticmethod
    def _extract_model_name(
        text: str
    ) -> str | None:

        models = [
            "Qwen2.5-3B-Instruct",
            "Qwen2.5-7B-Instruct",
            "Qwen2.5-14B-Instruct",
            "Mistral-7B",
        ]

        for model in models:
            if model.lower() in text.lower():
                return model

        return None

    @staticmethod
    def _extract_file_path(
        text: str
    ) -> str:

        match = re.search(
            r"([A-Za-z]:[\\/][^\s]+|"
            r"[\w./\\-]+\.(?:txt|md|json|pdf|csv|py))",
            text,
        )

        return match.group(1) if match else ""

    @staticmethod
    def _guess_tags(
        text: str
    ) -> List[str]:

        lower = text.lower()

        mapping = {
            "backend": ["backend", "api", "server"],
            "api": ["backend", "api"],
            "бэкенд": ["backend", "api", "server"],
            "devops": ["devops", "docker", "deploy"],
            "docker": ["devops", "docker"],
            "деплой": ["devops", "deploy"],
            "test": ["testing", "qa"],
            "qa": ["testing", "qa"],
            "тест": ["testing", "qa"],
            "security": ["security"],
            "безопас": ["security"],
            "frontend": ["frontend", "ui"],
            "ui": ["frontend", "ui"],
            "analysis": ["analysis", "summary"],
            "аналит": ["analysis", "summary"],
        }

        tags = []

        for key, values in mapping.items():
            if key in lower:
                tags.extend(values)

        return sorted(set(tags))