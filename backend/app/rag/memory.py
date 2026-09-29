from __future__ import annotations

import json
import os
import re
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from app.routing.embeddings import (
    EmbeddingService,
    get_embedding_service,
)

@dataclass
class MemoryChunk:
    document_id: str
    text: str
    source_path: str
    saved_path: str
    metadata: Dict[str, Any]
    content_hash: str = ""


@dataclass
class RetrievedChunk:
    document_id: str
    chunk_index: int
    text: str
    source_path: str
    saved_path: str

    similarity: float
    rerank_score: float

    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "source_path": self.source_path,
            "saved_path": self.saved_path,
            "similarity": self.similarity,
            "rerank_score": self.rerank_score,
            "metadata": self.metadata,
        }


class AgentMemory:
    """
    Persistent semantic document store for one LLMAgent.

    Stage 9:
        document chunks
            -> BGE-M3 embeddings
            -> persistent storage
            -> cosine retrieval
            -> CrossEncoder reranking

    Documents are deduplicated by document_id
    and normalized content SHA-256.
    """

    def __init__(
        self,
        agent_name: str,
        embedding_service: EmbeddingService | None = None,
        storage_root: str | Path | None = None,
    ) -> None:

        self.agent_name = agent_name

        self.embedding_service = (
            embedding_service
            or get_embedding_service()
        )

        root = Path(
            storage_root
            or os.getenv(
                "RAG_STORAGE_DIR",
                "/project/backend/server_storage/rag",
            )
        )

        safe_agent_name = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            agent_name,
        ).strip("._")

        if not safe_agent_name:
            raise ValueError(
                "Agent name cannot be converted "
                "to a safe storage directory name"
            )

        self.storage_dir = (
            root / safe_agent_name
        )

        self.index_path = (
            self.storage_dir / "index.json"
        )

        self.embeddings_path = (
            self.storage_dir / "embeddings.npy"
        )

        self._chunks: List[MemoryChunk] = []
        self._embeddings: np.ndarray | None = None

        self._load()

    @property
    def chunks_count(self) -> int:
        return len(self._chunks)

    @property
    def documents_count(self) -> int:
        return len({
            chunk.document_id
            for chunk in self._chunks
        })

    def _serialize_chunk(
        self,
        chunk: MemoryChunk,
    ) -> Dict[str, Any]:

        return {
            "document_id": chunk.document_id,
            "text": chunk.text,
            "source_path": chunk.source_path,
            "saved_path": chunk.saved_path,
            "metadata": chunk.metadata,
            "content_hash": chunk.content_hash,
        }

    def _deserialize_chunk(
        self,
        data: Dict[str, Any],
    ) -> MemoryChunk:

        return MemoryChunk(
            document_id=str(
                data.get("document_id", "")
            ),
            text=str(
                data.get("text", "")
            ),
            source_path=str(
                data.get("source_path", "")
            ),
            saved_path=str(
                data.get("saved_path", "")
            ),
            metadata=dict(
                data.get("metadata", {})
            ),
            content_hash=str(
                data.get("content_hash", "")
            ),
        )


    def _save(self) -> None:
        self.storage_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        index_data = {
            "version": 1,
            "agent": self.agent_name,
            "chunks": [
                self._serialize_chunk(chunk)
                for chunk in self._chunks
            ],
        }

        temp_index = (
            self.index_path.with_suffix(
                ".json.tmp"
            )
        )

        temp_embeddings = (
            self.embeddings_path.with_suffix(
                ".npy.tmp"
            )
        )

        temp_index.write_text(
            json.dumps(
                index_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        embeddings = self._embeddings

        if embeddings is None:
            embeddings = np.empty(
                (0, 0),
                dtype=np.float32,
            )

        with temp_embeddings.open("wb") as file:
            np.save(
                file,
                embeddings.astype(
                    np.float32,
                    copy=False,
                ),
                allow_pickle=False,
            )

        temp_index.replace(
            self.index_path
        )

        temp_embeddings.replace(
            self.embeddings_path
        )

    def _content_hash(
        self,
        chunks: List[str],
    ) -> str:
        normalized = "\n".join(
            chunk.strip()
            for chunk in chunks
            if chunk.strip()
        )

        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

    def _load(self) -> None:
        index_exists = (
            self.index_path.exists()
        )

        embeddings_exist = (
            self.embeddings_path.exists()
        )

        if not index_exists and not embeddings_exist:
            return

        if index_exists != embeddings_exist:
            raise RuntimeError(
                f"Incomplete RAG storage for agent "
                f"'{self.agent_name}': index/embeddings "
                f"pair is inconsistent"
            )

        data = json.loads(
            self.index_path.read_text(
                encoding="utf-8"
            )
        )

        if int(data.get("version", 0)) != 1:
            raise RuntimeError(
                f"Unsupported RAG index version for "
                f"agent '{self.agent_name}'"
            )

        chunks = [
            self._deserialize_chunk(item)
            for item in data.get(
                "chunks",
                [],
            )
        ]

        embeddings = np.load(
            self.embeddings_path,
            allow_pickle=False,
        )

        embeddings = np.asarray(
            embeddings,
            dtype=np.float32,
        )

        if embeddings.ndim != 2:
            raise RuntimeError(
                f"Invalid embedding matrix for "
                f"agent '{self.agent_name}'"
            )

        if embeddings.shape[0] != len(chunks):
            raise RuntimeError(
                f"Persistent RAG storage mismatch "
                f"for agent '{self.agent_name}': "
                f"{len(chunks)} chunks vs "
                f"{embeddings.shape[0]} embeddings"
            )

        self._chunks = chunks

        self._embeddings = (
            embeddings
            if len(chunks) > 0
            else None
        )

        print(
            "[AgentMemory] restored:",
            f"agent={self.agent_name}",
            f"documents={self.documents_count}",
            f"chunks={self.chunks_count}",
        )


    def add_document(
        self,
        *,
        document_id: str,
        chunks: List[str],
        source_path: str = "",
        saved_path: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        clean_chunks = [
            str(chunk).strip()
            for chunk in chunks
            if str(chunk).strip()
        ]

        if not clean_chunks:
            return {
                "status": "empty",
                "document_id": document_id,
                "chunks_added": 0,
                "chunks_total": self.chunks_count,
                "documents_total": self.documents_count,
            }

        content_hash = self._content_hash(
            clean_chunks
        )

        existing_document_ids = {
            chunk.document_id
            for chunk in self._chunks
        }

        if document_id in existing_document_ids:
            return {
                "status": "already_indexed",
                "reason": "document_id",
                "document_id": document_id,
                "chunks_added": 0,
                "chunks_total": self.chunks_count,
                "documents_total": self.documents_count,
            }

        existing_hashes = {
            chunk.content_hash
            for chunk in self._chunks
            if chunk.content_hash
        }

        if content_hash in existing_hashes:
            return {
                "status": "already_indexed",
                "reason": "content_hash",
                "document_id": document_id,
                "content_hash": content_hash,
                "chunks_added": 0,
                "chunks_total": self.chunks_count,
                "documents_total": self.documents_count,
            }

        embeddings = self.embedding_service.embed(
            clean_chunks
        )

        if embeddings.shape[0] != len(clean_chunks):
            raise RuntimeError(
                "Embedding count does not match chunk count"
            )

        new_chunks = [
            MemoryChunk(
                document_id=document_id,
                text=text,
                source_path=source_path,
                saved_path=saved_path,
                metadata=dict(metadata),
                content_hash=content_hash,
            )
            for text in clean_chunks
        ]

        self._chunks.extend(new_chunks)

        if self._embeddings is None:
            self._embeddings = embeddings.astype(
                np.float32,
                copy=False,
            )

        else:
            self._embeddings = np.vstack([
                self._embeddings,
                embeddings,
            ]).astype(
                np.float32,
                copy=False,
            )

        self._save()

        return {
            "status": "ok",
            "document_id": document_id,
            "chunks_added": len(clean_chunks),
            "chunks_total": self.chunks_count,
            "documents_total": self.documents_count,
        }

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        rerank_top_k: int = 3,
    ) -> List[RetrievedChunk]:

        query = (query or "").strip()

        if not query:
            return []

        if not self._chunks:
            return []

        if self._embeddings is None:
            return []

        query_embedding = self.embedding_service.embed(
            [query]
        )[0]

        # Both document and query embeddings are normalized,
        # therefore dot product == cosine similarity.
        similarities = (
            self._embeddings
            @ query_embedding
        )

        candidate_count = min(
            max(top_k, rerank_top_k),
            len(self._chunks),
        )

        candidate_indices = (
            np.argsort(-similarities)[
                :candidate_count
            ]
        )

        candidates = [
            (
                int(index),
                float(similarities[index]),
            )
            for index in candidate_indices
        ]

        rerank_pairs = [
            [
                query,
                self._chunks[index].text,
            ]
            for index, _ in candidates
        ]

        rerank_scores = (
            self.embedding_service.rerank(
                rerank_pairs
            )
        )

        ranked = []

        for (
            (index, similarity),
            rerank_score,
        ) in zip(
            candidates,
            rerank_scores,
        ):
            ranked.append(
                (
                    index,
                    similarity,
                    float(rerank_score),
                )
            )

        ranked.sort(
            key=lambda item: -item[2]
        )

        result_limit = min(
            rerank_top_k,
            len(ranked),
        )

        results: List[RetrievedChunk] = []

        for (
            index,
            similarity,
            rerank_score,
        ) in ranked[:result_limit]:

            chunk = self._chunks[index]

            results.append(
                RetrievedChunk(
                    document_id=chunk.document_id,
                    chunk_index=index,
                    text=chunk.text,
                    source_path=chunk.source_path,
                    saved_path=chunk.saved_path,
                    similarity=similarity,
                    rerank_score=rerank_score,
                    metadata=chunk.metadata,
                )
            )

        return results