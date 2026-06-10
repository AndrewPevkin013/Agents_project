from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4


class MockAgent:

    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.name: str = metadata["name"]
        self.description: str = metadata.get("description", "")
        self.system_prompt: str = metadata.get("system_prompt", "")
        self.tags: List[str] = list(metadata.get("tags", []))
        self.memory: Dict[str, Any] = {}

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = payload.get("prompt") or payload.get("task") or payload.get("query") or ""

        return {
            "agent": self.name,
            "status": "ok",
            "role": self.system_prompt,
            "received_prompt": prompt,
            "memory_items": len(self.memory),
            "result": f"[{self.name}] обработал задачу как имитационный агент: {prompt}"
        }

    def add_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        record_id = data.get("id") or f"rec_{uuid4().hex[:8]}"
        self.memory[record_id] = data
        return {"status": "ok", "agent": self.name, "added_id": record_id}

    def delete_data(self, target: str) -> Dict[str, Any]:
        existed = target in self.memory
        if existed:
            del self.memory[target]
        return {"status": "ok", "agent": self.name, "deleted": target, "existed": existed}

    def edit_data(self, target: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if target not in self.memory:
            self.memory[target] = {}
        if isinstance(self.memory[target], dict):
            self.memory[target].update(data)
        else:
            self.memory[target] = data
        return {"status": "ok", "agent": self.name, "updated": target}

    def load_file(self, file_path: str) -> Dict[str, Any]:
        # MVP-заглушка. Реальную загрузку PDF/CSV/RAG подключим позже.
        record_id = f"file_{uuid4().hex[:8]}"
        self.memory[record_id] = {"type": "file", "path": file_path}
        return {
            "status": "ok",
            "agent": self.name,
            "file_path": file_path,
            "record_id": record_id,
            "chunks_loaded": 1
        }