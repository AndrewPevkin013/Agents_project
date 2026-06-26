from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List

class CommandStore:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.commands: List[Dict[str, Any]] = []
    def load(self) -> None:
        if not self.config_path.exists():
            self.config_path.write_text(json.dumps({"commands": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.commands = list(json.loads(self.config_path.read_text(encoding="utf-8")).get("commands", []))
    def list_commands(self) -> List[Dict[str, Any]]:
        return self.commands
    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))
    def retrieve(self, user_request: str, top_k: int = 3) -> List[Dict[str, Any]]:
        req = self._tokens(user_request)
        scored = []
        for command in self.commands:
            doc = " ".join([command.get("name", ""), command.get("functionality", ""), command.get("example", ""), json.dumps(command.get("command", {}), ensure_ascii=False), json.dumps(command.get("usage_example", {}), ensure_ascii=False)])
            scored.append((len(req & self._tokens(doc)), command))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**command, "score": score} for score, command in scored[:top_k]]
