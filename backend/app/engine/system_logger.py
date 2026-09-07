from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from app.engine.agent_registry import AgentRegistry
from app.engine.metrics_logger import MetricsLogger


class SystemLogger:
    def __init__(
        self,
        registry: AgentRegistry,
        logs_dir: str | Path = "logs",
        metrics_logger: MetricsLogger | None = None,
    ) -> None:
        self.registry = registry
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)

        self.state_log_path = self.logs_dir / "system_state.txt"
        self.state_json_path = self.logs_dir / "system_state.json"
        self.metrics_logger = metrics_logger or MetricsLogger(self.logs_dir)

    def collect_metrics(self) -> Dict[str, Any]:
        snapshot = self.registry.snapshot()

        duplicate_tag_groups: Dict[str, List[str]] = {}
        empty_prompt_agents = []

        for name, metadata in snapshot.items():
            if not metadata.get("system_prompt"):
                empty_prompt_agents.append(name)

            for tag in metadata.get("tags", []):
                duplicate_tag_groups.setdefault(tag, []).append(name)

        duplicate_tag_groups = {
            tag: names
            for tag, names in duplicate_tag_groups.items()
            if len(names) > 1
        }

        runtime_metrics = self.metrics_logger.build_summary()

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent_count": len(snapshot),
            "agents": snapshot,
            "duplicate_tag_groups": duplicate_tag_groups,
            "empty_prompt_agents": empty_prompt_agents,
            "runtime_metrics": runtime_metrics,
        }

    def save_state_report(self) -> Dict[str, Any]:
        metrics = self.collect_metrics()

        self.state_json_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        lines = [
            "SYSTEM STATE REPORT",
            "",
            f"Timestamp: {metrics['timestamp']}",
            f"Agent count: {metrics['agent_count']}",
            "",
            "AGENTS:",
        ]

        for name, metadata in metrics["agents"].items():
            lines.append(f"- {name}")
            lines.append(f"  type: {metadata.get('type', 'mock')}")
            lines.append(f"  tags: {metadata.get('tags', [])}")
            lines.append(f"  system_prompt: {metadata.get('system_prompt', '')}")

        lines.extend([
            "",
            "CONFLICTS:",
            f"Empty prompt agents: {metrics['empty_prompt_agents']}",
            f"Duplicate tag groups: {metrics['duplicate_tag_groups']}",
            "",
            "RUNTIME METRICS:",
            json.dumps(metrics["runtime_metrics"], ensure_ascii=False, indent=2),
        ])

        self.state_log_path.write_text("\n".join(lines), encoding="utf-8")

        return metrics

    def resolve_conflicts(self) -> List[Dict[str, Any]]:
        metrics = self.save_state_report()

        commands: List[Dict[str, Any]] = []

        for agent_name in metrics["empty_prompt_agents"]:
            commands.append({
                "action": "edit_agent",
                "agent": agent_name,
                "system_prompt": f"Ты агент {agent_name}. Выполняй задачи согласно своей специализации."
            })

        if metrics["duplicate_tag_groups"] and not commands:
            commands.append({
                "action": "no_action",
                "reason": f"Duplicate tags detected but automatic consolidation is disabled: {metrics['duplicate_tag_groups']}"
            })

        if not commands:
            commands.append({
                "action": "no_action",
                "reason": "No conflicts detected"
            })

        return commands