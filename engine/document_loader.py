from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


class DocumentLoader:
    def __init__(self, storage_dir: str | Path = "server_storage/documents") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def read_document(file_path: str) -> str:
        path = Path(file_path)

        if not path.exists():
            return ""

        if path.suffix.lower() in {".txt", ".md", ".json", ".py", ".csv"}:
            return path.read_text(encoding="utf-8", errors="ignore")

        return path.name

    @staticmethod
    def split_text(text: str, chunk_size: int = 1000) -> List[str]:
        if not text:
            return []

        return [
            text[i:i + chunk_size]
            for i in range(0, len(text), chunk_size)
        ]

    def load(self, file_path: str, agent_name: str) -> Dict[str, Any]:
        source = Path(file_path)

        document_id = f"doc_{uuid4().hex[:8]}"
        agent_dir = self.storage_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)

        saved_file = None

        if source.exists() and source.is_file():
            saved_file = agent_dir / f"{document_id}_{source.name}"
            shutil.copy2(source, saved_file)

        text = self.read_document(file_path)
        chunks = self.split_text(text)

        metadata = {
            "id": document_id,
            "type": "document",
            "agent": agent_name,
            "source_path": file_path,
            "saved_path": str(saved_file) if saved_file else "",
            "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "chars": len(text),
            "chunks_count": len(chunks),
            "chunks": chunks,
        }

        meta_path = agent_dir / f"{document_id}.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return metadata