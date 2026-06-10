from __future__ import annotations

from typing import Any, Dict, List

from engine.agent_registry import AgentRegistry


class AgentExecutor:

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if "type" in command:
            return self._execute_legacy_command(command)

        action = command.get("action")
        if not action:
            raise ValueError("Command must contain 'action' or legacy 'type'")

        handlers = {
            "extract": self._extract,
            "create_agent": self._create_agent,
            "delete_agent": self._delete_agent,
            "list_agents": self._list_agents,
            "add": self._add,
            "delete": self._delete_data,
            "edit": self._edit,
            "load": self._load,
            "consolidate": self._consolidate,
            "split": self._split,
        }

        if action not in handlers:
            raise ValueError(f"Unsupported action: {action}")

        return handlers[action](command)

    def execute_many(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.execute(command) for command in commands]

    def _execute_legacy_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        command_type = command.get("type")

        if command_type != "agent_call":
            raise ValueError(f"Unsupported command type: {command_type}")

        agent_name = command.get("agent")
        if not agent_name:
            raise ValueError("Command must contain 'agent'")

        payload = command.get("payload", {})
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
            "description": command.get("description", ""),
            "system_prompt": command.get("system_prompt", ""),
            "tags": command.get("tags", []),
        }
        self.registry.upsert_from_metadata(metadata)
        return {
            "action": "create_agent",
            "status": "ok",
            "created": metadata["name"],
            "metadata": metadata,
        }

    def _delete_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command["agent"]
        self.registry.unregister(agent_name)
        return {
            "action": "delete_agent",
            "status": "ok",
            "deleted": agent_name
        }

    def _list_agents(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": "list_agents",
            "agents": self.registry.list_agents(),
            "metadata": self.registry.snapshot()
        }

    def _add(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        result = agent.add_data(command.get("data", {}))
        return {"action": "add", **result}

    def _delete_data(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        result = agent.delete_data(command.get("target", ""))
        return {"action": "delete", **result}

    def _edit(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        result = agent.edit_data(command.get("target", ""), command.get("data", {}))
        return {"action": "edit", **result}

    def _load(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent = self.registry.get(command["agent"])
        result = agent.load_file(command.get("file_path", ""))
        return {"action": "load", **result}

    def _consolidate(self, command: Dict[str, Any]) -> Dict[str, Any]:
        source_agents = command.get("source_agents", [])
        target_agent = command["target_agent"]

        descriptions = []
        tags = []
        prompts = []

        for name in source_agents:
            metadata = self.registry.get_metadata(name)
            descriptions.append(metadata.get("description", ""))
            tags.extend(metadata.get("tags", []))
            prompts.append(metadata.get("system_prompt", ""))

        self.registry.upsert_from_metadata({
            "name": target_agent,
            "description": "Consolidated agent: " + ", ".join(source_agents),
            "system_prompt": "\n".join(prompts),
            "tags": sorted(set(tags)),
        })

        removed = []
        for name in source_agents:
            if name in self.registry.list_agents():
                self.registry.unregister(name)
                removed.append(name)

        return {
            "action": "consolidate",
            "status": "ok",
            "created": target_agent,
            "removed": removed
        }

    def _split(self, command: Dict[str, Any]) -> Dict[str, Any]:
        source_agent = command["source_agent"]
        target_agents = command.get("target_agents", [])

        source_meta = self.registry.get_metadata(source_agent)

        created = []
        for name in target_agents:
            self.registry.upsert_from_metadata({
                "name": name,
                "description": f"Specialized agent split from {source_agent}",
                "system_prompt": source_meta.get("system_prompt", ""),
                "tags": source_meta.get("tags", []),
            })
            created.append(name)

        self.registry.unregister(source_agent)

        return {
            "action": "split",
            "status": "ok",
            "created": created,
            "removed": source_agent
        }