from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.engine.agent_registry import AgentRegistry
from app.routing.semantic_router import SemanticAgentRouter


class DocumentRouter:
    """
    Orchestration layer between document upload and semantic routing.

    Old keyword matching and automatic mock-agent creation were removed.

    Stage 1 behavior:
      - suitable existing agent -> generate `load`
      - no suitable agent -> generate `no_action`

    Stage 2 will replace the NO_AGENT branch with:
      LLM summary -> LLM registry check -> optional create_agent.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        semantic_router: SemanticAgentRouter | None = None,
    ) -> None:
        self.registry = registry
        self.semantic_router = (
            semantic_router
            or SemanticAgentRouter(
                registry=registry,
                learn=False,
            )
        )

    @staticmethod
    def read_document(file_path: str) -> str:
        path = Path(file_path)

        if not path.exists():
            return ""

        if path.suffix.lower() in {
            ".txt",
            ".md",
            ".json",
            ".py",
            ".csv",
        }:
            return path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        # PDF/DOCX parsing is a separate next step.
        # Returning only the filename preserves current behavior.
        return path.name

    def process_document(
        self,
        file_path: str,
        document_text: str = "",
        threshold: int = 1,
    ) -> List[Dict[str, Any]]:
        del threshold  # compatibility with the existing API

        if not document_text:
            document_text = self.read_document(file_path)

        decision = self.semantic_router.route(
            document_text
        )

        if decision.matched:
            return [
                {
                    "action": "load",
                    "agent": decision.agent,
                    "file_path": file_path,
                    "routing": decision.to_dict(),
                }
            ]

        return [
            {
                "action": "no_action",
                "reason": "no_suitable_agent",
                "routing": decision.to_dict(),
                "file_path": file_path,
            }
        ]
