from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


class CommandStore:

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.commands: List[Dict[str, Any]] = []

    def load(self) -> None:
        if not self.config_path.exists():
            self.config_path.write_text(
                json.dumps({"commands": []}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.commands = list(config.get("commands", []))

    def list_commands(self) -> List[Dict[str, Any]]:
        return self.commands

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    def retrieve(self, user_request: str, top_k: int = 3) -> List[Dict[str, Any]]:
        request_tokens = self._tokens(user_request)

        scored = []
        for command in self.commands:
            doc = " ".join([
                command.get("name", ""),
                command.get("functionality", ""),
                command.get("example", ""),
                json.dumps(command.get("command", {}), ensure_ascii=False),
            ])
            doc_tokens = self._tokens(doc)
            score = len(request_tokens & doc_tokens)
            scored.append((score, command))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {**command, "score": score}
            for score, command in scored[:top_k]
        ]