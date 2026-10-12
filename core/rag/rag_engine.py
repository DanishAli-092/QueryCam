# """
# core/rag/rag_engine.py
# ========================
# RAGEngine — SDS §3.1 Module 6 (Retrieval-Augmented Generation).

# "Translates user text queries into dense numerical vectors, executes
# rapid Cosine-Similarity searches against the vector index, and fetches
# timestamp metadata. Finally, synthesizes the retrieved chunks into a
# fluent, timestamped forensic answer."

# This class is the concrete embodiment of Module 6's "Components
# Involved: Sentence-Transformer (CPU), ChromaDB, Qwen2.5-1.5B GGUF
# (GPU)" — it does not appear as its own box in the Class Diagram
# because the diagram shows QueryCamController calling each component
# directly, but bundling that call sequence here is what actually makes
# Module Decomposition (SDS §3.1) "highly cohesive, loosely coupled" in
# code: QueryCamController.handle_forensic_query() becomes a single call
# into RAGEngine.answer_query(), instead of the Controller knowing five
# different components' APIs.

# Reproduces SDS Sequence Diagram §4.2.2 (Forensic Query) steps 1-14
# verbatim, MINUS the GPU-mutex acquire/release bracket — that bracket
# is applied by the caller via `with gpu_locked(Phase.QUERY):`, because
# lock ownership must span exactly "generate_answer()" and nothing else
# (encode_text/search/fetch_timestamps are CPU-only and must NOT hold
# the GPU lock idle while they run — see SDS §3.2.C).
# """

# from __future__ import annotations

# import logging
# from dataclasses import dataclass, field

# import config
# from core.models.qwen_llm import QwenLLMEngine
# from core.models.sentence_encoder import SentenceTransformerEncoder
# from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
# from core.rag.vector_store import ChromaDBVectorStore
# from core.storage.sqlite_store import SQLiteMetadataStore

# logger = logging.getLogger("querycam.rag.rag_engine")


# @dataclass
# class RAGAnswer:
#     """Return value of RAGEngine.answer_query() — everything the
#     Controller needs to update the UI and persist the CHAT_LOG row."""

#     answer_text: str
#     context_object_ids: list[str] = field(default_factory=list)
#     timestamps: list[str] = field(default_factory=list)  # formatted HH:MM:SS.mmm strings
#     raw_hits: list[dict] = field(default_factory=list)   # ChromaDB hits, for PDF export


# class RAGEngine:
#     def __init__(
#         self,
#         encoder: SentenceTransformerEncoder,
#         vector_store: ChromaDBVectorStore,
#         metadata_store: SQLiteMetadataStore,
#         llm: QwenLLMEngine,
#         orchestrator: GPUMutexOrchestrator | None = None,
#         top_k: int = config.PIPELINE.rag_top_k,
#     ) -> None:
#         self.encoder = encoder
#         self.vector_store = vector_store
#         self.metadata_store = metadata_store
#         self.llm = llm
#         self.orchestrator = orchestrator or GPUMutexOrchestrator.instance()
#         self.top_k = top_k

#     def answer_query(self, session_id: str, query_text: str) -> RAGAnswer:
#         """
#         Executes SDS Sequence Diagram §4.2.2 steps 3-16 verbatim:

#           3-6.   acquire_lock() -> check_vram() -> OK -> "Locked"
#           7-8.   encode_text() -> query_vector
#           9-10.  search() -> Context List (ChromaDB)
#           11-12. fetch_timestamps() -> Timestamps (SQLite)
#           13-14. generate_answer() -> Answer (Qwen)
#           15-16. release_lock() -> clear_cache()

#         (persist_chat_log() / step 17 "save_log()" happens AFTER this
#         method returns, in QueryCamController.handle_forensic_query() —
#         the diagram places it outside the locked band, since it is a
#         CPU-only SQLite write with nothing to do with the GPU.)

#         The entire retrieval + generation sequence is held under ONE
#         lock acquisition, matching the diagram's literal arrow order —
#         NOT just the generate_answer() call. This is a deliberate
#         session-level mutex (see TC-16: a second ingestion/query attempt
#         must be blocked for the full duration of this phase, not just
#         during the millisecond Qwen is actually decoding tokens).
#         """
#         with gpu_locked(Phase.QUERY, self.orchestrator):
#             # Steps 7-8: encode the query.
#             query_vector = self.encoder.encode_text(query_text)

#             # Steps 9-10: cosine similarity search, scoped to this session.
#             hits = self.vector_store.similarity_search(
#                 query_vector, top_k=self.top_k, session_id=session_id
#             )
#             if not hits:
#                 logger.info("RAGEngine: no ChromaDB hits for session=%s query=%r", session_id, query_text)

#             # Steps 11-12: resolve exact timestamps for each retrieved object.
#             object_ids = [h["object_id"] for h in hits]
#             timestamp_rows = self.metadata_store.fetch_timestamps(object_ids)
#             ts_by_object_id = {row["object_id"]: row for row in timestamp_rows}

#             # Build one enriched tuple per hit, then DEDUPE by formatted
#             # timestamp string and SORT chronologically. Without this,
#             # near-duplicate keyframes (motion filter can flag two
#             # consecutive frames as separate keyframes for the same
#             # lingering object) produce repeated timestamps in
#             # similarity-rank order rather than a clean, sorted,
#             # deduplicated evidence trail — confusing both the LLM prompt
#             # and the UI's timestamp display.
#             seen_timestamps: set[str] = set()
#             enriched: list[tuple[float, str, str, str]] = []  # (sec, ts_str, object_id, context_line)
#             for hit in hits:
#                 row = ts_by_object_id.get(hit["object_id"])
#                 if row is None:
#                     continue  # object vanished from SQLite (shouldn't happen, but don't crash)
#                 ts_str = self._format_timestamp(row["timestamp_sec"])
#                 if ts_str in seen_timestamps:
#                     continue
#                 seen_timestamps.add(ts_str)
#                 enriched.append((
#                     row["timestamp_sec"], ts_str, hit["object_id"],
#                     f"[{ts_str}] ({row['yolo_label']}) {row['blip_caption']}",
#                 ))
#             enriched.sort(key=lambda e: e[0])  # chronological — both for the LLM prompt and the UI

#             formatted_timestamps = [e[1] for e in enriched]
#             deduped_object_ids = [e[2] for e in enriched]
#             context_strings = [e[3] for e in enriched]

#             # Steps 13-14: synthesize the final forensic answer.
#             # Qwen is loaded here (inside the lock) and unloaded before the
#             # lock releases — this is what keeps "active peak allocation
#             # never breaches 3.20GB" true: Qwen's weights never coexist in
#             # VRAM with BLIP's outside this exact window.
#             try:
#                 if not self.llm.is_loaded:
#                     self.llm.load_model()
#                 answer_text = self.llm.generate_answer(
#                     prompt=query_text,
#                     context=context_strings,
#                     orchestrator=self.orchestrator,
#                 )
#             finally:
#                 self.llm.unload_memory()
#             # Steps 15-16 (release_lock() -> clear_cache()) fire automatically
#             # when the `with` block exits — see gpu_locked.__exit__().

#         return RAGAnswer(
#             answer_text=answer_text,
#             context_object_ids=deduped_object_ids,
#             timestamps=formatted_timestamps,
#             raw_hits=hits,
#         )

#     @staticmethod
#     def _format_timestamp(seconds: float) -> str:
#         millis = int(round((seconds - int(seconds)) * 1000))
#         h, rem = divmod(int(seconds), 3600)
#         m, s = divmod(rem, 60)
#         return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"


from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import config
from core.models.qwen_llm import QwenLLMEngine
from core.models.sentence_encoder import SentenceTransformerEncoder
from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
from core.rag.vector_store import ChromaDBVectorStore
from core.storage.sqlite_store import SQLiteMetadataStore

logger = logging.getLogger("querycam.rag.rag_engine")


@dataclass
class RAGAnswer:
    answer_text: str
    context_object_ids: list[str] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    raw_hits: list[dict] = field(default_factory=list)


class RAGEngine:
    def __init__(self, encoder: SentenceTransformerEncoder, vector_store: ChromaDBVectorStore,
                 metadata_store: SQLiteMetadataStore, llm: QwenLLMEngine,
                 orchestrator: GPUMutexOrchestrator | None = None,
                 top_k: int = config.PIPELINE.rag_top_k) -> None:
        self.encoder = encoder
        self.vector_store = vector_store
        self.metadata_store = metadata_store
        self.llm = llm
        self.orchestrator = orchestrator or GPUMutexOrchestrator.instance()
        self.top_k = top_k

    def answer_query(self, session_id: str, query_text: str,
                      progress_callback: Callable[[str], None] | None = None) -> RAGAnswer:
        def _report(stage: str) -> None:
            if progress_callback is not None:
                progress_callback(stage)

        _report("Encoding query (CPU)...")
        _report("🔒 Acquiring GPU lock for Qwen...")
        with gpu_locked(Phase.QUERY, self.orchestrator):
            _report("🔒 GPU locked (phase=query) — retrieving context...")
            query_vector = self.encoder.encode_text(query_text)
            hits = self.vector_store.similarity_search(query_vector, top_k=self.top_k, session_id=session_id)
            if not hits:
                logger.info("RAGEngine: no ChromaDB hits for session=%s query=%r", session_id, query_text)

            object_ids = [h["object_id"] for h in hits]
            timestamp_rows = self.metadata_store.fetch_timestamps(object_ids)
            ts_by_object_id = {row["object_id"]: row for row in timestamp_rows}

            # Dedupe by formatted timestamp string + sort chronologically —
            # without this, near-duplicate keyframes produce repeated,
            # out-of-order timestamps in similarity-rank order.
            seen_timestamps: set[str] = set()
            enriched: list[tuple[float, str, str, str]] = []
            for hit in hits:
                row = ts_by_object_id.get(hit["object_id"])
                if row is None:
                    continue
                ts_str = self._format_timestamp(row["timestamp_sec"])
                if ts_str in seen_timestamps:
                    continue
                seen_timestamps.add(ts_str)
                enriched.append((row["timestamp_sec"], ts_str, hit["object_id"],
                                 f"[{ts_str}] ({row['yolo_label']}) {row['blip_caption']}"))
            enriched.sort(key=lambda e: e[0])

            formatted_timestamps = [e[1] for e in enriched]
            deduped_object_ids = [e[2] for e in enriched]
            context_strings = [e[3] for e in enriched]

            try:
                if not self.llm.is_loaded:
                    _report("🔒 Loading Qwen2.5-1.5B (GPU, 4-bit GGUF)...")
                    self.llm.load_model()
                _report("🔒 Qwen generating answer...")
                answer_text = self.llm.generate_answer(prompt=query_text, context=context_strings,
                                                       orchestrator=self.orchestrator)
            finally:
                _report("Unloading Qwen, releasing VRAM...")
                self.llm.unload_memory()
        _report("✅ GPU lock released — Qwen idle.")

        return RAGAnswer(answer_text=answer_text, context_object_ids=deduped_object_ids,
                         timestamps=formatted_timestamps, raw_hits=hits)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        millis = int(round((seconds - int(seconds)) * 1000))
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"