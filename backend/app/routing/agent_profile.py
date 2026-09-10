from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from app.routing.embeddings import EmbeddingService


@dataclass
class AgentProfile:
    """
    Semantic routing profile of an agent.

    The profile is independent from the LLM weights of the agent.
    It contains:
      - description,
      - keywords/tags,
      - chunks from previously accepted documents.
    """

    name: str
    description: str
    keywords: List[str] = field(default_factory=list)

    kw_weight: float = 0.92
    max_learned: int = 200

    embedding_service: EmbeddingService | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService()

        # Avoid an empty base profile. The notebook assumes a description
        # exists; in the product we use the agent name as a safe fallback.
        base_description = self.description.strip() or self.name

        self.description = base_description
        self.keywords = [
            keyword.strip()
            for keyword in self.keywords
            if keyword and keyword.strip()
        ]

        self.texts: List[str] = [
            self.description,
            *self.keywords,
        ]

        self.emb = self.embedding_service.embed(self.texts)

        self.weights = np.array(
            [1.0] + [self.kw_weight] * len(self.keywords),
            dtype=float,
        )

        self.n_learned = 0

    def add_document(
        self,
        chunks: List[str],
        chunk_emb: np.ndarray,
    ) -> None:
        """
        Learn only from a document that has already been accepted.

        FIFO applies only to learned document chunks; description and
        keywords are always preserved.
        """
        if not chunks:
            return

        self.texts += chunks
        self.emb = np.vstack([self.emb, chunk_emb])

        self.weights = np.concatenate(
            [
                self.weights,
                np.ones(len(chunks), dtype=float),
            ]
        )

        self.n_learned += len(chunks)

        if self.n_learned <= self.max_learned:
            return

        base = 1 + len(self.keywords)
        drop = self.n_learned - self.max_learned

        self.texts = (
            self.texts[:base]
            + self.texts[base + drop:]
        )

        self.emb = np.vstack(
            [
                self.emb[:base],
                self.emb[base + drop:],
            ]
        )

        self.weights = np.concatenate(
            [
                self.weights[:base],
                self.weights[base + drop:],
            ]
        )

        self.n_learned = self.max_learned

    def similarity(
        self,
        chunk_emb: np.ndarray,
        k: int = 3,
    ) -> float:
        """
        Document-to-agent similarity from the notebook:

        1. For every document chunk, find its strongest match
           against the profile matrix.
        2. Take the strongest k document chunks.
        3. Return their mean score.
        """
        if chunk_emb.size == 0:
            return 0.0

        scores = (chunk_emb @ self.emb.T) * self.weights
        per_chunk = scores.max(axis=1)

        k = min(k, len(per_chunk))

        if k <= 0:
            return 0.0

        return float(
            np.sort(per_chunk)[-k:].mean()
        )

    def profile_text(self, n_kw: int = 12) -> str:
        return (
            self.description
            + " Ключевые темы: "
            + ", ".join(self.keywords[:n_kw])
        )
