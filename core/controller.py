# """
# core/controller.py
# ====================
# QueryCamController — SDS §4.1 Class Diagram (<<Controller>>).

#     +process_video_ingestion(path: str): bool
#     +handle_forensic_query(query_text: str): str
#     +update_ui_display(result: str): void

# This is the ONLY class that talks to every other module. Streamlit's
# app.py should never import OpenCVMotionFilter, YOLOv11Detector,
# BLIPCaptioner, etc. directly — it calls this Controller and nothing
# else, which is the Layered Architecture (SDS §1.1) justification
# actually enforced in code.
# """

# from __future__ import annotations

# import logging
# import uuid
# from pathlib import Path
# from typing import Callable

# import cv2

# import config
# from core.export.pdf_exporter import EvidenceFrame, PDFExporter
# from core.ingestion.motion_filter import OpenCVMotionFilter, VideoValidationError
# from core.models.blip_captioner import BLIPCaptioner
# from core.models.qwen_llm import QwenLLMEngine
# from core.models.sentence_encoder import SentenceTransformerEncoder
# from core.models.yolo_detector import YOLOv11Detector
# from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
# from core.rag.rag_engine import RAGEngine
# from core.rag.vector_store import ChromaDBVectorStore
# from core.security.auth import AuthService
# from core.storage.sqlite_store import SQLiteMetadataStore
# from core.video_utils import ensure_browser_playable
# from dto.entities import ChatRecord, DetectedObject, VideoSession

# logger = logging.getLogger("querycam.controller")


# class IngestionResult:
#     def __init__(self, success: bool, message: str, session_id: str | None = None,
#                  total_frames: int = 0, keyframe_count: int = 0) -> None:
#         self.success = success
#         self.message = message
#         self.session_id = session_id
#         self.total_frames = total_frames
#         self.keyframe_count = keyframe_count


# class QueryResult:
#     def __init__(self, success: bool, message: str, answer: str = "",
#                  timestamps: list[str] | None = None) -> None:
#         self.success = success
#         self.message = message
#         self.answer = answer
#         self.timestamps = timestamps or []


# class QueryCamController:
#     """<<Controller>> — SDS Class Diagram. One instance per Streamlit
#     session (constructed once and cached via st.session_state)."""

#     def __init__(self) -> None:
#         # --- Storage layer (Module 6) ---
#         self.store = SQLiteMetadataStore(str(config.SQLITE_DB_PATH))
#         self.vector_store = ChromaDBVectorStore(index_path=config.CHROMA_PERSIST_PATH)

#         # --- Security & Audit (Module 2) ---
#         self.auth = AuthService(self.store)

#         # --- Hardware Orchestration (Module 3) — constructed ONCE, shared
#         # by every GPU_Model instance below via the singleton accessor.
#         self.orchestrator = GPUMutexOrchestrator.instance()
#         self.orchestrator.vram_sentinel.start()

#         # --- CPU-pinned models (Module 4/5) — loaded once, kept resident;
#         # 16GB RAM budget comfortably tolerates this, unlike VRAM.
#         self.motion_filter = OpenCVMotionFilter()
#         self.yolo = YOLOv11Detector()
#         self.encoder = SentenceTransformerEncoder()

#         # --- GPU models (Module 5/6) — NOT loaded here. load_model() is
#         # called lazily, inside their respective locked windows, and
#         # unload_memory() is called before the lock releases. See
#         # _ingest_keyframes() and RAGEngine.answer_query().
#         self.blip = BLIPCaptioner()
#         self.qwen = QwenLLMEngine()

#         self.rag_engine = RAGEngine(
#             encoder=self.encoder,
#             vector_store=self.vector_store,
#             metadata_store=self.store,
#             llm=self.qwen,
#             orchestrator=self.orchestrator,
#         )
#         self.pdf_exporter = PDFExporter()

#         self._cpu_models_loaded = False

#     def _ensure_cpu_models_loaded(self) -> None:
#         """YOLO + SentenceEncoder are cheap and RAM-only — load once, lazily,
#         on first use rather than blocking Streamlit's initial page render."""
#         if self._cpu_models_loaded:
#             return
#         self.yolo.load_model()
#         self.encoder.load_model()
#         self._cpu_models_loaded = True

#     # ------------------------------------------------------------------ #
#     # process_video_ingestion(path) -> bool — SDS Class Diagram
#     # Reproduces Sequence Diagram §4.2.1 steps 1-25 exactly.
#     # ------------------------------------------------------------------ #

#     def process_video_ingestion(
#         self, video_path: str, user_id: int,
#         progress_callback: Callable[[str], None] | None = None,
#     ) -> IngestionResult:
#         """
#         progress_callback, if given, is invoked with a short human-readable
#         stage string at each major step — app.py wires this to a
#         st.status() box so the person watching sees "which model is
#         active" instead of a single opaque spinner for the whole
#         ingestion. Purely cosmetic: never affects control flow.
#         """
#         def _report(stage: str) -> None:
#             logger.info(stage)
#             if progress_callback is not None:
#                 progress_callback(stage)

#         # TC-03: reject unsupported formats before anything else runs.
#         _report("Validating video file...")
#         try:
#             OpenCVMotionFilter.validate_video(video_path)
#         except VideoValidationError as e:
#             self.store.log_system_event(user_id, "INGESTION_REJECTED", str(e))
#             return IngestionResult(False, "Only MP4/AVI formats accepted.")

#         _report("Loading YOLOv11 + Sentence-Encoder (CPU)...")
#         self._ensure_cpu_models_loaded()

#         cap = cv2.VideoCapture(video_path)
#         native_fps = cap.get(cv2.CAP_PROP_FPS) or config.PIPELINE.target_fps
#         total_native_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#         cap.release()

#         session = VideoSession(
#             user_id=user_id, video_path=video_path,
#             fps=int(native_fps), total_frames=total_native_frames,
#         )
#         self.store.save_video_session(session)
#         self.store.update_session_status(session.session_id, "Processing")

#         try:
#             # Step 3: acquire_lock() — held for the ENTIRE ingestion phase
#             # (steps 3-22 in the diagram), not just the BLIP caption calls.
#             with gpu_locked(Phase.INGESTION, self.orchestrator):
#                 # Steps 4-6: check_vram() -> OK -> "Locked" (handled inside gpu_locked)

#                 # Step 7-8: extract_frames() -> List<Frame>
#                 _report("Extracting frames (OpenCV motion filter, 5FPS + 640x640)...")
#                 frames = self.motion_filter.extract_frames(video_path, session.session_id)

#                 # Step 9-10: compute_timestamps() -> List<str> (metadata pass,
#                 # not persisted separately — Frame.timestamp_sec already has
#                 # the per-frame float; this call exists for parity with the
#                 # diagram and for any UI that wants the pre-formatted strings).
#                 self.motion_filter.compute_timestamps(video_path)

#                 # Step 11-12: save_metadata() -> SQLite, per frame.
#                 for frame in frames:
#                     self.store.save_frame_metadata(frame)

#                 # Steps 13-21: "loop / AI Pipeline on Keyframes" —
#                 # detect() -> crop() -> caption() -> encode() -> insert().
#                 keyframe_count = 0
#                 if any(f.is_keyframe for f in frames):
#                     keyframe_count = self._ingest_keyframes(frames, session.session_id, _report)

#             if keyframe_count == 0:
#                 self.store.update_session_status(session.session_id, "Completed")
#                 self.store.log_system_event(
#                     user_id, "INGESTION",
#                     f"session={session.session_id}: no motion-active frames detected",
#                 )
#                 return IngestionResult(
#                     True, "No motion-active frames detected – nothing to index.",
#                     session_id=session.session_id, total_frames=len(frames), keyframe_count=0,
#                 )

#             # Step 22-23 (release_lock() -> trigger_gc()) already fired on
#             # `with` exit above. The GPU lock is now free, so rendering the
#             # full annotated video (CPU-only YOLO pass, no GPU involved) is
#             # deliberately done OUTSIDE the `with gpu_locked(...)` block —
#             # it has nothing to do with the mutex and shouldn't extend the
#             # window where ingestion blocks a concurrent query.
#             if keyframe_count > 0:
#                 _report("Rendering processed video (full-frame YOLO pass)...")
#                 try:
#                     self.render_annotated_video(video_path, session.session_id)
#                 except Exception:  # noqa: BLE001 — a failed preview must never fail ingestion itself
#                     logger.exception("render_annotated_video failed for session=%s", session.session_id)

#             _report("Finalizing index...")
#             self.store.update_session_status(session.session_id, "Completed")
#             self.store.log_system_event(
#                 user_id, "INGESTION",
#                 f"session={session.session_id}: {len(frames)} frames, {keyframe_count} keyframes indexed",
#             )
#             return IngestionResult(
#                 True, "Ingestion complete.", session_id=session.session_id,
#                 total_frames=len(frames), keyframe_count=keyframe_count,
#             )

#         except RuntimeError as e:
#             # e.g. GPU lock could not be acquired (VRAM stayed >= cap after GC) — TC-05.
#             self.store.update_session_status(session.session_id, "Failed")
#             self.store.log_system_event(user_id, "INGESTION_FAILED", str(e))
#             logger.exception("Ingestion failed for session=%s", session.session_id)
#             return IngestionResult(False, "GPU memory threshold – releasing locks.",
#                                     session_id=session.session_id)

#     def _ingest_keyframes(
#         self, frames: list, session_id: str,
#         report: Callable[[str], None] = lambda stage: None,
#     ) -> int:
#         """Steps 13-21 of the Sequence Diagram — runs INSIDE the caller's
#         `with gpu_locked(...)` block. Loads BLIP once for the whole batch
#         (Optimization Mandate: Batch Ingestion) and guarantees it is
#         unloaded even if a caption call raises partway through."""
#         crop_dir = config.CROP_DIR / session_id
#         crop_dir.mkdir(parents=True, exist_ok=True)
#         keyframe_count = 0
#         total_keyframes = sum(1 for f in frames if f.is_keyframe)

#         try:
#             report("Loading BLIP-Base (GPU, float16)...")
#             self.blip.load_model()
#             for frame, frame_array in self.motion_filter.iter_keyframes(frames):
#                 keyframe_count += 1
#                 report(f"YOLOv11 + BLIP: keyframe {keyframe_count}/{total_keyframes}...")
#                 boxes = self.yolo.detect(frame_array)  # step: detect()
#                 if not boxes:
#                     continue
#                 crops = self.yolo.crop_entities(frame_array, boxes)  # step: crop()

#                 # Draw ALL boxes for this frame onto a full-frame copy and
#                 # persist it — this is the "processed video" gallery the
#                 # UI shows after ingestion (US-06), distinct from the
#                 # per-object crops used for BLIP captioning below.
#                 annotated = frame_array.copy()
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(
#                         annotated, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA,
#                     )
#                 annotated_path = crop_dir / f"{frame.frame_id}_annotated.jpg"
#                 cv2.imwrite(str(annotated_path), annotated)
#                 self.store.update_frame_image_path(frame.frame_id, str(annotated_path))

#                 for box, crop_arr in zip(boxes, crops):
#                     caption = self.blip.generate_caption(crop_arr, self.orchestrator)  # step: caption()

#                     object_id = str(uuid.uuid4())
#                     crop_path = crop_dir / f"{object_id}.jpg"
#                     cv2.imwrite(str(crop_path), crop_arr)

#                     detected_obj = DetectedObject(
#                         frame_id=frame.frame_id, yolo_label=box.label,
#                         confidence=box.confidence, bbox=box, blip_caption=caption,
#                         object_id=object_id, crop_image_path=str(crop_path),
#                     )
#                     self.store.save_detected_object(detected_obj)

#                     embedding = self.encoder.encode_text(caption)  # step: encode()
#                     self.vector_store.insert_vector(  # step: insert()
#                         vector_id=object_id, embedding=embedding, document=caption,
#                         metadata={"session_id": session_id, "frame_id": frame.frame_id,
#                                   "yolo_label": box.label},
#                     )
#                     self.store.link_vector(object_id, object_id)
#         finally:
#             # Unload BEFORE the lock releases — see VRAM Safeguard note above.
#             report("Unloading BLIP, releasing VRAM...")
#             self.blip.unload_memory()

#         return keyframe_count

#     # ------------------------------------------------------------------ #
#     # handle_forensic_query(text) -> str — SDS Class Diagram
#     # ------------------------------------------------------------------ #

#     def handle_forensic_query(self, session_id: str, user_id: int, query_text: str) -> QueryResult:
#         self._ensure_cpu_models_loaded()
#         try:
#             result = self.rag_engine.answer_query(session_id, query_text)
#         except RuntimeError as e:
#             self.store.log_system_event(user_id, "QUERY_FAILED", str(e))
#             return QueryResult(False, "GPU memory threshold – releasing locks.")

#         if not result.context_object_ids:
#             # TC-08: query with no matching context.
#             answer = "No relevant timestamps found. Try different keywords."
#             record = ChatRecord(user_id=user_id, session_id=session_id,
#                                  query_text=query_text, answer_text=answer)
#             self.store.persist_chat_log(record)  # step 17: save_log()
#             return QueryResult(True, "No matches.", answer=answer, timestamps=[])

#         # Step 17: save_log() — happens AFTER the GPU lock has already
#         # released inside rag_engine.answer_query().
#         record = ChatRecord(
#             user_id=user_id, session_id=session_id, query_text=query_text,
#             answer_text=result.answer_text, retrieved_context_ids=result.context_object_ids,
#         )
#         self.store.persist_chat_log(record)
#         self.store.log_system_event(user_id, "QUERY", f"session={session_id}: {query_text!r}")

#         return QueryResult(True, "OK", answer=result.answer_text, timestamps=result.timestamps)

#     # ------------------------------------------------------------------ #
#     # update_ui_display(result) -> void — SDS Class Diagram
#     # ------------------------------------------------------------------ #

#     def update_ui_display(self, result: str) -> None:
#         """
#         SDS Class Diagram declares this method on the Controller, but in
#         a Streamlit app the "UI" is just the next script rerun reading
#         st.session_state — there is no persistent view object to push
#         into. This method exists as the single seam the Streamlit layer
#         calls after every action, so app.py never manipulates
#         st.session_state fields the Controller doesn't know about.
#         """
#         logger.debug("update_ui_display: %s", result)

#     # ------------------------------------------------------------------ #
#     # Chat history / PDF export / audit logs — supporting Controller API
#     # (mirrors SDS §6 API Design endpoints 1:1 for a future REST layer)
#     # ------------------------------------------------------------------ #

#     def get_chat_history(self, session_id: str) -> list[ChatRecord]:
#         return self.store.get_chat_history(session_id)

#     def clear_chat_history(self, session_id: str, user_id: int) -> bool:
#         ok = self.store.delete_chat_log(session_id)
#         if ok:
#             self.vector_store.delete_by_session(session_id)
#             self.store.log_system_event(user_id, "CLEAR_HISTORY", f"session={session_id}")
#         return ok

#     def export_pdf(self, session_id: str, user_id: int, log_ids: list[int],
#                     include_evidence_frames: bool = True) -> str:
#         all_records = self.store.get_chat_history(session_id)
#         selected = [r for r in all_records if r.log_id in log_ids]

#         evidence_frames = None
#         if include_evidence_frames and selected:
#             evidence_frames = self._build_evidence_frames(selected)

#         path = self.pdf_exporter.generate_report(session_id, selected, evidence_frames)
#         self.store.log_system_event(user_id, "PDF_EXPORT", f"session={session_id}, path={path}")
#         return path

#     def _build_evidence_frames(self, records: list[ChatRecord]) -> dict[int, EvidenceFrame]:
#         evidence: dict[int, EvidenceFrame] = {}
#         for record in records:
#             if not record.retrieved_context_ids:
#                 continue
#             rows = self.store.fetch_timestamps(record.retrieved_context_ids[:1])
#             if not rows:
#                 continue
#             crop_path = rows[0].get("crop_image_path")
#             if crop_path and Path(crop_path).exists():
#                 evidence[record.log_id] = EvidenceFrame(
#                     image_path=crop_path,
#                     caption=f"{rows[0]['yolo_label']} @ frame {rows[0]['frame_index']}",
#                 )
#         return evidence

#     def get_system_logs(self, user_id: int | None = None) -> list:
#         return self.store.get_system_logs(user_id)

#     def get_vram_status(self) -> dict:
#         """Mirrors SDS §6 endpoint GET /api/system/vram."""
#         snap = self.orchestrator.vram_sentinel.check_vram()
#         return {"vram_free_pct": self.orchestrator.vram_sentinel.get_free_vram_percent(),
#                 "locked": self.orchestrator.is_locked(),
#                 "active_phase": self.orchestrator.active_phase.value}

#     def render_annotated_video(self, video_path: str, session_id: str) -> str:
#         """
#         Full per-frame YOLO pass purely to produce a continuous, playable
#         "processed video" with bounding boxes drawn — distinct from the
#         ingestion pipeline's sparse, motion-filtered keyframe sampling
#         (OpenCVMotionFilter only keeps keyframes for RAG indexing, which
#         would make for a choppy, discontinuous highlight reel rather than
#         a real video). This re-decodes the ORIGINAL file and runs YOLO on
#         EVERY frame at native resolution/FPS — slower (roughly one extra
#         full decode + detection pass over the whole video), but what the
#         person gets back actually plays like a normal annotated video.

#         YOLOv11Detector is a CPU_Model — this never touches the GPU Mutex
#         Lock, so it's safe to call with no gpu_locked() wrapper at all.

#         Returns the path to the final browser-playable (H.264) MP4.
#         """
#         self._ensure_cpu_models_loaded()

#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         cap = cv2.VideoCapture(video_path)
#         fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
#         width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#         height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#         writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

#         try:
#             while True:
#                 ok, frame = cap.read()
#                 if not ok:
#                     break
#                 # detect() rescales its output boxes to whatever frame shape
#                 # is passed in (see YOLOv11Detector._postprocess's orig_shape
#                 # argument) — passing the native-resolution frame here, not
#                 # the 640x640 one motion_filter uses, is what keeps this
#                 # output crisp instead of blurry/upscaled.
#                 boxes = self.yolo.detect(frame)
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(
#                         frame, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA,
#                     )
#                 writer.write(frame)
#         finally:
#             cap.release()
#             writer.release()

#         # cv2.VideoWriter's 'mp4v' fourcc is NOT browser-playable (same
#         # issue as raw AVI uploads — see core/video_utils.py's docstring).
#         # Reuse the exact same transcode helper the upload preview uses.
#         final_path = ensure_browser_playable(raw_path)
#         logger.info("Annotated video rendered for session=%s -> %s", session_id, final_path)
#         return final_path

#     def get_processed_video_path(self, session_id: str) -> str | None:
#         """Returns the cached annotated-video path for a session if
#         render_annotated_video() has already produced one, else None —
#         lets the UI re-show it on every rerun without re-rendering."""
#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         preview_path = raw_path.with_name(raw_path.stem + "_preview.mp4")
#         if preview_path.exists():
#             return str(preview_path)
#         if raw_path.exists():
#             return str(raw_path)  # transcode may have failed — fall back to the raw file
#         return None

#     def get_session_gallery(self, session_id: str) -> list[dict]:
#         """Processed-results gallery for the Video Ingestion tab — one
#         row per detected object, each with its own crop + caption (see
#         app.py::render_ingestion_tab, which groups these back per-frame
#         for display)."""
#         return self.store.get_session_detections(session_id)

#     def get_model_status(self) -> dict:
#         """
#         Live per-model load state + which GPU phase currently holds the
#         mutex — powers the sidebar's model status panel (which model is
#         locked, which is released). BLIP/Qwen are only ever loaded for
#         the exact duration of their own gpu_locked() window (see
#         _ingest_keyframes() and RAGEngine.answer_query()), so
#         `loaded == True` for either of them IS the "currently locked"
#         signal; there is no separate flag to track.
#         """
#         phase = self.orchestrator.active_phase.value
#         return {
#             "gpu_lock_phase": phase,
#             "models": [
#                 {"key": "yolo", "name": "YOLOv11n (CPU)", "loaded": self.yolo.is_loaded, "gpu": False},
#                 {"key": "encoder", "name": "Sentence-Encoder (CPU)", "loaded": self.encoder.is_loaded, "gpu": False},
#                 {"key": "blip", "name": "BLIP-Base (GPU)", "loaded": self.blip.is_loaded, "gpu": True},
#                 {"key": "qwen", "name": "Qwen2.5-1.5B (GPU)", "loaded": self.qwen.is_loaded, "gpu": True},
#             ],
#         }

#     def shutdown(self) -> None:
#         self.orchestrator.vram_sentinel.stop()
#         self.store.close()


# from __future__ import annotations

# import logging
# import uuid
# from pathlib import Path
# from typing import Callable

# import cv2

# import config
# from core.export.pdf_exporter import EvidenceFrame, PDFExporter
# from core.ingestion.motion_filter import OpenCVMotionFilter, VideoValidationError
# from core.models.blip_captioner import BLIPCaptioner
# from core.models.qwen_llm import QwenLLMEngine
# from core.models.sentence_encoder import SentenceTransformerEncoder
# from core.models.yolo_detector import YOLOv11Detector
# from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
# from core.rag.rag_engine import RAGEngine
# from core.rag.vector_store import ChromaDBVectorStore
# from core.security.auth import AuthService
# from core.storage.sqlite_store import SQLiteMetadataStore
# from core.video_utils import ensure_browser_playable
# from dto.entities import ChatRecord, DetectedObject, VideoSession

# logger = logging.getLogger("querycam.controller")


# class IngestionResult:
#     def __init__(self, success: bool, message: str, session_id: str | None = None,
#                  total_frames: int = 0, keyframe_count: int = 0) -> None:
#         self.success = success
#         self.message = message
#         self.session_id = session_id
#         self.total_frames = total_frames
#         self.keyframe_count = keyframe_count


# class QueryResult:
#     def __init__(self, success: bool, message: str, answer: str = "",
#                  timestamps: list[str] | None = None) -> None:
#         self.success = success
#         self.message = message
#         self.answer = answer
#         self.timestamps = timestamps or []


# class QueryCamController:
#     def __init__(self) -> None:
#         self.store = SQLiteMetadataStore(str(config.SQLITE_DB_PATH))
#         self.vector_store = ChromaDBVectorStore(index_path=config.CHROMA_PERSIST_PATH)
#         self.auth = AuthService(self.store)

#         self.orchestrator = GPUMutexOrchestrator.instance()
#         self.orchestrator.vram_sentinel.start()

#         self.motion_filter = OpenCVMotionFilter()
#         self.yolo = YOLOv11Detector()
#         self.encoder = SentenceTransformerEncoder()

#         self.blip = BLIPCaptioner()
#         self.qwen = QwenLLMEngine()

#         self.rag_engine = RAGEngine(encoder=self.encoder, vector_store=self.vector_store,
#                                     metadata_store=self.store, llm=self.qwen, orchestrator=self.orchestrator)
#         self.pdf_exporter = PDFExporter()
#         self._cpu_models_loaded = False

#         # Per-session proof-of-constraint data (SDS §3.2 visibility) — kept
#         # in-memory on the controller instance (which itself lives in
#         # st.session_state), same pattern as get_processed_video_path's
#         # disk-cache lookup: survives Streamlit tab-switch reruns without
#         # needing a new SQLite table for throwaway diagnostic data.
#         self._session_vram_history: dict[str, list[dict]] = {}
#         self._session_frame_stats: dict[str, dict] = {}

#     def _ensure_cpu_models_loaded(self) -> None:
#         if self._cpu_models_loaded:
#             return
#         self.yolo.load_model()
#         self.encoder.load_model()
#         self._cpu_models_loaded = True

#     def process_video_ingestion(self, video_path: str, user_id: int,
#                                  progress_callback: Callable[[str], None] | None = None) -> IngestionResult:
#         def _report(stage: str) -> None:
#             logger.info(stage)
#             if progress_callback is not None:
#                 progress_callback(stage)

#         _report("Validating video file...")
#         try:
#             OpenCVMotionFilter.validate_video(video_path)
#         except VideoValidationError as e:
#             self.store.log_system_event(user_id, "INGESTION_REJECTED", str(e))
#             return IngestionResult(False, "Only MP4/AVI formats accepted.")

#         _report("Loading YOLOv11 + Sentence-Encoder (CPU)...")
#         self._ensure_cpu_models_loaded()

#         cap = cv2.VideoCapture(video_path)
#         native_fps = cap.get(cv2.CAP_PROP_FPS) or config.PIPELINE.target_fps
#         total_native_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#         cap.release()

#         session = VideoSession(user_id=user_id, video_path=video_path,
#                                fps=int(native_fps), total_frames=total_native_frames)
#         self.store.save_video_session(session)
#         self.store.update_session_status(session.session_id, "Processing")

#         # Start the VRAM timeline capture for this ingestion run — covers
#         # CPU-model loading too, not just the GPU-locked window, so the
#         # chart shows the full "before BLIP / BLIP active / after BLIP"
#         # story (SDS §3.2 proof-of-constraint).
#         self.orchestrator.vram_sentinel.start_recording()

#         try:
#             with gpu_locked(Phase.INGESTION, self.orchestrator):
#                 _report("Extracting frames (OpenCV motion filter, 5FPS + 640x640)...")
#                 frames = self.motion_filter.extract_frames(video_path, session.session_id)
#                 self.motion_filter.compute_timestamps(video_path)

#                 for frame in frames:
#                     self.store.save_frame_metadata(frame)

#                 keyframe_count = 0
#                 if any(f.is_keyframe for f in frames):
#                     keyframe_count = self._ingest_keyframes(frames, session.session_id, _report)

#             if keyframe_count > 0:
#                 _report("Rendering processed video (full-frame YOLO pass)...")
#                 try:
#                     self.render_annotated_video(video_path, session.session_id)
#                 except Exception:
#                     logger.exception("render_annotated_video failed for session=%s", session.session_id)

#             _report("Finalizing index...")
#             self.store.update_session_status(session.session_id, "Completed")

#             # Frame-reduction proof (SDS target: min_keyframe_reduction_pct
#             # >= 0.60) — native decoded frames -> 5FPS-sampled frames ->
#             # motion-filtered keyframes.
#             sampled_count = len(frames)
#             reduction_pct = 1.0 - (keyframe_count / max(sampled_count, 1))
#             self._session_frame_stats[session.session_id] = {
#                 "total_native_frames": total_native_frames,
#                 "sampled_frame_count": sampled_count,
#                 "keyframe_count": keyframe_count,
#                 "reduction_pct": reduction_pct,
#             }

#             if keyframe_count == 0:
#                 self.store.log_system_event(user_id, "INGESTION",
#                                             f"session={session.session_id}: no motion-active frames detected")
#                 return IngestionResult(True, "No motion-active frames detected – nothing to index.",
#                                        session_id=session.session_id, total_frames=len(frames), keyframe_count=0)

#             self.store.log_system_event(
#                 user_id, "INGESTION",
#                 f"session={session.session_id}: {len(frames)} frames, {keyframe_count} keyframes indexed")
#             return IngestionResult(True, "Ingestion complete.", session_id=session.session_id,
#                                    total_frames=len(frames), keyframe_count=keyframe_count)

#         except RuntimeError as e:
#             self.store.update_session_status(session.session_id, "Failed")
#             self.store.log_system_event(user_id, "INGESTION_FAILED", str(e))
#             logger.exception("Ingestion failed for session=%s", session.session_id)
#             return IngestionResult(False, "GPU memory threshold – releasing locks.", session_id=session.session_id)

#         finally:
#             # Stop + snapshot the timeline regardless of success/failure,
#             # so even a failed run leaves a VRAM history behind to debug.
#             self.orchestrator.vram_sentinel.stop_recording()
#             self._session_vram_history[session.session_id] = self.orchestrator.vram_sentinel.get_history()

#     def _ingest_keyframes(self, frames: list, session_id: str,
#                           report: Callable[[str], None] = lambda stage: None) -> int:
#         crop_dir = config.CROP_DIR / session_id
#         crop_dir.mkdir(parents=True, exist_ok=True)
#         keyframe_count = 0
#         total_keyframes = sum(1 for f in frames if f.is_keyframe)

#         try:
#             report("Loading BLIP-Base (GPU, float16)...")
#             self.blip.load_model()
#             for frame, frame_array in self.motion_filter.iter_keyframes(frames):
#                 keyframe_count += 1
#                 report(f"YOLOv11 + BLIP: keyframe {keyframe_count}/{total_keyframes}...")
#                 boxes = self.yolo.detect(frame_array)
#                 if not boxes:
#                     continue
#                 crops = self.yolo.crop_entities(frame_array, boxes)

#                 annotated = frame_array.copy()
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(annotated, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
#                 annotated_path = crop_dir / f"{frame.frame_id}_annotated.jpg"
#                 cv2.imwrite(str(annotated_path), annotated)
#                 self.store.update_frame_image_path(frame.frame_id, str(annotated_path))

#                 for box, crop_arr in zip(boxes, crops):
#                     caption = self.blip.generate_caption(crop_arr, self.orchestrator)
#                     object_id = str(uuid.uuid4())
#                     crop_path = crop_dir / f"{object_id}.jpg"
#                     cv2.imwrite(str(crop_path), crop_arr)

#                     detected_obj = DetectedObject(frame_id=frame.frame_id, yolo_label=box.label,
#                                                   confidence=box.confidence, bbox=box, blip_caption=caption,
#                                                   object_id=object_id, crop_image_path=str(crop_path))
#                     self.store.save_detected_object(detected_obj)

#                     embedding = self.encoder.encode_text(caption)
#                     self.vector_store.insert_vector(
#                         vector_id=object_id, embedding=embedding, document=caption,
#                         metadata={"session_id": session_id, "frame_id": frame.frame_id, "yolo_label": box.label})
#                     self.store.link_vector(object_id, object_id)
#         finally:
#             report("Unloading BLIP, releasing VRAM...")
#             self.blip.unload_memory()

#         return keyframe_count

#     def render_annotated_video(self, video_path: str, session_id: str) -> str:
#         """Full per-frame YOLO pass for a continuous, playable 'processed
#         video' with bounding boxes drawn — distinct from the sparse,
#         motion-filtered keyframe sampling used for RAG indexing. Runs
#         OUTSIDE the GPU mutex lock (YOLO is CPU-only)."""
#         self._ensure_cpu_models_loaded()

#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         cap = cv2.VideoCapture(video_path)
#         fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
#         width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#         height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#         writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

#         try:
#             while True:
#                 ok, frame = cap.read()
#                 if not ok:
#                     break
#                 boxes = self.yolo.detect(frame)
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(frame, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
#                 writer.write(frame)
#         finally:
#             cap.release()
#             writer.release()

#         final_path = ensure_browser_playable(raw_path)
#         logger.info("Annotated video rendered for session=%s -> %s", session_id, final_path)
#         return final_path

#     def get_processed_video_path(self, session_id: str) -> str | None:
#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         preview_path = raw_path.with_name(raw_path.stem + "_preview.mp4")
#         if preview_path.exists():
#             return str(preview_path)
#         if raw_path.exists():
#             return str(raw_path)
#         return None

#     def handle_forensic_query(self, session_id: str, user_id: int, query_text: str) -> QueryResult:
#         self._ensure_cpu_models_loaded()
#         try:
#             result = self.rag_engine.answer_query(session_id, query_text)
#         except RuntimeError as e:
#             self.store.log_system_event(user_id, "QUERY_FAILED", str(e))
#             return QueryResult(False, "GPU memory threshold – releasing locks.")

#         if not result.context_object_ids:
#             answer = "No relevant timestamps found. Try different keywords."
#             record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text, answer_text=answer)
#             self.store.persist_chat_log(record)
#             return QueryResult(True, "No matches.", answer=answer, timestamps=[])

#         record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text,
#                             answer_text=result.answer_text, retrieved_context_ids=result.context_object_ids)
#         self.store.persist_chat_log(record)
#         self.store.log_system_event(user_id, "QUERY", f"session={session_id}: {query_text!r}")
#         return QueryResult(True, "OK", answer=result.answer_text, timestamps=result.timestamps)

#     def update_ui_display(self, result: str) -> None:
#         logger.debug("update_ui_display: %s", result)

#     def get_chat_history(self, session_id: str) -> list[ChatRecord]:
#         return self.store.get_chat_history(session_id)

#     def clear_chat_history(self, session_id: str, user_id: int) -> bool:
#         ok = self.store.delete_chat_log(session_id)
#         if ok:
#             self.vector_store.delete_by_session(session_id)
#             self.store.log_system_event(user_id, "CLEAR_HISTORY", f"session={session_id}")
#         return ok

#     def export_pdf(self, session_id: str, user_id: int, log_ids: list[int],
#                    include_evidence_frames: bool = True) -> str:
#         all_records = self.store.get_chat_history(session_id)
#         selected = [r for r in all_records if r.log_id in log_ids]
#         evidence_frames = None
#         if include_evidence_frames and selected:
#             evidence_frames = self._build_evidence_frames(selected)
#         path = self.pdf_exporter.generate_report(session_id, selected, evidence_frames)
#         self.store.log_system_event(user_id, "PDF_EXPORT", f"session={session_id}, path={path}")
#         return path

#     def _build_evidence_frames(self, records: list[ChatRecord]) -> dict[int, EvidenceFrame]:
#         evidence: dict[int, EvidenceFrame] = {}
#         for record in records:
#             if not record.retrieved_context_ids:
#                 continue
#             rows = self.store.fetch_timestamps(record.retrieved_context_ids[:1])
#             if not rows:
#                 continue
#             crop_path = rows[0].get("crop_image_path")
#             if crop_path and Path(crop_path).exists():
#                 evidence[record.log_id] = EvidenceFrame(
#                     image_path=crop_path, caption=f"{rows[0]['yolo_label']} @ frame {rows[0]['frame_index']}")
#         return evidence

#     def get_session_gallery(self, session_id: str) -> list[dict]:
#         return self.store.get_session_detections(session_id)

#     def get_vram_history(self, session_id: str) -> list[dict]:
#         """[{"t": elapsed_sec, "used_mb": float, "total_mb": float}, ...]
#         captured during this session's ingestion — empty list on a
#         CPU-only host (no NVIDIA GPU to poll)."""
#         return self._session_vram_history.get(session_id, [])

#     def get_frame_stats(self, session_id: str) -> dict | None:
#         """{"total_native_frames", "sampled_frame_count", "keyframe_count",
#         "reduction_pct"} for the motion-filter reduction proof."""
#         return self._session_frame_stats.get(session_id)

#     def get_peak_vram_status(self, session_id: str) -> dict | None:
#         """Compares the recorded peak against this project's own
#         absolute_peak_vram_gb constraint (config.HardwareConfig) — the
#         direct "did we meet our own design target" proof for the jury.

#         Returns None when there's no real GPU reading to compare (CPU-only
#         host, or nvidia-smi unavailable) — total_mb==0 is VRAMSentinel's
#         explicit "nothing to report" sentinel (see _read_vram_via_nvidia_smi),
#         not an actual zero-VRAM-used measurement, so those entries must be
#         filtered out rather than treated as a (misleadingly perfect) reading.
#         """
#         real_readings = [h for h in self.get_vram_history(session_id) if h["total_mb"] > 0]
#         if not real_readings:
#             return None
#         peak_mb = max(h["used_mb"] for h in real_readings)
#         budget_mb = config.HARDWARE.absolute_peak_vram_gb * 1024
#         return {
#             "peak_mb": peak_mb,
#             "peak_gb": round(peak_mb / 1024, 2),
#             "budget_gb": config.HARDWARE.absolute_peak_vram_gb,
#             "within_budget": peak_mb <= budget_mb,
#         }

#     def get_system_logs(self, user_id: int | None = None) -> list:
#         return self.store.get_system_logs(user_id)

#     def get_model_status(self) -> dict:
#         phase = self.orchestrator.active_phase.value
#         return {
#             "gpu_lock_phase": phase,
#             "models": [
#                 {"key": "yolo", "name": "YOLOv11n (CPU)", "loaded": self.yolo.is_loaded, "gpu": False},
#                 {"key": "encoder", "name": "Sentence-Encoder (CPU)", "loaded": self.encoder.is_loaded, "gpu": False},
#                 {"key": "blip", "name": "BLIP-Base (GPU)", "loaded": self.blip.is_loaded, "gpu": True},
#                 {"key": "qwen", "name": "Qwen2.5-1.5B (GPU)", "loaded": self.qwen.is_loaded, "gpu": True},
#             ],
#         }

#     def get_vram_status(self) -> dict:
#         self.orchestrator.vram_sentinel.check_vram()
#         return {"vram_free_pct": self.orchestrator.vram_sentinel.get_free_vram_percent(),
#                "locked": self.orchestrator.is_locked(), "active_phase": self.orchestrator.active_phase.value}

#     def shutdown(self) -> None:
#         self.orchestrator.vram_sentinel.stop()
#         self.store.close()

# from __future__ import annotations

# import logging
# import uuid
# from pathlib import Path
# from typing import Callable

# import cv2

# import config
# from core.export.pdf_exporter import EvidenceFrame, PDFExporter
# from core.ingestion.motion_filter import OpenCVMotionFilter, VideoValidationError
# from core.models.blip_captioner import BLIPCaptioner
# from core.models.qwen_llm import QwenLLMEngine
# from core.models.sentence_encoder import SentenceTransformerEncoder
# from core.models.yolo_detector import YOLOv11Detector
# from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
# from core.rag.rag_engine import RAGEngine
# from core.rag.vector_store import ChromaDBVectorStore
# from core.security.auth import AuthService
# from core.storage.sqlite_store import SQLiteMetadataStore
# from core.video_utils import ensure_browser_playable
# from dto.entities import ChatRecord, DetectedObject, VideoSession

# logger = logging.getLogger("querycam.controller")


# class IngestionResult:
#     def __init__(self, success: bool, message: str, session_id: str | None = None,
#                  total_frames: int = 0, keyframe_count: int = 0) -> None:
#         self.success = success
#         self.message = message
#         self.session_id = session_id
#         self.total_frames = total_frames
#         self.keyframe_count = keyframe_count


# class QueryResult:
#     def __init__(self, success: bool, message: str, answer: str = "",
#                  timestamps: list[str] | None = None) -> None:
#         self.success = success
#         self.message = message
#         self.answer = answer
#         self.timestamps = timestamps or []


# class QueryCamController:
#     def __init__(self) -> None:
#         self.store = SQLiteMetadataStore(str(config.SQLITE_DB_PATH))
#         self.vector_store = ChromaDBVectorStore(index_path=config.CHROMA_PERSIST_PATH)
#         self.auth = AuthService(self.store)

#         self.orchestrator = GPUMutexOrchestrator.instance()
#         self.orchestrator.vram_sentinel.start()

#         self.motion_filter = OpenCVMotionFilter()
#         self.yolo = YOLOv11Detector()
#         self.encoder = SentenceTransformerEncoder()

#         self.blip = BLIPCaptioner()
#         self.qwen = QwenLLMEngine()

#         self.rag_engine = RAGEngine(encoder=self.encoder, vector_store=self.vector_store,
#                                     metadata_store=self.store, llm=self.qwen, orchestrator=self.orchestrator)
#         self.pdf_exporter = PDFExporter()
#         self._cpu_models_loaded = False

#         # Per-session proof-of-constraint data (SDS §3.2 visibility) — kept
#         # in-memory on the controller instance (which itself lives in
#         # st.session_state), same pattern as get_processed_video_path's
#         # disk-cache lookup: survives Streamlit tab-switch reruns without
#         # needing a new SQLite table for throwaway diagnostic data.
#         self._session_vram_history: dict[str, list[dict]] = {}
#         self._session_frame_stats: dict[str, dict] = {}

#     def _ensure_cpu_models_loaded(self) -> None:
#         if self._cpu_models_loaded:
#             return
#         self.yolo.load_model()
#         self.encoder.load_model()
#         self._cpu_models_loaded = True

#     def process_video_ingestion(self, video_path: str, user_id: int,
#                                  progress_callback: Callable[[str], None] | None = None) -> IngestionResult:
#         def _report(stage: str) -> None:
#             logger.info(stage)
#             if progress_callback is not None:
#                 progress_callback(stage)

#         _report("Validating video file...")
#         try:
#             OpenCVMotionFilter.validate_video(video_path)
#         except VideoValidationError as e:
#             self.store.log_system_event(user_id, "INGESTION_REJECTED", str(e))
#             return IngestionResult(False, "Only MP4/AVI formats accepted.")

#         _report("Loading YOLOv11 + Sentence-Encoder (CPU)...")
#         self._ensure_cpu_models_loaded()

#         cap = cv2.VideoCapture(video_path)
#         native_fps = cap.get(cv2.CAP_PROP_FPS) or config.PIPELINE.target_fps
#         total_native_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#         cap.release()

#         session = VideoSession(user_id=user_id, video_path=video_path,
#                                fps=int(native_fps), total_frames=total_native_frames)
#         self.store.save_video_session(session)
#         self.store.update_session_status(session.session_id, "Processing")

#         # Start the VRAM timeline capture for this ingestion run — covers
#         # CPU-model loading too, not just the GPU-locked window, so the
#         # chart shows the full "before BLIP / BLIP active / after BLIP"
#         # story (SDS §3.2 proof-of-constraint).
#         self.orchestrator.vram_sentinel.start_recording()

#         try:
#             with gpu_locked(Phase.INGESTION, self.orchestrator):
#                 _report("Extracting frames (OpenCV motion filter, 5FPS + 640x640)...")
#                 frames = self.motion_filter.extract_frames(video_path, session.session_id)
#                 self.motion_filter.compute_timestamps(video_path)

#                 for frame in frames:
#                     self.store.save_frame_metadata(frame)

#                 keyframe_count = 0
#                 if any(f.is_keyframe for f in frames):
#                     keyframe_count = self._ingest_keyframes(frames, session.session_id, _report)

#             if keyframe_count > 0:
#                 _report("Rendering processed video (full-frame YOLO pass)...")
#                 try:
#                     self.render_annotated_video(video_path, session.session_id)
#                 except Exception:
#                     logger.exception("render_annotated_video failed for session=%s", session.session_id)

#             _report("Finalizing index...")
#             self.store.update_session_status(session.session_id, "Completed")

#             # Frame-reduction proof (SDS target: min_keyframe_reduction_pct
#             # >= 0.60) — native decoded frames -> 5FPS-sampled frames ->
#             # motion-filtered keyframes.
#             sampled_count = len(frames)
#             reduction_pct = 1.0 - (keyframe_count / max(sampled_count, 1))
#             self._session_frame_stats[session.session_id] = {
#                 "total_native_frames": total_native_frames,
#                 "sampled_frame_count": sampled_count,
#                 "keyframe_count": keyframe_count,
#                 "reduction_pct": reduction_pct,
#             }

#             if keyframe_count == 0:
#                 self.store.log_system_event(user_id, "INGESTION",
#                                             f"session={session.session_id}: no motion-active frames detected")
#                 return IngestionResult(True, "No motion-active frames detected – nothing to index.",
#                                        session_id=session.session_id, total_frames=len(frames), keyframe_count=0)

#             self.store.log_system_event(
#                 user_id, "INGESTION",
#                 f"session={session.session_id}: {len(frames)} frames, {keyframe_count} keyframes indexed")
#             return IngestionResult(True, "Ingestion complete.", session_id=session.session_id,
#                                    total_frames=len(frames), keyframe_count=keyframe_count)

#         except RuntimeError as e:
#             self.store.update_session_status(session.session_id, "Failed")
#             self.store.log_system_event(user_id, "INGESTION_FAILED", str(e))
#             logger.exception("Ingestion failed for session=%s", session.session_id)
#             return IngestionResult(False, "GPU memory threshold – releasing locks.", session_id=session.session_id)

#         finally:
#             # Stop + snapshot the timeline regardless of success/failure,
#             # so even a failed run leaves a VRAM history behind to debug.
#             self.orchestrator.vram_sentinel.stop_recording()
#             self._session_vram_history[session.session_id] = self.orchestrator.vram_sentinel.get_history()

#     def _ingest_keyframes(self, frames: list, session_id: str,
#                           report: Callable[[str], None] = lambda stage: None) -> int:
#         crop_dir = config.CROP_DIR / session_id
#         crop_dir.mkdir(parents=True, exist_ok=True)
#         keyframe_count = 0
#         total_keyframes = sum(1 for f in frames if f.is_keyframe)

#         try:
#             report("Loading BLIP-Base (GPU, float16)...")
#             self.blip.load_model()
#             for frame, frame_array in self.motion_filter.iter_keyframes(frames):
#                 keyframe_count += 1
#                 report(f"YOLOv11 + BLIP: keyframe {keyframe_count}/{total_keyframes}...")
#                 boxes = self.yolo.detect(frame_array)
#                 if not boxes:
#                     continue
#                 crops = self.yolo.crop_entities(frame_array, boxes)

#                 annotated = frame_array.copy()
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(annotated, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
#                 annotated_path = crop_dir / f"{frame.frame_id}_annotated.jpg"
#                 cv2.imwrite(str(annotated_path), annotated)
#                 self.store.update_frame_image_path(frame.frame_id, str(annotated_path))

#                 for box, crop_arr in zip(boxes, crops):
#                     caption = self.blip.generate_caption(crop_arr, self.orchestrator)
#                     object_id = str(uuid.uuid4())
#                     crop_path = crop_dir / f"{object_id}.jpg"
#                     cv2.imwrite(str(crop_path), crop_arr)

#                     detected_obj = DetectedObject(frame_id=frame.frame_id, yolo_label=box.label,
#                                                   confidence=box.confidence, bbox=box, blip_caption=caption,
#                                                   object_id=object_id, crop_image_path=str(crop_path))
#                     self.store.save_detected_object(detected_obj)

#                     embedding = self.encoder.encode_text(caption)
#                     self.vector_store.insert_vector(
#                         vector_id=object_id, embedding=embedding, document=caption,
#                         metadata={"session_id": session_id, "frame_id": frame.frame_id, "yolo_label": box.label})
#                     self.store.link_vector(object_id, object_id)
#         finally:
#             report("Unloading BLIP, releasing VRAM...")
#             self.blip.unload_memory()

#         return keyframe_count

#     def render_annotated_video(self, video_path: str, session_id: str) -> str:
#         """Full per-frame YOLO pass for a continuous, playable 'processed
#         video' with bounding boxes drawn — distinct from the sparse,
#         motion-filtered keyframe sampling used for RAG indexing. Runs
#         OUTSIDE the GPU mutex lock (YOLO is CPU-only)."""
#         self._ensure_cpu_models_loaded()

#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         cap = cv2.VideoCapture(video_path)
#         fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
#         width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#         height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#         writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

#         try:
#             while True:
#                 ok, frame = cap.read()
#                 if not ok:
#                     break
#                 boxes = self.yolo.detect(frame)
#                 for box in boxes:
#                     x1, y1, x2, y2 = box.as_xyxy()
#                     cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
#                     cv2.putText(frame, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
#                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
#                 writer.write(frame)
#         finally:
#             cap.release()
#             writer.release()

#         final_path = ensure_browser_playable(raw_path)
#         logger.info("Annotated video rendered for session=%s -> %s", session_id, final_path)
#         return final_path

#     def get_processed_video_path(self, session_id: str) -> str | None:
#         raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
#         preview_path = raw_path.with_name(raw_path.stem + "_preview.mp4")
#         if preview_path.exists():
#             return str(preview_path)
#         if raw_path.exists():
#             return str(raw_path)
#         return None

#     def handle_forensic_query(self, session_id: str, user_id: int, query_text: str,
#                               progress_callback: Callable[[str], None] | None = None) -> QueryResult:
#         self._ensure_cpu_models_loaded()
#         try:
#             result = self.rag_engine.answer_query(session_id, query_text, progress_callback=progress_callback)
#         except RuntimeError as e:
#             self.store.log_system_event(user_id, "QUERY_FAILED", str(e))
#             return QueryResult(False, "GPU memory threshold – releasing locks.")

#         if not result.context_object_ids:
#             answer = "No relevant timestamps found. Try different keywords."
#             record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text, answer_text=answer)
#             self.store.persist_chat_log(record)
#             return QueryResult(True, "No matches.", answer=answer, timestamps=[])

#         record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text,
#                             answer_text=result.answer_text, retrieved_context_ids=result.context_object_ids)
#         self.store.persist_chat_log(record)
#         self.store.log_system_event(user_id, "QUERY", f"session={session_id}: {query_text!r}")
#         return QueryResult(True, "OK", answer=result.answer_text, timestamps=result.timestamps)

#     def update_ui_display(self, result: str) -> None:
#         logger.debug("update_ui_display: %s", result)

#     def get_chat_history(self, session_id: str) -> list[ChatRecord]:
#         return self.store.get_chat_history(session_id)

#     def clear_chat_history(self, session_id: str, user_id: int) -> bool:
#         ok = self.store.delete_chat_log(session_id)
#         if ok:
#             self.vector_store.delete_by_session(session_id)
#             self.store.log_system_event(user_id, "CLEAR_HISTORY", f"session={session_id}")
#         return ok

#     def export_pdf(self, session_id: str, user_id: int, log_ids: list[int],
#                    include_evidence_frames: bool = True) -> str:
#         all_records = self.store.get_chat_history(session_id)
#         selected = [r for r in all_records if r.log_id in log_ids]
#         evidence_frames = None
#         if include_evidence_frames and selected:
#             evidence_frames = self._build_evidence_frames(selected)
#         path = self.pdf_exporter.generate_report(session_id, selected, evidence_frames)
#         self.store.log_system_event(user_id, "PDF_EXPORT", f"session={session_id}, path={path}")
#         return path

#     def _build_evidence_frames(self, records: list[ChatRecord]) -> dict[int, EvidenceFrame]:
#         evidence: dict[int, EvidenceFrame] = {}
#         for record in records:
#             if not record.retrieved_context_ids:
#                 continue
#             rows = self.store.fetch_timestamps(record.retrieved_context_ids[:1])
#             if not rows:
#                 continue
#             crop_path = rows[0].get("crop_image_path")
#             if crop_path and Path(crop_path).exists():
#                 evidence[record.log_id] = EvidenceFrame(
#                     image_path=crop_path, caption=f"{rows[0]['yolo_label']} @ frame {rows[0]['frame_index']}")
#         return evidence

#     def get_session_gallery(self, session_id: str) -> list[dict]:
#         return self.store.get_session_detections(session_id)

#     def get_vram_history(self, session_id: str) -> list[dict]:
#         """[{"t": elapsed_sec, "used_mb": float, "total_mb": float}, ...]
#         captured during this session's ingestion — empty list on a
#         CPU-only host (no NVIDIA GPU to poll)."""
#         return self._session_vram_history.get(session_id, [])

#     def get_frame_stats(self, session_id: str) -> dict | None:
#         """{"total_native_frames", "sampled_frame_count", "keyframe_count",
#         "reduction_pct"} for the motion-filter reduction proof."""
#         return self._session_frame_stats.get(session_id)

#     def get_peak_vram_status(self, session_id: str) -> dict | None:
#         """Compares the recorded peak against this project's own
#         absolute_peak_vram_gb constraint (config.HardwareConfig) — the
#         direct "did we meet our own design target" proof for the jury.

#         Returns None when there's no real GPU reading to compare (CPU-only
#         host, or nvidia-smi unavailable) — total_mb==0 is VRAMSentinel's
#         explicit "nothing to report" sentinel (see _read_vram_via_nvidia_smi),
#         not an actual zero-VRAM-used measurement, so those entries must be
#         filtered out rather than treated as a (misleadingly perfect) reading.
#         """
#         real_readings = [h for h in self.get_vram_history(session_id) if h["total_mb"] > 0]
#         if not real_readings:
#             return None
#         peak_mb = max(h["used_mb"] for h in real_readings)
#         budget_mb = config.HARDWARE.absolute_peak_vram_gb * 1024
#         return {
#             "peak_mb": peak_mb,
#             "peak_gb": round(peak_mb / 1024, 2),
#             "budget_gb": config.HARDWARE.absolute_peak_vram_gb,
#             "within_budget": peak_mb <= budget_mb,
#         }

#     def get_system_logs(self, user_id: int | None = None) -> list:
#         return self.store.get_system_logs(user_id)

#     def get_model_status(self) -> dict:
#         phase = self.orchestrator.active_phase.value
#         return {
#             "gpu_lock_phase": phase,
#             "models": [
#                 {"key": "yolo", "name": "YOLOv11n (CPU)", "loaded": self.yolo.is_loaded, "gpu": False},
#                 {"key": "encoder", "name": "Sentence-Encoder (CPU)", "loaded": self.encoder.is_loaded, "gpu": False},
#                 {"key": "blip", "name": "BLIP-Base (GPU)", "loaded": self.blip.is_loaded, "gpu": True},
#                 {"key": "qwen", "name": "Qwen2.5-1.5B (GPU)", "loaded": self.qwen.is_loaded, "gpu": True},
#             ],
#         }

#     def get_vram_status(self) -> dict:
#         self.orchestrator.vram_sentinel.check_vram()
#         return {"vram_free_pct": self.orchestrator.vram_sentinel.get_free_vram_percent(),
#                "locked": self.orchestrator.is_locked(), "active_phase": self.orchestrator.active_phase.value}

#     def shutdown(self) -> None:
#         self.orchestrator.vram_sentinel.stop()
#         self.store.close()


from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Callable

import cv2

import config
from core.export.pdf_exporter import EvidenceFrame, PDFExporter
from core.ingestion.motion_filter import OpenCVMotionFilter, VideoValidationError
from core.models.blip_captioner import BLIPCaptioner
from core.models.qwen_llm import QwenLLMEngine
from core.models.sentence_encoder import SentenceTransformerEncoder
from core.models.yolo_detector import YOLOv11Detector
from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase, gpu_locked
from core.rag.rag_engine import RAGEngine
from core.rag.vector_store import ChromaDBVectorStore
from core.security.auth import AuthService
from core.storage.sqlite_store import SQLiteMetadataStore
from core.video_utils import ensure_browser_playable
from dto.entities import ChatRecord, DetectedObject, VideoSession

logger = logging.getLogger("querycam.controller")


class IngestionResult:
    def __init__(self, success: bool, message: str, session_id: str | None = None,
                 total_frames: int = 0, keyframe_count: int = 0) -> None:
        self.success = success
        self.message = message
        self.session_id = session_id
        self.total_frames = total_frames
        self.keyframe_count = keyframe_count


class QueryResult:
    def __init__(self, success: bool, message: str, answer: str = "",
                 timestamps: list[str] | None = None) -> None:
        self.success = success
        self.message = message
        self.answer = answer
        self.timestamps = timestamps or []


class QueryCamController:
    def __init__(self) -> None:
        self.store = SQLiteMetadataStore(str(config.SQLITE_DB_PATH))
        self.vector_store = ChromaDBVectorStore(index_path=config.CHROMA_PERSIST_PATH)
        self.auth = AuthService(self.store)

        self.orchestrator = GPUMutexOrchestrator.instance()
        self.orchestrator.vram_sentinel.start()

        self.motion_filter = OpenCVMotionFilter()
        self.yolo = YOLOv11Detector()
        self.encoder = SentenceTransformerEncoder()

        self.blip = BLIPCaptioner()
        self.qwen = QwenLLMEngine()

        self.rag_engine = RAGEngine(encoder=self.encoder, vector_store=self.vector_store,
                                    metadata_store=self.store, llm=self.qwen, orchestrator=self.orchestrator)
        self.pdf_exporter = PDFExporter()
        self._cpu_models_loaded = False

        # Per-session proof-of-constraint data (SDS §3.2 visibility) — kept
        # in-memory on the controller instance (which itself lives in
        # st.session_state), same pattern as get_processed_video_path's
        # disk-cache lookup: survives Streamlit tab-switch reruns without
        # needing a new SQLite table for throwaway diagnostic data.
        self._session_vram_history: dict[str, list[dict]] = {}
        self._session_frame_stats: dict[str, dict] = {}

    def _ensure_cpu_models_loaded(self) -> None:
        if self._cpu_models_loaded:
            return
        self.yolo.load_model()
        self.encoder.load_model()
        self._cpu_models_loaded = True

    def process_video_ingestion(self, video_path: str, user_id: int,
                                 progress_callback: Callable[[str], None] | None = None) -> IngestionResult:
        def _report(stage: str) -> None:
            logger.info(stage)
            if progress_callback is not None:
                progress_callback(stage)

        _report("Validating video file...")
        try:
            OpenCVMotionFilter.validate_video(video_path)
        except VideoValidationError as e:
            self.store.log_system_event(user_id, "INGESTION_REJECTED", str(e))
            return IngestionResult(False, "Only MP4/AVI formats accepted.")

        _report("Loading YOLOv11 + Sentence-Encoder (CPU)...")
        self._ensure_cpu_models_loaded()

        cap = cv2.VideoCapture(video_path)
        native_fps = cap.get(cv2.CAP_PROP_FPS) or config.PIPELINE.target_fps
        total_native_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        session = VideoSession(user_id=user_id, video_path=video_path,
                               fps=int(native_fps), total_frames=total_native_frames)
        self.store.save_video_session(session)
        self.store.update_session_status(session.session_id, "Processing")

        # Start the VRAM timeline capture for this ingestion run — covers
        # CPU-model loading too, not just the GPU-locked window, so the
        # chart shows the full "before BLIP / BLIP active / after BLIP"
        # story (SDS §3.2 proof-of-constraint).
        self.orchestrator.vram_sentinel.start_recording()

        try:
            with gpu_locked(Phase.INGESTION, self.orchestrator):
                _report("Extracting frames (OpenCV motion filter, 5FPS + 640x640)...")
                frames = self.motion_filter.extract_frames(video_path, session.session_id)
                self.motion_filter.compute_timestamps(video_path)

                for frame in frames:
                    self.store.save_frame_metadata(frame)

                keyframe_count = 0
                if any(f.is_keyframe for f in frames):
                    keyframe_count = self._ingest_keyframes(frames, session.session_id, _report)

            if keyframe_count > 0:
                _report("Rendering processed video (full-frame YOLO pass)...")
                try:
                    self.render_annotated_video(video_path, session.session_id)
                except Exception:
                    logger.exception("render_annotated_video failed for session=%s", session.session_id)

            _report("Finalizing index...")
            self.store.update_session_status(session.session_id, "Completed")

            # Frame-reduction proof (SDS target: min_keyframe_reduction_pct
            # >= 0.60) — native decoded frames -> 5FPS-sampled frames ->
            # motion-filtered keyframes.
            sampled_count = len(frames)
            reduction_pct = 1.0 - (keyframe_count / max(sampled_count, 1))
            self._session_frame_stats[session.session_id] = {
                "total_native_frames": total_native_frames,
                "sampled_frame_count": sampled_count,
                "keyframe_count": keyframe_count,
                "reduction_pct": reduction_pct,
            }

            if keyframe_count == 0:
                self.store.log_system_event(user_id, "INGESTION",
                                            f"session={session.session_id}: no motion-active frames detected")
                return IngestionResult(True, "No motion-active frames detected – nothing to index.",
                                       session_id=session.session_id, total_frames=len(frames), keyframe_count=0)

            self.store.log_system_event(
                user_id, "INGESTION",
                f"session={session.session_id}: {len(frames)} frames, {keyframe_count} keyframes indexed")
            return IngestionResult(True, "Ingestion complete.", session_id=session.session_id,
                                   total_frames=len(frames), keyframe_count=keyframe_count)

        except RuntimeError as e:
            self.store.update_session_status(session.session_id, "Failed")
            self.store.log_system_event(user_id, "INGESTION_FAILED", str(e))
            logger.exception("Ingestion failed for session=%s", session.session_id)
            return IngestionResult(False, "GPU memory threshold – releasing locks.", session_id=session.session_id)

        finally:
            # Stop + snapshot the timeline regardless of success/failure,
            # so even a failed run leaves a VRAM history behind to debug.
            self.orchestrator.vram_sentinel.stop_recording()
            self._session_vram_history[session.session_id] = self.orchestrator.vram_sentinel.get_history()

    def _ingest_keyframes(self, frames: list, session_id: str,
                          report: Callable[[str], None] = lambda stage: None) -> int:
        crop_dir = config.CROP_DIR / session_id
        crop_dir.mkdir(parents=True, exist_ok=True)
        keyframe_count = 0
        total_keyframes = sum(1 for f in frames if f.is_keyframe)

        try:
            report("Loading BLIP-Base (GPU, float16)...")
            self.blip.load_model()
            for frame, frame_array in self.motion_filter.iter_keyframes(frames):
                keyframe_count += 1
                report(f"YOLOv11 + BLIP: keyframe {keyframe_count}/{total_keyframes}...")
                boxes = self.yolo.detect(frame_array)
                if not boxes:
                    continue
                crops = self.yolo.crop_entities(frame_array, boxes)

                annotated = frame_array.copy()
                for box in boxes:
                    x1, y1, x2, y2 = box.as_xyxy()
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(annotated, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
                annotated_path = crop_dir / f"{frame.frame_id}_annotated.jpg"
                cv2.imwrite(str(annotated_path), annotated)
                self.store.update_frame_image_path(frame.frame_id, str(annotated_path))

                for box, crop_arr in zip(boxes, crops):
                    caption = self.blip.generate_caption(crop_arr, self.orchestrator)
                    object_id = str(uuid.uuid4())
                    crop_path = crop_dir / f"{object_id}.jpg"
                    cv2.imwrite(str(crop_path), crop_arr)

                    detected_obj = DetectedObject(frame_id=frame.frame_id, yolo_label=box.label,
                                                  confidence=box.confidence, bbox=box, blip_caption=caption,
                                                  object_id=object_id, crop_image_path=str(crop_path))
                    self.store.save_detected_object(detected_obj)

                    embedding = self.encoder.encode_text(caption)
                    self.vector_store.insert_vector(
                        vector_id=object_id, embedding=embedding, document=caption,
                        metadata={"session_id": session_id, "frame_id": frame.frame_id, "yolo_label": box.label})
                    self.store.link_vector(object_id, object_id)
        finally:
            report("Unloading BLIP, releasing VRAM...")
            self.blip.unload_memory()

        return keyframe_count

    def render_annotated_video(self, video_path: str, session_id: str) -> str:
        """Full per-frame YOLO pass for a continuous, playable 'processed
        video' with bounding boxes drawn — distinct from the sparse,
        motion-filtered keyframe sampling used for RAG indexing. Runs
        OUTSIDE the GPU mutex lock (YOLO is CPU-only)."""
        self._ensure_cpu_models_loaded()

        raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                boxes = self.yolo.detect(frame)
                for box in boxes:
                    x1, y1, x2, y2 = box.as_xyxy()
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(frame, f"{box.label} {box.confidence:.2f}", (x1, max(y1 - 6, 10)),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
                writer.write(frame)
        finally:
            cap.release()
            writer.release()

        final_path = ensure_browser_playable(raw_path)
        logger.info("Annotated video rendered for session=%s -> %s", session_id, final_path)
        return final_path

    def get_processed_video_path(self, session_id: str) -> str | None:
        raw_path = config.PROCESSED_VIDEO_DIR / f"{session_id}_annotated_raw.mp4"
        preview_path = raw_path.with_name(raw_path.stem + "_preview.mp4")
        if preview_path.exists():
            return str(preview_path)
        if raw_path.exists():
            return str(raw_path)
        return None

    def handle_forensic_query(self, session_id: str, user_id: int, query_text: str,
                              progress_callback: Callable[[str], None] | None = None) -> QueryResult:
        self._ensure_cpu_models_loaded()
        try:
            result = self.rag_engine.answer_query(session_id, query_text, progress_callback=progress_callback)
        except RuntimeError as e:
            self.store.log_system_event(user_id, "QUERY_FAILED", str(e))
            return QueryResult(False, "GPU memory threshold – releasing locks.")

        if not result.context_object_ids:
            answer = "No relevant timestamps found. Try different keywords."
            record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text, answer_text=answer)
            self.store.persist_chat_log(record)
            return QueryResult(True, "No matches.", answer=answer, timestamps=[])

        record = ChatRecord(user_id=user_id, session_id=session_id, query_text=query_text,
                            answer_text=result.answer_text, retrieved_context_ids=result.context_object_ids)
        self.store.persist_chat_log(record)
        self.store.log_system_event(user_id, "QUERY", f"session={session_id}: {query_text!r}")
        return QueryResult(True, "OK", answer=result.answer_text, timestamps=result.timestamps)

    def update_ui_display(self, result: str) -> None:
        logger.debug("update_ui_display: %s", result)

    def get_chat_history(self, session_id: str) -> list[ChatRecord]:
        return self.store.get_chat_history(session_id)

    def clear_chat_history(self, session_id: str, user_id: int) -> bool:
        ok = self.store.delete_chat_log(session_id)
        if ok:
            self.vector_store.delete_by_session(session_id)
            self.store.log_system_event(user_id, "CLEAR_HISTORY", f"session={session_id}")
        return ok

    def export_pdf(self, session_id: str, user_id: int, log_ids: list[int],
                   include_evidence_frames: bool = True) -> str:
        all_records = self.store.get_chat_history(session_id)
        selected = [r for r in all_records if r.log_id in log_ids]
        evidence_frames = None
        if include_evidence_frames and selected:
            evidence_frames = self._build_evidence_frames(selected)
        path = self.pdf_exporter.generate_report(session_id, selected, evidence_frames)
        self.store.log_system_event(user_id, "PDF_EXPORT", f"session={session_id}, path={path}")
        return path

    def _build_evidence_frames(self, records: list[ChatRecord]) -> dict[int, EvidenceFrame]:
        """
        Uses the FULL annotated frame (bounding box + label drawn, square
        640x640 from the motion filter) rather than the tiny per-object
        crop — the crop alone is often a handful of pixels for a distant
        person, which looks heavily pixelated and gets stretched into an
        odd aspect ratio when forced into a fixed-width PDF image box. The
        full frame is both crisper AND more useful forensic evidence: it
        shows WHERE in the scene the detection was, not just an isolated
        sliver of it.
        """
        evidence: dict[int, EvidenceFrame] = {}
        for record in records:
            if not record.retrieved_context_ids:
                continue
            rows = self.store.fetch_timestamps(record.retrieved_context_ids[:1])
            if not rows:
                continue
            frame_path = rows[0].get("frame_image_path")
            if frame_path and Path(frame_path).exists():
                evidence[record.log_id] = EvidenceFrame(
                    image_path=frame_path, caption=f"{rows[0]['yolo_label']} @ frame {rows[0]['frame_index']}")
        return evidence

    def get_session_gallery(self, session_id: str) -> list[dict]:
        return self.store.get_session_detections(session_id)

    def get_vram_history(self, session_id: str) -> list[dict]:
        """[{"t": elapsed_sec, "used_mb": float, "total_mb": float}, ...]
        captured during this session's ingestion — empty list on a
        CPU-only host (no NVIDIA GPU to poll)."""
        return self._session_vram_history.get(session_id, [])

    def get_frame_stats(self, session_id: str) -> dict | None:
        """{"total_native_frames", "sampled_frame_count", "keyframe_count",
        "reduction_pct"} for the motion-filter reduction proof."""
        return self._session_frame_stats.get(session_id)

    def get_peak_vram_status(self, session_id: str) -> dict | None:
        """Compares the recorded peak against this project's own
        absolute_peak_vram_gb constraint (config.HardwareConfig) — the
        direct "did we meet our own design target" proof for the jury.

        Returns None when there's no real GPU reading to compare (CPU-only
        host, or nvidia-smi unavailable) — total_mb==0 is VRAMSentinel's
        explicit "nothing to report" sentinel (see _read_vram_via_nvidia_smi),
        not an actual zero-VRAM-used measurement, so those entries must be
        filtered out rather than treated as a (misleadingly perfect) reading.
        """
        real_readings = [h for h in self.get_vram_history(session_id) if h["total_mb"] > 0]
        if not real_readings:
            return None
        peak_mb = max(h["used_mb"] for h in real_readings)
        budget_mb = config.HARDWARE.absolute_peak_vram_gb * 1024
        return {
            "peak_mb": peak_mb,
            "peak_gb": round(peak_mb / 1024, 2),
            "budget_gb": config.HARDWARE.absolute_peak_vram_gb,
            "within_budget": peak_mb <= budget_mb,
        }

    def get_system_logs(self, user_id: int | None = None) -> list:
        return self.store.get_system_logs(user_id)

    def get_model_status(self) -> dict:
        phase = self.orchestrator.active_phase.value
        return {
            "gpu_lock_phase": phase,
            "models": [
                {"key": "yolo", "name": "YOLOv11n (CPU)", "loaded": self.yolo.is_loaded, "gpu": False},
                {"key": "encoder", "name": "Sentence-Encoder (CPU)", "loaded": self.encoder.is_loaded, "gpu": False},
                {"key": "blip", "name": "BLIP-Base (GPU)", "loaded": self.blip.is_loaded, "gpu": True},
                {"key": "qwen", "name": "Qwen2.5-1.5B (GPU)", "loaded": self.qwen.is_loaded, "gpu": True},
            ],
        }

    def get_vram_status(self) -> dict:
        self.orchestrator.vram_sentinel.check_vram()
        return {"vram_free_pct": self.orchestrator.vram_sentinel.get_free_vram_percent(),
               "locked": self.orchestrator.is_locked(), "active_phase": self.orchestrator.active_phase.value}

    def shutdown(self) -> None:
        self.orchestrator.vram_sentinel.stop()
        self.store.close()