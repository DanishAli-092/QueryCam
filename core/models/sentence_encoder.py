"""
core/models/sentence_encoder.py
=================================
SentenceTransformerEncoder — SDS §3.1 Modules 5 & 6 / §4.1 Class Diagram.

"A localized embedding model pinned to the 16GB system RAM, responsible
for translating both visual captions and user text queries into
high-dimensional numerical vectors."

Used in BOTH pipelines (SDS Component Overview lists it under
'Shift 1 & Shift 2'): during ingestion to embed BLIP captions, and
during forensic query to embed the user's natural-language question.
Because it is a CPU_Model, it never touches the GPU Mutex Lock — it
can run freely regardless of which model currently holds the GPU.
"""

from __future__ import annotations

import logging

import numpy as np

import config
from core.models.base import CPU_Model

logger = logging.getLogger("querycam.models.sentence_encoder")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None


class ModelNotLoadedError(RuntimeError):
    pass


class SentenceTransformerEncoder(CPU_Model):
    """dimension: int — SDS Class Diagram attribute (384 for all-MiniLM-L6-v2)."""

    def __init__(
        self,
        model_path: str = config.MODELS.sentence_transformer_id,
        dimension: int = config.PIPELINE.embedding_dimension,
        max_allocation_gb: float = 0.5,
    ) -> None:
        super().__init__(model_path, max_allocation_gb)
        self.dimension = dimension

    def load_model(self) -> None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is not installed.")
        self.pin_to_ram()
        self._model = SentenceTransformer(self.model_path, device="cpu")
        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim != self.dimension:
            logger.warning(
                "Configured embedding_dimension=%d does not match model's "
                "actual output dimension=%d — using the model's real value.",
                self.dimension, actual_dim,
            )
            self.dimension = actual_dim
        self.is_loaded = True
        logger.info("SentenceTransformerEncoder ready (dim=%d, cpu).", self.dimension)

    def unload_memory(self) -> None:
        super().unload_memory()  # CPU_Model.unload_memory()

    def encode_text(self, text: str) -> np.ndarray:
        """encode_text(text: str) -> np.ndarray — SDS Class Diagram.

        Used identically for BLIP captions (ingestion, SDS Sequence
        Diagram step 16 'encode()') and user queries (query flow, step 2).
        """
        if not self.is_loaded or self._model is None:
            raise ModelNotLoadedError("Call load_model() before encode_text().")
        embedding = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return embedding.astype(np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Batch variant — used during ingestion so N captions are embedded
        in one forward pass instead of N (Optimization Mandate: Batch
        Ingestion architectures, system prompt)."""
        if not self.is_loaded or self._model is None:
            raise ModelNotLoadedError("Call load_model() before encode_batch().")
        embeddings = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.astype(np.float32)
