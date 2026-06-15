from __future__ import annotations

from typing import Any, Dict, List

from engine.agent_registry import AgentRegistry


class AgentExecutor:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if "type" in command and command.get("type") == "agent_call":
            return self._execute_legacy_command(command)

        action = command.get("action")
        if not action:
            raise ValueError("Command must contain 'action' or legacy 'type'")

        handlers = {
            "extract": self._extract,
            "create_agent": self._create_agent,
            "delete_agent": self._delete_agent,
            "edit_agent": self._edit_agent,
            "list_agents": self._list_agents,
            "add": self._add,
            "delete": self._delete_data,
            "edit": self._edit,
            "load": self._load,
        }

        if action not in handlers:
            raise ValueError(f"Unsupported action: {action}")

        return handlers[action](command)

    def execute_many(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.execute(command) for command in commands]

    def _execute_legacy_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command.get("agent")
        payload = command.get("payload", {})

        if not agent_name:
            raise ValueError("Command must contain 'agent'")

        if not isinstance(payload, dict):
            raise TypeError("Command payload must be a JSON object")

        agent = self.registry.get(agent_name)
        return agent.run(payload)

    def _extract(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agents = command.get("agents", [])
        prompts = command.get("prompts", {})

        answers = {}

        for agent_name in agents:
            agent = self.registry.get(agent_name)
            prompt = prompts.get(agent_name, "")
            answers[agent_name] = agent.run({"prompt": prompt})

        return {
            "action": "extract",
            "agents": agents,
            "answers": answers
        }

    def _create_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        metadata = {
            "name": command["agent"],
            "type": command.get("type", "mock"),
            "description": command.get("description", ""),
            "system_prompt": command.get("system_prompt", ""),
            "tags": command.get("tags", []),
            "model_name": command.get("model_name", ""),
            "model_path": command.get("model_path", ""),
            "generation": command.get("generation", {
                "max_new_tokens": 256,
                "temperature": 0.7,
                "do_sample": True
            }),
        }

        self.registry.upsert_from_metadata(metadata)

        return {
            "action": "create_agent",
            "status": "ok",
            "created": metadata["name"],
            "metadata": self.registry.get_metadata(metadata["name"]),
        }

    def _delete_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command["agent"]
        self.registry.unregister(agent_name)

        return {
            "action": "delete_agent",
            "status": "ok",
            "deleted": agent_name
        }

    def _edit_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command["agent"]
        old = self.registry.get_metadata(agent_name)

        metadata = {
            **old,
            "description": command.get("description", old.get("description", "")),
            "system_prompt": command.get("system_prompt", old.get("system_prompt", "")),
            "tags": command.get("tags", old.get("tags", [])),
            "type": command.get("type", old.get("type", "mock")),
            "model_name": command.get("model_name", old.get("model_name", "")),
            "model_path": command.get("model_path", old.get("model_path", "")),
            "generation": command.get("generation", old.get("generation", {})),
        }

        self.registry.upsert_from_metadata(metadata)

        return {
            "action": "edit_agent",
            "status": "ok",
            "agent": agent_name,
            "metadata": self.registry.get_metadata(agent_name)
        }

    def _list_agents(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": "list_agents",
            "agents": self.registry.list_agents(),
            "metadata": self.registry.snapshot()
        }

    def _add(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        return {"action": "add", **agent.add_data(command.get("data", {}))}

    def _delete_data(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        return {"action": "delete", **agent.delete_data(command.get("target", ""))}

    def _edit(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        return {"action": "edit", **agent.edit_data(command.get("target", ""), command.get("data", {}))}

    def _load(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        return {"action": "load", **agent.load_file(command.get("file_path", ""))}