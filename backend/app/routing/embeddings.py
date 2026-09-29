from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import numpy as np


class EmbeddingService:
    """
    Lazy-loaded local BGE embedding + reranking service.

    The service never downloads models from Hugging Face Hub.
    Models are loaded only on the first actual embed()/rerank() call.
    """

    def __init__(
        self,
        embedding_model: str | None = None,
        reranker_model: str | None = None,
        device: str = "cpu",
        reranker_max_length: int = 512,
        models_dir: str | None = None,
    ) -> None:

        self.models_dir = Path(
            models_dir
            or os.getenv(
                "MODELS_DIR",
                "/project/models",
            )
        )

        self.embedding_model_path = Path(
            embedding_model
            or os.getenv(
                "EMBEDDING_MODEL_PATH",
                str(self.models_dir / "bge-m3"),
            )
        )

        self.reranker_model_path = Path(
            reranker_model
            or os.getenv(
                "RERANKER_MODEL_PATH",
                str(
                    self.models_dir
                    / "bge-reranker-v2-m3"
                ),
            )
        )

        self.device = self._resolve_device(
            os.getenv(
                "EMBEDDING_DEVICE",
                device,
            )
        )

        self.reranker_max_length = (
            reranker_max_length
        )

        self._embedder = None
        self._reranker = None

    @staticmethod
    def _resolve_device(
        device: str,
    ) -> str:

        device = str(
            device
        ).strip().lower()

        if device != "auto":
            return device

        try:
            import torch

            return (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        except ImportError:
            return "cpu"

    def _ensure_embedder(self) -> None:
        if self._embedder is not None:
            return

        if not self.embedding_model_path.exists():
            raise FileNotFoundError(
                "Local embedding model was not found: "
                f"{self.embedding_model_path}"
            )

        from sentence_transformers import (
            SentenceTransformer,
        )

        print(
            "[EmbeddingService] loading local embedder:",
            self.embedding_model_path,
            "device=",
            self.device,
        )

        self._embedder = SentenceTransformer(
            str(self.embedding_model_path),
            device=self.device,
            local_files_only=True,
        )

        print(
            "[EmbeddingService] embedder ready:",
            self.embedding_model_path,
        )

    def _ensure_reranker(self) -> None:
        if self._reranker is not None:
            return

        if not self.reranker_model_path.exists():
            raise FileNotFoundError(
                "Local reranker model was not found: "
                f"{self.reranker_model_path}"
            )

        from sentence_transformers import (
            CrossEncoder,
        )

        print(
            "[EmbeddingService] loading local reranker:",
            self.reranker_model_path,
            "device=",
            self.device,
        )

        self._reranker = CrossEncoder(
            str(self.reranker_model_path),
            device=self.device,
            max_length=self.reranker_max_length,
            local_files_only=True,
        )

        print(
            "[EmbeddingService] reranker ready:",
            self.reranker_model_path,
        )

    def embed(
        self,
        texts: Sequence[str],
    ) -> np.ndarray:

        if not texts:
            return np.empty(
                (0, 0),
                dtype=np.float32,
            )

        self._ensure_embedder()

        return self._embedder.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def rerank(
        self,
        pairs: Sequence[Sequence[str]],
    ) -> np.ndarray:

        if not pairs:
            return np.asarray(
                [],
                dtype=np.float32,
            )

        self._ensure_reranker()

        raw_scores = (
            self._reranker.predict(
                list(pairs)
            )
        )

        raw_scores = np.asarray(
            raw_scores,
            dtype=float,
        )

        return (
            1.0
            / (
                1.0
                + np.exp(-raw_scores)
            )
        )

_default_embedding_service = EmbeddingService()


def get_embedding_service() -> EmbeddingService:
    return _default_embedding_service