from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from app.engine.agent_registry import AgentRegistry
from app.routing.agent_profile import AgentProfile
from app.routing.chunker import split_into_chunks
from app.routing.embeddings import EmbeddingService


@dataclass
class RoutingDecision:
    agent: Optional[str]
    stage: str
    reason: str

    best_agent: Optional[str] = None
    best_similarity: float = 0.0
    margin: float = 0.0

    similarities: Dict[str, float] = field(default_factory=dict)
    rerank_scores: Dict[str, float] = field(default_factory=dict)

    chunks: List[str] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.agent is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "matched": self.matched,
            "stage": self.stage,
            "reason": self.reason,
            "best_agent": self.best_agent,
            "best_similarity": self.best_similarity,
            "margin": self.margin,
            "similarities": self.similarities,
            "rerank_scores": self.rerank_scores,
            "chunks_count": len(self.chunks),
        }


class SemanticAgentRouter:
    """
    Production adapter around the algorithm from agent_router_v3.ipynb.

    Pipeline:
        document
          -> sentence-aware chunker
          -> BGE-M3 bi-encoder
          -> profile similarities
          -> low/high/margin decision
          -> BGE reranker for the grey zone
          -> existing agent or NO_AGENT

    Agent creation is intentionally NOT performed here.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        embedding_service: EmbeddingService | None = None,
        *,
        low: float = 0.45,
        high: float = 0.58,
        margin: float = 0.05,
        rerank_top: int = 3,
        rerank_min: float = 0.30,
        learn: bool = False,
    ) -> None:
        self.registry = registry
        self.embedding_service = (
            embedding_service
            or EmbeddingService()
        )

        self.low = low
        self.high = high
        self.margin = margin
        self.rerank_top = rerank_top
        self.rerank_min = rerank_min
        self.learn = learn

        self.profiles: Dict[str, AgentProfile] = {}
        self.sync_from_registry()

    def _profile_from_metadata(
        self,
        name: str,
        metadata: Dict[str, Any],
    ) -> AgentProfile:
        # Friend's notebook uses description + keywords.
        # In the current product, tags are the natural source of keywords.
        description = metadata.get("description", "") or name
        keywords = list(metadata.get("tags", []))

        return AgentProfile(
            name=name,
            description=description,
            keywords=keywords,
            embedding_service=self.embedding_service,
        )

    def sync_from_registry(self) -> None:
        """
        Add profiles for newly registered agents and remove profiles
        for deleted agents.

        Existing profiles are intentionally preserved so that learned
        document chunks are not lost on every request.
        """
        snapshot = self.registry.snapshot()

        for name, metadata in snapshot.items():
            if name not in self.profiles:
                self.profiles[name] = self._profile_from_metadata(
                    name,
                    metadata,
                )

        existing_names = set(snapshot)
        stale = [
            name
            for name in self.profiles
            if name not in existing_names
        ]

        for name in stale:
            del self.profiles[name]

    def add_or_refresh_profile(
        self,
        agent_name: str,
    ) -> None:
        metadata = self.registry.get_metadata(agent_name)

        self.profiles[agent_name] = self._profile_from_metadata(
            agent_name,
            metadata,
        )

    def score(
        self,
        document: str,
    ) -> RoutingDecision:
        self.sync_from_registry()

        chunks = split_into_chunks(document)

        if not chunks:
            return RoutingDecision(
                agent=None,
                stage="empty",
                reason="empty_document",
            )

        if not self.profiles:
            return RoutingDecision(
                agent=None,
                stage="no_profiles",
                reason="no_registered_agents",
                chunks=chunks,
            )

        chunk_emb = self.embedding_service.embed(chunks)

        similarities = {
            name: profile.similarity(chunk_emb)
            for name, profile in self.profiles.items()
        }

        ranked = sorted(
            similarities.items(),
            key=lambda item: -item[1],
        )

        best_agent, best_similarity = ranked[0]

        second_similarity = (
            ranked[1][1]
            if len(ranked) > 1
            else -1.0
        )

        current_margin = (
            best_similarity - second_similarity
        )

        if best_similarity < self.low:
            return RoutingDecision(
                agent=None,
                stage="bi_encoder",
                reason=(
                    f"similarity {best_similarity:.3f} "
                    f"< low {self.low:.3f}"
                ),
                best_agent=best_agent,
                best_similarity=best_similarity,
                margin=current_margin,
                similarities=similarities,
                chunks=chunks,
            )

        if (
            best_similarity >= self.high
            and current_margin >= self.margin
        ):
            decision = RoutingDecision(
                agent=best_agent,
                stage="bi_encoder",
                reason="confident_match",
                best_agent=best_agent,
                best_similarity=best_similarity,
                margin=current_margin,
                similarities=similarities,
                chunks=chunks,
            )

            if self.learn:
                self.profiles[best_agent].add_document(
                    chunks,
                    chunk_emb,
                )

            return decision

        # Grey zone -> reranker.
        candidates = [
            name
            for name, _ in ranked[:self.rerank_top]
        ]

        # The notebook chooses the four chunks most similar to the
        # current best candidate.
        best_profile = self.profiles[best_agent]

        per_chunk = (
            chunk_emb @ best_profile.emb.T
        ).max(axis=1)

        top_indices = np.argsort(per_chunk)[::-1][:4]

        # Restore source order for readability.
        doc_view = " ".join(
            chunks[index]
            for index in sorted(top_indices)
        )

        pairs = [
            [
                self.profiles[name].profile_text(),
                doc_view,
            ]
            for name in candidates
        ]

        rerank_values = self.embedding_service.rerank(pairs)

        rerank_scores = {
            name: float(score)
            for name, score in zip(
                candidates,
                rerank_values,
            )
        }

        winner_index = int(
            np.argmax(rerank_values)
        )

        winner = candidates[winner_index]
        winner_score = float(
            rerank_values[winner_index]
        )

        if winner_score < self.rerank_min:
            return RoutingDecision(
                agent=None,
                stage="reranker",
                reason=(
                    f"reranker {winner_score:.3f} "
                    f"< rerank_min {self.rerank_min:.3f}"
                ),
                best_agent=best_agent,
                best_similarity=best_similarity,
                margin=current_margin,
                similarities=similarities,
                rerank_scores=rerank_scores,
                chunks=chunks,
            )

        decision = RoutingDecision(
            agent=winner,
            stage="reranker",
            reason=(
                f"reranker_match {winner_score:.3f}"
            ),
            best_agent=best_agent,
            best_similarity=best_similarity,
            margin=current_margin,
            similarities=similarities,
            rerank_scores=rerank_scores,
            chunks=chunks,
        )

        # Following the architecture note: by default we do not learn
        # from reranker decisions. This avoids reinforcing a grey-zone
        # mistake. Later a confirmed decision can be learned explicitly.
        return decision

    def route(
        self,
        document: str,
    ) -> RoutingDecision:
        return self.score(document)

    def learn_document(
        self,
        agent_name: str,
        document: str,
    ) -> None:
        """
        Explicit learning hook for confirmed assignments.
        """
        self.sync_from_registry()

        if agent_name not in self.profiles:
            raise ValueError(
                f"No routing profile for agent: {agent_name}"
            )

        chunks = split_into_chunks(document)

        if not chunks:
            return

        chunk_emb = self.embedding_service.embed(chunks)

        self.profiles[agent_name].add_document(
            chunks,
            chunk_emb,
        )
