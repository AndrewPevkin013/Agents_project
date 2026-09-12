from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.documents.processor import DocumentProcessor
from app.engine.agent_registry import AgentRegistry
from app.routing.semantic_router import SemanticAgentRouter


class DocumentRouter:
    """
    Orchestration layer between upload preprocessing and semantic agent routing.

    Pipeline:
        uploaded file
        -> DocumentProcessor
        -> normalized routing text
        -> SemanticAgentRouter (BGE-M3)
        -> load existing agent OR no_action

    Images and engineering PDFs are first transformed by DrawingAnalyzer into
    RAG-oriented text plus structured metadata/diagram information.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        semantic_router: SemanticAgentRouter | None = None,
        document_processor: DocumentProcessor | None = None,
    ) -> None:
        self.registry = registry

        self.semantic_router = (
            semantic_router
            or SemanticAgentRouter(
                registry=registry,
                learn=False,
            )
        )

        project_dir = (
            Path(__file__).resolve().parents[3]
        )

        self.document_processor = (
            document_processor
            or DocumentProcessor(
                project_dir
                / "backend"
                / "server_storage"
                / "processed"
            )
        )

    def process_document(
        self,
        file_path: str,
        document_text: str = "",
        threshold: int = 1,
    ) -> List[Dict[str, Any]]:
        del threshold  # compatibility with existing API

        processed = (
            self.document_processor.process(
                file_path=file_path,
                document_text=document_text,
            )
        )

        normalized_path = (
            self.document_processor
            .save_normalized(processed)
        )

        routing_text = (
            processed.routing_text()
        )

        if not routing_text.strip():
            return [
                {
                    "action": "no_action",
                    "reason":
                        "empty_processed_document",
                    "file_path":
                        file_path,
                    "document_processing": {
                        "kind":
                            processed.kind,
                        "normalized_path":
                            normalized_path,
                        "artifacts":
                            processed.artifacts,
                    },
                }
            ]

        decision = self.semantic_router.route(
            routing_text
        )

        processing_info = {
            "kind": processed.kind,
            "normalized_path":
                normalized_path,
            "tags": processed.tags,
            "metadata":
                processed.metadata,
            "diagram": processed.diagram,
            "artifacts":
                processed.artifacts,
        }

        if decision.matched:
            return [
                {
                    "action": "load",
                    "agent": decision.agent,
                    "file_path": file_path,
                    "routing":
                        decision.to_dict(),
                    "document_processing":
                        processing_info,
                }
            ]

        return [
            {
                "action": "no_action",
                "reason":
                    "no_suitable_agent",
                "routing":
                    decision.to_dict(),
                "file_path":
                    file_path,
                "document_processing":
                    processing_info,
            }
        ]
