from __future__ import annotations
from typing import Any, Dict, List
from engine.agent_registry import AgentRegistry
from engine.document_router import DocumentRouter
from engine.system_logger import SystemLogger

class AgentExecutor:
    def __init__(self, registry: AgentRegistry, document_router: DocumentRouter | None = None, system_logger: SystemLogger | None = None) -> None:
        self.registry = registry
        self.document_router = document_router or DocumentRouter(registry)
        self.system_logger = system_logger or SystemLogger(registry)

    def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if "type" in command and command.get("type") == "agent_call":
            return self._execute_legacy_command(command)
        action = command.get("action")
        if not action:
            raise ValueError("Command must contain 'action' or legacy 'type'")
        handlers = {"extract": self._extract, "create_agent": self._create_agent, "delete_agent": self._delete_agent, "remove": self._delete_agent, "edit_agent": self._edit_agent, "cancel": self._cancel, "list_agents": self._list_agents, "add": self._add, "delete": self._delete_data, "edit": self._edit, "load": self._load, "route_document": self._route_document, "resolve_logger_conflicts": self._resolve_logger_conflicts, "consolidate": self._consolidate, "split": self._split, "no_action": self._no_action}
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
        return self.registry.get(agent_name).run(payload)

    def _extract(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agents = command.get("agents", [])
        prompts = command.get("prompts", {})
        answers = {agent_name: self.registry.get(agent_name).run({"prompt": prompts.get(agent_name, "")}) for agent_name in agents}
        return {"action": "extract", "agents": agents, "answers": answers}

    def _create_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        metadata = {"name": command["agent"], "type": command.get("type", "mock"), "description": command.get("description", ""), "system_prompt": command.get("system_prompt", ""), "tags": command.get("tags", []), "model_name": command.get("model_name", ""), "model_path": command.get("model_path", ""), "generation": command.get("generation", {"max_new_tokens": 256, "temperature": 0.7, "do_sample": True}), "device": command.get("device", "auto"), "torch_dtype": command.get("torch_dtype", "float16")}
        self.registry.upsert_from_metadata(metadata)
        return {"action": "create_agent", "status": "ok", "created": metadata["name"], "metadata": self.registry.get_metadata(metadata["name"])}

    def _delete_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command["agent"]
        self.registry.unregister(agent_name)
        return {"action": "delete_agent", "status": "ok", "deleted": agent_name}

    def _edit_agent(self, command: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = command["agent"]
        updates = {"type": command.get("type"), "description": command.get("description"), "system_prompt": command.get("system_prompt"), "tags": command.get("tags"), "model_name": command.get("model_name"), "model_path": command.get("model_path"), "generation": command.get("generation"), "device": command.get("device"), "torch_dtype": command.get("torch_dtype")}
        metadata = self.registry.update_metadata(agent_name, updates)
        return {"action": "edit_agent", "status": "ok", "agent": agent_name, "metadata": metadata}

    def _cancel(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "cancel", "status": "cancelled", "reason": command.get("reason", "")}
    def _list_agents(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "list_agents", "agents": self.registry.list_agents(), "metadata": self.registry.snapshot()}
    def _add(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "add", **self.registry.get(command["agent"]).add_data(command.get("data", {}))}
    def _delete_data(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "delete", **self.registry.get(command["agent"]).delete_data(command.get("target", ""))}
    def _edit(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "edit", **self.registry.get(command["agent"]).edit_data(command.get("target", ""), command.get("data", {}))}
    def _load(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "load", **self.registry.get(command["agent"]).load_file(command.get("file_path", ""))}
    def _route_document(self, command: Dict[str, Any]) -> Dict[str, Any]:
        generated = self.document_router.process_document(command.get("file_path", ""), command.get("document_text", ""), command.get("threshold", 1))
        return {"action": "route_document", "status": "ok", "generated_commands": generated, "results": self.execute_many(generated)}
    def _resolve_logger_conflicts(self, command: Dict[str, Any]) -> Dict[str, Any]:
        generated = self.system_logger.resolve_conflicts()
        return {"action": "resolve_logger_conflicts", "status": "ok", "generated_commands": generated, "results": self.execute_many(generated)}
    def _consolidate(self, command: Dict[str, Any]) -> Dict[str, Any]:
        source_agents = command.get("source_agents", [])
        target_agent = command["target_agent"]
        prompts, tags = [], []
        for name in source_agents:
            metadata = self.registry.get_metadata(name)
            prompts.append(metadata.get("system_prompt", ""))
            tags.extend(metadata.get("tags", []))
        self.registry.upsert_from_metadata({"name": target_agent, "type": "mock", "description": "Consolidated agent: " + ", ".join(source_agents), "system_prompt": "\n".join(prompts), "tags": sorted(set(tags))})
        removed = []
        for name in source_agents:
            if name in self.registry.list_agents():
                self.registry.unregister(name)
                removed.append(name)
        return {"action": "consolidate", "status": "ok", "created": target_agent, "removed": removed}
    def _split(self, command: Dict[str, Any]) -> Dict[str, Any]:
        source_agent = command["source_agent"]
        target_agents = command.get("target_agents", [])
        source_meta = self.registry.get_metadata(source_agent)
        created = []
        for name in target_agents:
            self.registry.upsert_from_metadata({"name": name, "type": "mock", "description": f"Specialized agent split from {source_agent}", "system_prompt": source_meta.get("system_prompt", ""), "tags": source_meta.get("tags", [])})
            created.append(name)
        self.registry.unregister(source_agent)
        return {"action": "split", "status": "ok", "created": created, "removed": source_agent}
    def _no_action(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "no_action", "status": "ok", "reason": command.get("reason", "")}
