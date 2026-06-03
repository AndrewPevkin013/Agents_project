import json
import re
from pathlib import Path
from typing import Any, Dict, List

from engine.agent_executor import AgentExecutor


class CommandRouter:
    def __init__(self, executor: AgentExecutor) -> None:
        self.executor = executor

    def route(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return self.executor.execute(command)

    def route_file(self, command_path: str | Path) -> Dict[str, Any]:
        with Path(command_path).open("r", encoding="utf-8") as file:
            command = json.load(file)
        return self.route(command)

    def route_directory(self, command_dir: str | Path) -> List[Dict[str, Any]]:
        results = []
        for path in sorted(Path(command_dir).glob("command_*.json")):
            results.append({"file": path.name, "response": self.route_file(path)})
        return results

    @staticmethod
    def from_angle_command(text: str) -> Dict[str, Any]:
        """
        Converts Handler format like:
        <AnalystAgent, Build execution plan>
        into internal JSON command.
        """
        match = re.fullmatch(r"\s*<\s*([^,>]+)\s*,\s*(.*?)\s*>\s*", text, re.DOTALL)
        if not match:
            raise ValueError(f"Invalid angle command: {text}")

        agent_name = match.group(1).strip()
        prompt = match.group(2).strip()

        return {
            "type": "agent_call",
            "agent": agent_name,
            "payload": {"prompt": prompt}
        }
