# """
# core/storage/sqlite_store.py
# =============================
# SQLiteMetadataStore — SDS §3.1 Module 6 (Storage Layer) / §4.1 Class Diagram.

# This is the ONLY class in the codebase allowed to hold a sqlite3
# connection or write raw SQL. QueryCamController and every other module
# talk to storage exclusively through this class's public methods, which
# is what keeps "swap ChromaDB for FAISS without touching other layers"
# (SDS §1.1 Justification for Layered Architecture) actually true in
# practice — SQLite could be swapped for Postgres here with zero changes
# outside this file.

# Thread-safety note: sqlite3 connections are not shared across threads
# by default. Streamlit reruns the whole script per interaction on one
# thread, so a single long-lived connection with check_same_thread=False
# plus WAL mode (set in schema.sql) is the pragmatic, correct choice here
# — it is NOT safe to naively reuse this pattern in a multi-process API
# server without a connection pool.
# """

# from __future__ import annotations

# import json
# import logging
# import sqlite3
# from contextlib import contextmanager
# from pathlib import Path
# from typing import Iterator, Optional

# from dto.entities import ChatRecord, DetectedObject, Frame, SystemLog, User, VideoSession

# logger = logging.getLogger("querycam.storage.sqlite")

# _SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# class SQLiteMetadataStore:
#     """db_path : str — SDS Class Diagram attribute."""

#     def __init__(self, db_path: str) -> None:
#         self.db_path = db_path
#         Path(db_path).parent.mkdir(parents=True, exist_ok=True)
#         self._conn = sqlite3.connect(db_path, check_same_thread=False)
#         self._conn.row_factory = sqlite3.Row
#         self._conn.execute("PRAGMA foreign_keys = ON;")
#         self._init_schema()

#     def _init_schema(self) -> None:
#         with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
#             self._conn.executescript(f.read())
#         self._conn.commit()
#         logger.info("SQLite schema verified/initialized at %s", self.db_path)

#     @contextmanager
#     def _cursor(self) -> Iterator[sqlite3.Cursor]:
#         cur = self._conn.cursor()
#         try:
#             yield cur
#             self._conn.commit()
#         except Exception:
#             self._conn.rollback()
#             raise
#         finally:
#             cur.close()

#     # ------------------------------------------------------------------ #
#     # USER — Security & Audit Module (SDS §3.1 Module 2)
#     # ------------------------------------------------------------------ #

#     def create_user(self, username: str, hashed_password: str) -> int:
#         with self._cursor() as cur:
#             cur.execute(
#                 "INSERT INTO USER (username, hashed_password) VALUES (?, ?)",
#                 (username, hashed_password),
#             )
#             return cur.lastrowid

#     def get_user_by_username(self, username: str) -> Optional[User]:
#         row = self._conn.execute(
#             "SELECT * FROM USER WHERE username = ?", (username,)
#         ).fetchone()
#         return self._row_to_user(row) if row else None

#     def record_failed_attempt(self, user_id: int) -> int:
#         """Increments failed_attempts and returns the new count."""
#         with self._cursor() as cur:
#             cur.execute(
#                 "UPDATE USER SET failed_attempts = failed_attempts + 1 WHERE user_id = ?",
#                 (user_id,),
#             )
#             cur.execute("SELECT failed_attempts FROM USER WHERE user_id = ?", (user_id,))
#             return cur.fetchone()[0]

#     def set_lockout(self, user_id: int, locked_until_iso: str) -> None:
#         with self._cursor() as cur:
#             cur.execute(
#                 "UPDATE USER SET locked_until = ? WHERE user_id = ?",
#                 (locked_until_iso, user_id),
#             )

#     def reset_attempts(self, user_id: int) -> None:
#         """SDS Class Diagram: User.reset_attempts()."""
#         with self._cursor() as cur:
#             cur.execute(
#                 "UPDATE USER SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
#                 (user_id,),
#             )

#     # ------------------------------------------------------------------ #
#     # VIDEO_SESSION / FRAME / DETECTED_OBJECT — Ingestion Module
#     # ------------------------------------------------------------------ #

#     def save_video_session(self, session: VideoSession) -> str:
#         with self._cursor() as cur:
#             cur.execute(
#                 """INSERT INTO VIDEO_SESSION
#                    (session_id, user_id, video_path, fps, total_frames, processing_status)
#                    VALUES (?, ?, ?, ?, ?, ?)""",
#                 (session.session_id, session.user_id, session.video_path,
#                  session.fps, session.total_frames, session.processing_status),
#             )
#         return session.session_id

#     def update_session_status(self, session_id: str, status: str) -> None:
#         with self._cursor() as cur:
#             cur.execute(
#                 "UPDATE VIDEO_SESSION SET processing_status = ? WHERE session_id = ?",
#                 (status, session_id),
#             )

#     def save_frame_metadata(self, frame: Frame) -> bool:
#         """SDS Class Diagram: SQLiteMetadataStore.save_frame_metadata() -> bool."""
#         try:
#             with self._cursor() as cur:
#                 cur.execute(
#                     """INSERT INTO FRAME
#                        (frame_id, session_id, frame_index, timestamp_sec, is_keyframe, frame_image_path)
#                        VALUES (?, ?, ?, ?, ?, ?)""",
#                     (frame.frame_id, frame.session_id, frame.frame_index,
#                      frame.timestamp_sec, int(frame.is_keyframe), frame.frame_image_path),
#                 )
#             return True
#         except sqlite3.Error:
#             logger.exception("save_frame_metadata failed for %s", frame.frame_id)
#             return False

#     def update_frame_image_path(self, frame_id: str, image_path: str) -> None:
#         """Called once YOLO has actually drawn boxes on a keyframe and saved
#         the annotated JPEG — save_frame_metadata() runs before detection,
#         so this path isn't known yet at insert time (US-06 / processed-frame
#         gallery in the UI)."""
#         with self._cursor() as cur:
#             cur.execute(
#                 "UPDATE FRAME SET frame_image_path = ? WHERE frame_id = ?",
#                 (image_path, frame_id),
#             )

#     def get_session_detections(self, session_id: str) -> list[dict]:
#         """
#         One row PER DETECTED_OBJECT (not grouped/concatenated) — each
#         carrying its own crop image, its own label+confidence, and its
#         parent frame's full annotated image + timestamp.

#         This replaces the old get_session_keyframe_gallery(), which used
#         GROUP_CONCAT to squash every object in a frame into one jumbled
#         caption string under a single image. The UI now pairs exactly
#         one caption with exactly one crop image — see render_ingestion_tab()
#         in app.py, which re-groups these flat rows back into
#         "one full frame + its own row of individually-captioned crops".
#         """
#         rows = self._conn.execute(
#             """SELECT do.object_id, do.yolo_label, do.confidence, do.crop_image_path,
#                       f.frame_id, f.frame_index, f.timestamp_sec, f.frame_image_path
#                FROM DETECTED_OBJECT do
#                JOIN FRAME f ON f.frame_id = do.frame_id
#                WHERE f.session_id = ? AND f.frame_image_path IS NOT NULL
#                ORDER BY f.timestamp_sec ASC, do.confidence DESC""",
#             (session_id,),
#         ).fetchall()
#         return [dict(r) for r in rows]

#     def save_detected_object(self, obj: DetectedObject) -> bool:
#         try:
#             with self._cursor() as cur:
#                 cur.execute(
#                     """INSERT INTO DETECTED_OBJECT
#                        (object_id, frame_id, yolo_label, confidence,
#                         bbox_x, bbox_y, bbox_w, bbox_h, crop_image_path, blip_caption)
#                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
#                     (obj.object_id, obj.frame_id, obj.yolo_label, obj.confidence,
#                      obj.bbox.x, obj.bbox.y, obj.bbox.w, obj.bbox.h,
#                      obj.crop_image_path, obj.blip_caption),
#                 )
#             return True
#         except sqlite3.Error:
#             logger.exception("save_detected_object failed for %s", obj.object_id)
#             return False

#     def fetch_timestamps(self, object_ids: list[str]) -> list[dict]:
#         """
#         SDS Class Diagram: SQLiteMetadataStore.fetch_timestamps() -> str
#         (returns structured rows; the RAG module formats these into the
#         display string handed to Qwen and the UI — see SDS Sequence
#         Diagram §4.2.2 step 11 'fetch_timestamps() -> Timestamps').
#         """
#         if not object_ids:
#             return []
#         placeholders = ",".join("?" for _ in object_ids)
#         rows = self._conn.execute(
#             f"""SELECT do.object_id, do.yolo_label, do.blip_caption, do.crop_image_path,
#                        f.session_id, f.frame_index, f.timestamp_sec
#                 FROM DETECTED_OBJECT do
#                 JOIN FRAME f ON f.frame_id = do.frame_id
#                 WHERE do.object_id IN ({placeholders})
#                 ORDER BY f.timestamp_sec ASC""",
#             object_ids,
#         ).fetchall()
#         return [dict(r) for r in rows]

#     # ------------------------------------------------------------------ #
#     # CHAT_LOG — RAG audit trail
#     # ------------------------------------------------------------------ #

#     def persist_chat_log(self, record: ChatRecord) -> int:
#         """SDS Class Diagram: SQLiteMetadataStore.persist_chat_log()."""
#         context_json = (
#             json.dumps(record.retrieved_context_ids)
#             if record.retrieved_context_ids is not None else None
#         )
#         with self._cursor() as cur:
#             cur.execute(
#                 """INSERT INTO CHAT_LOG
#                    (user_id, session_id, query_text, answer_text, retrieved_context_ids)
#                    VALUES (?, ?, ?, ?, ?)""",
#                 (record.user_id, record.session_id, record.query_text,
#                  record.answer_text, context_json),
#             )
#             return cur.lastrowid

#     def get_chat_history(self, session_id: str) -> list[ChatRecord]:
#         rows = self._conn.execute(
#             "SELECT * FROM CHAT_LOG WHERE session_id = ? ORDER BY timestamp ASC",
#             (session_id,),
#         ).fetchall()
#         return [self._row_to_chat_record(r) for r in rows]

#     def delete_chat_log(self, session_id: str) -> bool:
#         """SDS Class Diagram: SQLiteMetadataStore.delete_chat_log() -> bool.
#         Backs US-10 'Chat History View/Clear'."""
#         try:
#             with self._cursor() as cur:
#                 cur.execute("DELETE FROM CHAT_LOG WHERE session_id = ?", (session_id,))
#             return True
#         except sqlite3.Error:
#             logger.exception("delete_chat_log failed for session=%s", session_id)
#             return False

#     # ------------------------------------------------------------------ #
#     # SYSTEM_LOG — audit trail (US-12)
#     # ------------------------------------------------------------------ #

#     def log_system_event(self, user_id: Optional[int], action: str, details: str) -> None:
#         """SDS Class Diagram: log_system_event(user_id: int, action: str, details: str) -> void."""
#         with self._cursor() as cur:
#             cur.execute(
#                 "INSERT INTO SYSTEM_LOG (user_id, action_type, details) VALUES (?, ?, ?)",
#                 (user_id, action, details),
#             )

#     def get_system_logs(self, user_id: Optional[int] = None) -> list[SystemLog]:
#         if user_id is not None:
#             rows = self._conn.execute(
#                 "SELECT * FROM SYSTEM_LOG WHERE user_id = ? ORDER BY event_time DESC",
#                 (user_id,),
#             ).fetchall()
#         else:
#             rows = self._conn.execute(
#                 "SELECT * FROM SYSTEM_LOG ORDER BY event_time DESC"
#             ).fetchall()
#         return [self._row_to_system_log(r) for r in rows]

#     # ------------------------------------------------------------------ #
#     # CHROMADB_VECTOR bridge table
#     # ------------------------------------------------------------------ #

#     def link_vector(self, vector_id: str, object_id: str,
#                      embedding: Optional[list[float]] = None,
#                      distance_metric: str = "cosine") -> None:
#         with self._cursor() as cur:
#             cur.execute(
#                 """INSERT INTO CHROMADB_VECTOR (vector_id, object_id, embedding_768d, distance_metric)
#                    VALUES (?, ?, ?, ?)""",
#                 (vector_id, object_id, json.dumps(embedding) if embedding else None, distance_metric),
#             )

#     # ------------------------------------------------------------------ #
#     # Row -> dataclass mapping helpers
#     # ------------------------------------------------------------------ #

#     @staticmethod
#     def _row_to_user(row: sqlite3.Row) -> User:
#         return User(
#             user_id=row["user_id"], username=row["username"],
#             hashed_password=row["hashed_password"],
#             failed_attempts=row["failed_attempts"], locked_until=row["locked_until"],
#             created_at=row["created_at"],
#         )

#     @staticmethod
#     def _row_to_chat_record(row: sqlite3.Row) -> ChatRecord:
#         ctx = json.loads(row["retrieved_context_ids"]) if row["retrieved_context_ids"] else None
#         return ChatRecord(
#             log_id=row["log_id"], user_id=row["user_id"], session_id=row["session_id"],
#             query_text=row["query_text"], answer_text=row["answer_text"],
#             retrieved_context_ids=ctx, timestamp=row["timestamp"],
#         )

#     @staticmethod
#     def _row_to_system_log(row: sqlite3.Row) -> SystemLog:
#         return SystemLog(
#             log_id=row["log_id"], user_id=row["user_id"], action_type=row["action_type"],
#             details=row["details"], event_time=row["event_time"],
#         )

#     def close(self) -> None:
#         self._conn.close()

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from dto.entities import ChatRecord, DetectedObject, Frame, SystemLog, User, VideoSession

logger = logging.getLogger("querycam.storage.sqlite")

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class SQLiteMetadataStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            self._conn.executescript(f.read())
        self._conn.commit()
        logger.info("SQLite schema verified/initialized at %s", self.db_path)

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # USER
    def create_user(self, username: str, hashed_password: str) -> int:
        with self._cursor() as cur:
            cur.execute("INSERT INTO USER (username, hashed_password) VALUES (?, ?)",
                        (username, hashed_password))
            return cur.lastrowid

    def get_user_by_username(self, username: str) -> Optional[User]:
        row = self._conn.execute("SELECT * FROM USER WHERE username = ?", (username,)).fetchone()
        return self._row_to_user(row) if row else None

    def record_failed_attempt(self, user_id: int) -> int:
        with self._cursor() as cur:
            cur.execute("UPDATE USER SET failed_attempts = failed_attempts + 1 WHERE user_id = ?", (user_id,))
            cur.execute("SELECT failed_attempts FROM USER WHERE user_id = ?", (user_id,))
            return cur.fetchone()[0]

    def set_lockout(self, user_id: int, locked_until_iso: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE USER SET locked_until = ? WHERE user_id = ?", (locked_until_iso, user_id))

    def reset_attempts(self, user_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE USER SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?", (user_id,))

    # VIDEO_SESSION / FRAME / DETECTED_OBJECT
    def save_video_session(self, session: VideoSession) -> str:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO VIDEO_SESSION
                   (session_id, user_id, video_path, fps, total_frames, processing_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session.session_id, session.user_id, session.video_path,
                 session.fps, session.total_frames, session.processing_status),
            )
        return session.session_id

    def update_session_status(self, session_id: str, status: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE VIDEO_SESSION SET processing_status = ? WHERE session_id = ?",
                        (status, session_id))

    def save_frame_metadata(self, frame: Frame) -> bool:
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT INTO FRAME
                       (frame_id, session_id, frame_index, timestamp_sec, is_keyframe, frame_image_path)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (frame.frame_id, frame.session_id, frame.frame_index,
                     frame.timestamp_sec, int(frame.is_keyframe), frame.frame_image_path),
                )
            return True
        except sqlite3.Error:
            logger.exception("save_frame_metadata failed for %s", frame.frame_id)
            return False

    def update_frame_image_path(self, frame_id: str, image_path: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE FRAME SET frame_image_path = ? WHERE frame_id = ?", (image_path, frame_id))

    def save_detected_object(self, obj: DetectedObject) -> bool:
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT INTO DETECTED_OBJECT
                       (object_id, frame_id, yolo_label, confidence,
                        bbox_x, bbox_y, bbox_w, bbox_h, crop_image_path, blip_caption)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (obj.object_id, obj.frame_id, obj.yolo_label, obj.confidence,
                     obj.bbox.x, obj.bbox.y, obj.bbox.w, obj.bbox.h,
                     obj.crop_image_path, obj.blip_caption),
                )
            return True
        except sqlite3.Error:
            logger.exception("save_detected_object failed for %s", obj.object_id)
            return False

    def fetch_timestamps(self, object_ids: list[str]) -> list[dict]:
        if not object_ids:
            return []
        placeholders = ",".join("?" for _ in object_ids)
        rows = self._conn.execute(
            f"""SELECT do.object_id, do.yolo_label, do.blip_caption, do.crop_image_path,
                       f.session_id, f.frame_index, f.timestamp_sec, f.frame_image_path
                FROM DETECTED_OBJECT do
                JOIN FRAME f ON f.frame_id = do.frame_id
                WHERE do.object_id IN ({placeholders})
                ORDER BY f.timestamp_sec ASC""",
            object_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_detections(self, session_id: str) -> list[dict]:
        """One row PER DETECTED_OBJECT (not grouped) — each with its own
        crop image, its own label+confidence, and its parent frame's full
        annotated image + timestamp. Powers the Processed Results gallery
        in app.py, which pairs exactly one caption with exactly one image."""
        rows = self._conn.execute(
            """SELECT do.object_id, do.yolo_label, do.confidence, do.crop_image_path,
                      f.frame_id, f.frame_index, f.timestamp_sec, f.frame_image_path
               FROM DETECTED_OBJECT do
               JOIN FRAME f ON f.frame_id = do.frame_id
               WHERE f.session_id = ? AND f.frame_image_path IS NOT NULL
               ORDER BY f.timestamp_sec ASC, do.confidence DESC""",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # CHAT_LOG
    def persist_chat_log(self, record: ChatRecord) -> int:
        context_json = (json.dumps(record.retrieved_context_ids)
                        if record.retrieved_context_ids is not None else None)
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO CHAT_LOG
                   (user_id, session_id, query_text, answer_text, retrieved_context_ids)
                   VALUES (?, ?, ?, ?, ?)""",
                (record.user_id, record.session_id, record.query_text,
                 record.answer_text, context_json),
            )
            return cur.lastrowid

    def get_chat_history(self, session_id: str) -> list[ChatRecord]:
        rows = self._conn.execute(
            "SELECT * FROM CHAT_LOG WHERE session_id = ? ORDER BY timestamp ASC", (session_id,),
        ).fetchall()
        return [self._row_to_chat_record(r) for r in rows]

    def delete_chat_log(self, session_id: str) -> bool:
        try:
            with self._cursor() as cur:
                cur.execute("DELETE FROM CHAT_LOG WHERE session_id = ?", (session_id,))
            return True
        except sqlite3.Error:
            logger.exception("delete_chat_log failed for session=%s", session_id)
            return False

    # SYSTEM_LOG
    def log_system_event(self, user_id: Optional[int], action: str, details: str) -> None:
        with self._cursor() as cur:
            cur.execute("INSERT INTO SYSTEM_LOG (user_id, action_type, details) VALUES (?, ?, ?)",
                        (user_id, action, details))

    def get_system_logs(self, user_id: Optional[int] = None) -> list[SystemLog]:
        if user_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM SYSTEM_LOG WHERE user_id = ? ORDER BY event_time DESC", (user_id,),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM SYSTEM_LOG ORDER BY event_time DESC").fetchall()
        return [self._row_to_system_log(r) for r in rows]

    # CHROMADB_VECTOR bridge
    def link_vector(self, vector_id: str, object_id: str,
                     embedding: Optional[list[float]] = None,
                     distance_metric: str = "cosine") -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO CHROMADB_VECTOR (vector_id, object_id, embedding_768d, distance_metric)
                   VALUES (?, ?, ?, ?)""",
                (vector_id, object_id, json.dumps(embedding) if embedding else None, distance_metric),
            )

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(user_id=row["user_id"], username=row["username"],
                    hashed_password=row["hashed_password"], failed_attempts=row["failed_attempts"],
                    locked_until=row["locked_until"], created_at=row["created_at"])

    @staticmethod
    def _row_to_chat_record(row: sqlite3.Row) -> ChatRecord:
        ctx = json.loads(row["retrieved_context_ids"]) if row["retrieved_context_ids"] else None
        return ChatRecord(log_id=row["log_id"], user_id=row["user_id"], session_id=row["session_id"],
                          query_text=row["query_text"], answer_text=row["answer_text"],
                          retrieved_context_ids=ctx, timestamp=row["timestamp"])

    @staticmethod
    def _row_to_system_log(row: sqlite3.Row) -> SystemLog:
        return SystemLog(log_id=row["log_id"], user_id=row["user_id"], action_type=row["action_type"],
                         details=row["details"], event_time=row["event_time"])

    def close(self) -> None:
        self._conn.close()