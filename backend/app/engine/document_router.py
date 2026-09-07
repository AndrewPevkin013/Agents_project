from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from app.engine.agent_registry import AgentRegistry

class DocumentRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    @staticmethod
    def read_document(file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return ""
        if path.suffix.lower() in {".txt", ".md", ".json", ".py", ".csv"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        return path.name

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    @staticmethod
    def extract_topic(file_path: str, document_text: str = "") -> str:
        combined = f"{Path(file_path).stem} {document_text}".lower()
        mapping = {
            "backend": ["backend", "api", "server", "database", "auth", "rest", "endpoint"],
            "devops": ["devops", "docker", "deploy", "ci", "cd", "kubernetes", "infra"],
            "testing": ["test", "testing", "qa", "bug", "pytest", "coverage"],
            "security": ["security", "auth", "vulnerability", "token", "jwt", "audit"],
            "frontend": ["frontend", "ui", "react", "page", "component"],
        }
        best_topic, best_score = "document", 0
        for topic, words in mapping.items():
            score = sum(1 for word in words if word in combined)
            if score > best_score:
                best_topic, best_score = topic, score
        if best_score > 0:
            return best_topic
        tokens = list(DocumentRouter._tokens(combined))
        return tokens[0] if tokens else "document"

    def match_topic_to_agents(self, topic: str, document_text: str = "") -> Tuple[str | None, int]:
        query_tokens = self._tokens(topic + " " + document_text)
        best_agent, best_score = None, -1
        for name, metadata in self.registry.snapshot().items():
            agent_text = " ".join([name, metadata.get("description", ""), metadata.get("system_prompt", ""), " ".join(metadata.get("tags", []))])
            score = len(query_tokens & self._tokens(agent_text))
            if score > best_score:
                best_agent, best_score = name, score
        return best_agent, best_score

    @staticmethod
    def generate_new_agent_name(topic: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "", topic.title()) or "Document"
        return clean + "Agent"

    def process_document(self, file_path: str, document_text: str = "", threshold: int = 1) -> List[Dict[str, Any]]:
        if not document_text:
            document_text = self.read_document(file_path)
        topic = self.extract_topic(file_path, document_text)
        best_agent, score = self.match_topic_to_agents(topic, document_text)
        if best_agent and score >= threshold:
            return [{"action": "load", "agent": best_agent, "file_path": file_path}]
        new_agent = self.generate_new_agent_name(topic)
        if new_agent in self.registry.list_agents():
            new_agent = "DocumentAgent"
        return [
            {"action": "create_agent", "agent": new_agent, "type": "mock", "description": f"Agent created for documents about {topic}", "system_prompt": f"Ты агент для обработки документов по теме: {topic}.", "tags": [topic, "document"]},
            {"action": "load", "agent": new_agent, "file_path": file_path},
        ]
