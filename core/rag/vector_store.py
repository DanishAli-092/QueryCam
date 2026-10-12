"""
core/rag/vector_store.py
==========================
ChromaDBVectorStore — SDS §3.1 Module 6 (RAG) / §4.1 Class Diagram /
§5.2.6 (CHROMADB_VECTOR bridge table).

"An air-gapped vector database optimized for extremely fast
cosine-similarity searches to match user queries with specific video
frame embeddings."

Architectural note: ChromaDB's PersistentClient writes to a local
directory only (config.CHROMA_PERSIST_PATH) — no server process, no
network socket, satisfying the 100% offline/air-gapped constraint.
The actual 384-d float vectors live here; SQLiteMetadataStore's
CHROMADB_VECTOR table (SDS §5.2.6) only keeps the object_id <-> vector_id
mapping for relational traceability, never a duplicate authoritative copy.
"""

from __future__ import annotations

import logging

import numpy as np

import config

logger = logging.getLogger("querycam.rag.vector_store")

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:  # pragma: no cover
    chromadb = None
    Settings = None


class VectorStoreNotReadyError(RuntimeError):
    pass


class ChromaDBVectorStore:
    """
    index_path: str, metric: str = "cosine" — SDS Class Diagram attributes.
    """

    def __init__(
        self,
        index_path: str = config.CHROMA_PERSIST_PATH,
        metric: str = "cosine",
        collection_name: str = "querycam_objects",
    ) -> None:
        if chromadb is None:
            raise RuntimeError("chromadb is not installed. `pip install chromadb`.")

        self.index_path = index_path
        self.metric = metric
        self._client = chromadb.PersistentClient(
            path=index_path,
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": metric},
        )
        logger.info(
            "ChromaDBVectorStore ready (path=%s, metric=%s, collection=%s, count=%d)",
            index_path, metric, collection_name, self._collection.count(),
        )

    # ------------------------------------------------------------------ #
    # insert_vector() -> void — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def insert_vector(
        self,
        vector_id: str,
        embedding: np.ndarray,
        document: str,
        metadata: dict,
    ) -> None:
        """
        vector_id   : matches DETECTED_OBJECT.object_id (SDS §5.2.6 bridge).
        embedding   : 384-d float array from SentenceTransformerEncoder.
        document    : the BLIP caption text (kept alongside the vector so
                      similarity_search() can return it without a SQLite
                      round-trip for the common case).
        metadata    : e.g. {"session_id": ..., "frame_id": ..., "yolo_label": ...}
                      used for optional metadata-filtered search.
        """
        self._collection.upsert(
            ids=[vector_id],
            embeddings=[embedding.tolist()],
            documents=[document],
            metadatas=[metadata],
        )

    def insert_batch(
        self,
        vector_ids: list[str],
        embeddings: np.ndarray,
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Batch insert — Optimization Mandate: minimizes per-call overhead
        during Shift-1 ingestion versus one insert_vector() per object."""
        self._collection.upsert(
            ids=vector_ids,
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas,
        )

    # ------------------------------------------------------------------ #
    # similarity_search() -> List[dict] — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def similarity_search(
        self,
        query_embedding: np.ndarray,
        top_k: int = config.PIPELINE.rag_top_k,
        session_id: str | None = None,
    ) -> list[dict]:
        """
        Returns the Top-K most relevant context chunks (SDS Sequence
        Diagram §4.2.2 step 3: 'search() -> Context List'). Each dict:
            {"object_id": str, "caption": str, "distance": float, "metadata": dict}

        session_id, if given, scopes the search to one video session
        (a user querying "the backpack video" shouldn't retrieve hits
        from an unrelated earlier upload).
        """
        where_filter = {"session_id": session_id} if session_id else None
        results = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=where_filter,
        )

        hits: list[dict] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for object_id, caption, distance, meta in zip(ids, documents, distances, metadatas):
            hits.append({
                "object_id": object_id,
                "caption": caption,
                "distance": distance,
                "metadata": meta,
            })
        return hits

    def delete_by_session(self, session_id: str) -> None:
        """Companion to SQLiteMetadataStore.delete_chat_log() — used when a
        user purges a whole video session's footprint, not just chat text."""
        self._collection.delete(where={"session_id": session_id})

    def count(self) -> int:
        return self._collection.count()
