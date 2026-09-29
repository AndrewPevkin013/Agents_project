from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.documents.agent_proposer import (
    AgentProposer,
    AgentProposal,
)
from app.documents.processor import DocumentProcessor
from app.engine.agent_registry import AgentRegistry
from app.routing.semantic_router import SemanticAgentRouter


class DocumentRouter:
    """
    Orchestration layer between upload preprocessing,
    semantic routing and automatic agent proposal.

    Pipeline:

        uploaded file
        -> DocumentProcessor
        -> normalized routing text
        -> SemanticAgentRouter

        existing agent
            -> load

        no suitable agent
            -> AgentProposer
            -> semantic registry re-check
            -> existing agent OR create_agent
            -> load
    """

    def __init__(
        self,
        registry: AgentRegistry,
        semantic_router: SemanticAgentRouter | None = None,
        document_processor: DocumentProcessor | None = None,
        agent_proposer: AgentProposer | None = None,
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

        self.agent_proposer = (
            agent_proposer
            or AgentProposer(
                models_dir=(
                    project_dir
                    / "models"
                )
            )
        )


    @staticmethod
    def _normalize_tags(tags: Any) -> set[str]:
        if not isinstance(tags, (list, tuple, set)):
            return set()

        return {
            str(tag).strip().lower()
            for tag in tags
            if str(tag).strip()
        }


    def _proposal_matches_existing_domain(
        self,
        proposal: AgentProposal,
        agent_name: str | None,
    ) -> tuple[bool, Dict[str, Any]]:
        if not agent_name:
            return False, {
                "matched": False,
                "reason": "no_candidate_agent",
            }

        try:
            metadata = self.registry.get_metadata(agent_name)
        except Exception:
            return False, {
                "matched": False,
                "reason": "candidate_metadata_unavailable",
                "candidate": agent_name,
            }

        proposal_tags = self._normalize_tags(
            proposal.tags
        )

        existing_tags = self._normalize_tags(
            metadata.get("tags", [])
        )

        overlap = proposal_tags & existing_tags

        denominator = max(
            1,
            min(
                len(proposal_tags),
                len(existing_tags),
            ),
        )

        overlap_ratio = (
            len(overlap) / denominator
        )

        matched = (
            bool(overlap)
            and overlap_ratio >= 0.5
        )

        return matched, {
            "matched": matched,
            "candidate": agent_name,
            "proposal_tags": sorted(proposal_tags),
            "existing_tags": sorted(existing_tags),
            "overlap": sorted(overlap),
            "overlap_ratio": overlap_ratio,
            "reason": (
                "domain_tags_compatible"
                if matched
                else "domain_tags_incompatible"
            ),
        }

    def process_document(
        self,
        file_path: str,
        document_text: str = "",
        threshold: int = 1,
    ) -> List[Dict[str, Any]]:

        del threshold  # compatibility with existing API

        # Registry may have changed since this router
        # instance was created.
        self.semantic_router.sync_from_registry()

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

        processing_info = {
            "kind":
                processed.kind,

            "normalized_path":
                normalized_path,

            "routing_text":
                routing_text,

            "tags":
                processed.tags,

            "metadata":
                processed.metadata,

            "diagram":
                processed.diagram,

            "artifacts":
                processed.artifacts,
        }

        if not routing_text.strip():
            return [
                {
                    "action": "no_action",
                    "reason":
                        "empty_processed_document",
                    "file_path":
                        file_path,
                    "document_processing":
                        processing_info,
                }
            ]

        #
        # Stage 1:
        # Try existing semantic agents.
        #

        decision = (
            self.semantic_router.route(
                routing_text
            )
        )

        if decision.matched:
            return [
                {
                    "action": "load",
                    "agent":
                        decision.agent,
                    "file_path":
                        file_path,
                    "routing":
                        decision.to_dict(),
                    "document_processing":
                        processing_info,
                }
            ]

        #
        # Stage 2:
        # Ask an LLM to describe the missing
        # semantic specialization.
        #

        try:
            proposal = (
                self.agent_proposer.propose(
                    document_text=routing_text,
                    existing_agents=(
                        self.registry.snapshot()
                    ),
                    document_metadata={
                        "kind":
                            processed.kind,

                        "tags":
                            processed.tags,

                        "metadata":
                            processed.metadata,

                        "diagram":
                            processed.diagram,
                    },
                )
            )

        except Exception as exc:
            # Document routing should not crash the
            # entire upload pipeline if the proposer
            # provider is unavailable.
            return [
                {
                    "action": "no_action",
                    "reason":
                        "agent_proposal_failed",
                    "error":
                        str(exc),
                    "routing":
                        decision.to_dict(),
                    "file_path":
                        file_path,
                    "document_processing":
                        processing_info,
                }
            ]

        if proposal is None:
            return [
                {
                    "action": "no_action",
                    "reason":
                        "agent_proposal_empty",
                    "routing":
                        decision.to_dict(),
                    "file_path":
                        file_path,
                    "document_processing":
                        processing_info,
                }
            ]

        #
        # Stage 3:
        # Re-check the proposal semantically against
        # existing agents before actually creating one.
        #

        proposal_decision = (
            self.semantic_router.route(
                proposal.semantic_text()
            )
        )

        domain_match, domain_check = (
            self._proposal_matches_existing_domain(
                proposal,
                proposal_decision.agent,
            )
        )

        if (
            proposal_decision.matched
            and domain_match
        ):
            return [
                {
                    "action": "load",
                    "agent":
                        proposal_decision.agent,
                    "file_path":
                        file_path,
                    "routing":
                        decision.to_dict(),
                    "proposal":
                        proposal.to_dict(),
                    "proposal_recheck":
                        proposal_decision.to_dict(),
                    "proposal_domain_check":
                        domain_check,
                    "document_processing":
                        processing_info,
                }
            ]

        #
        # Exact-name protection.
        #
        # Never overwrite an existing agent accidentally,
        # because AgentExecutor.create_agent currently
        # ultimately uses upsert_from_metadata().
        #

        if (
            proposal.name
            in self.registry.list_agents()
        ):
            return [
                {
                    "action": "load",
                    "agent":
                        proposal.name,
                    "file_path":
                        file_path,
                    "routing":
                        decision.to_dict(),
                    "proposal":
                        proposal.to_dict(),
                    "proposal_recheck":
                        proposal_decision.to_dict(),
                    "proposal_domain_check":
                        domain_check,
                    "document_processing":
                        processing_info,
                }
            ]

        #
        # Stage 4:
        # Truly new semantic domain.
        #
        # Return create_agent followed by load.
        # AgentExecutor.execute_many() executes them
        # sequentially.
        #

        return [
            {
                "action": "create_agent",
                "agent":
                    proposal.name,
                "description":
                    proposal.description,
                "system_prompt":
                    proposal.system_prompt,
                "tags":
                    proposal.tags,
            },
            {
                "action": "load",
                "agent":
                    proposal.name,
                "file_path":
                    file_path,
                "routing":
                    decision.to_dict(),
                "proposal":
                    proposal.to_dict(),
                "proposal_recheck":
                    proposal_decision.to_dict(),
                "document_processing":
                    processing_info,
            },
        ]