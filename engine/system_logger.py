from __future__ import annotations
from typing import Any, Dict, List
from engine.agent_registry import AgentRegistry

class SystemLogger:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def collect_metrics(self) -> Dict[str, Any]:
        snapshot = self.registry.snapshot()
        duplicate_tag_groups: Dict[str, List[str]] = {}
        empty_prompt_agents = []
        for name, metadata in snapshot.items():
            if not metadata.get("system_prompt"):
                empty_prompt_agents.append(name)
            for tag in metadata.get("tags", []):
                duplicate_tag_groups.setdefault(tag, []).append(name)
        duplicate_tag_groups = {tag: names for tag, names in duplicate_tag_groups.items() if len(names) > 1}
        return {"agent_count": len(snapshot), "duplicate_tag_groups": duplicate_tag_groups, "empty_prompt_agents": empty_prompt_agents}

    def resolve_conflicts(self) -> List[Dict[str, Any]]:
        metrics = self.collect_metrics()
        commands: List[Dict[str, Any]] = []
        for agent_name in metrics["empty_prompt_agents"]:
            commands.append({"action": "edit_agent", "agent": agent_name, "system_prompt": f"Ты агент {agent_name}. Выполняй задачи согласно своей специализации."})
        if metrics["duplicate_tag_groups"] and not commands:
            commands.append({"action": "no_action", "reason": f"Duplicate tags detected but automatic consolidation is disabled: {metrics['duplicate_tag_groups']}"})
        if not commands:
            commands.append({"action": "no_action", "reason": "No conflicts detected"})
        return commands
