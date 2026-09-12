from __future__ import annotations

import os
from typing import Sequence

import numpy as np


class EmbeddingService:
    """
    Lazy-loaded BGE embedding + reranking service.

    Models are not loaded during module import. They are loaded only on the
    first call to embed() / rerank().
    """

    def __init__(
        self,
        embedding_model: str = "BAAI/bge-m3",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
        device: str = "auto",
        reranker_max_length: int = 512,
    ) -> None:
        self.embedding_model_name = embedding_model
        self.reranker_model_name = reranker_model
        self.device = self._resolve_device(device)
        self.reranker_max_length = reranker_max_length

        self.cache_folder = os.getenv("HF_HUB_CACHE")
        self._embedder = None
        self._reranker = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device

        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _ensure_embedder(self) -> None:
        if self._embedder is not None:
            return

        from sentence_transformers import SentenceTransformer

        self._embedder = SentenceTransformer(
            self.embedding_model_name,
            device=self.device,
            cache_folder=self.cache_folder,
            local_files_only=bool(self.cache_folder),
        )

    def _ensure_reranker(self) -> None:
        if self._reranker is not None:
            return

        from sentence_transformers import CrossEncoder

        self._reranker = CrossEncoder(
            self.reranker_model_name,
            device=self.device,
            max_length=self.reranker_max_length,
            cache_folder=self.cache_folder,
            local_files_only=bool(self.cache_folder),
        )

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        self._ensure_embedder()

        return self._embedder.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def rerank(self, pairs: Sequence[Sequence[str]]) -> np.ndarray:
        if not pairs:
            return np.asarray([], dtype=np.float32)

        self._ensure_reranker()

        raw_scores = self._reranker.predict(list(pairs))
        raw_scores = np.asarray(raw_scores, dtype=float)

        return 1.0 / (1.0 + np.exp(-raw_scores))