from __future__ import annotations

from typing import Any, Dict, List

from engine.agent_registry import AgentRegistry
from engine.command_store import CommandStore


class RuleBasedHandler:

    def __init__(self, registry: AgentRegistry, command_store: CommandStore) -> None:
        self.registry = registry
        self.command_store = command_store

    def build_system_prompt(self, user_request: str) -> str:
        agents = self.registry.snapshot()
        commands = self.command_store.retrieve(user_request, top_k=3)

        agents_block = "\n".join(
            f"- {name}: {meta.get('system_prompt', '')}"
            for name, meta in agents.items()
        )

        commands_block = "\n".join(
            f"- {c['name']}: {c.get('functionality', '')}"
            for c in commands
        )

        return (
            "You are the central Handler of a distributed multi-agent system.\n"
            "AVAILABLE AGENTS:\n"
            f"{agents_block}\n\n"
            "AVAILABLE COMMANDS:\n"
            f"{commands_block}\n"
        )

    def handle(self, user_request: str) -> List[Dict[str, Any]]:
        text = user_request.strip()
        lower = text.lower()

        # list agents
        if any(x in lower for x in ["какие агенты", "список агентов", "list agents", "what agents"]):
            return [{"action": "list_agents"}]

        # create agent: "создай агента SecurityAgent ..."
        if "создай" in lower and "агент" in lower:
            name = self._extract_agent_name(text) or "NewAgent"
            return [{
                "action": "create_agent",
                "agent": name,
                "description": f"Agent created from request: {text}",
                "system_prompt": f"Ты агент {name}. Твоя роль сформирована из запроса пользователя: {text}",
                "tags": self._guess_tags(text),
            }]

        if "create" in lower and "agent" in lower:
            name = self._extract_agent_name(text) or "NewAgent"
            return [{
                "action": "create_agent",
                "agent": name,
                "description": f"Agent created from request: {text}",
                "system_prompt": f"You are {name}. Your role was created from user request: {text}",
                "tags": self._guess_tags(text),
            }]

        # delete agent
        if any(x in lower for x in ["удали агента", "delete agent", "remove agent"]):
            name = self._extract_agent_name(text)
            if not name:
                selected = self.registry.select_agent(text)
                name = selected or ""
            return [{"action": "delete_agent", "agent": name}]

        # default: select agent and extract
        selected = self.registry.select_agent(text)
        if selected is None:
            return [{"action": "list_agents"}]

        return [{
            "action": "extract",
            "agents": [selected],
            "prompts": {selected: text}
        }]

    @staticmethod
    def _extract_agent_name(text: str) -> str | None:
        # Ищем токен вида BackendAgent / SecurityAgent / DevOpsAgent.
        for token in text.replace(",", " ").replace(".", " ").split():
            cleaned = token.strip()
            if cleaned.endswith("Agent") and cleaned[0].isupper():
                return cleaned
        return None

    @staticmethod
    def _guess_tags(text: str) -> List[str]:
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
        }

        tags = []
        for key, values in mapping.items():
            if key in lower:
                tags.extend(values)

        return sorted(set(tags))