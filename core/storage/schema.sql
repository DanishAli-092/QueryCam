-- schema.sql
-- Query-Cam relational schema — SDS §5. Database Design (ERD)
-- Every table, column, constraint, and index below is a literal
-- transcription of SDS §5.2.1 - §5.2.7. Do not diverge from this
-- without updating the SDS Schema Tables section to match.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;   -- concurrent Streamlit reads while ingestion writes

-- 5.2.1 USER — Authentication & Security
CREATE TABLE IF NOT EXISTS USER (
    user_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE,
    hashed_password   TEXT NOT NULL,
    failed_attempts   INTEGER NOT NULL DEFAULT 0,
    locked_until      DATETIME NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_user_username ON USER (username);

-- 5.2.2 VIDEO_SESSION — Video Upload & Processing Metadata
CREATE TABLE IF NOT EXISTS VIDEO_SESSION (
    session_id         TEXT PRIMARY KEY,
    user_id            INTEGER NOT NULL,
    video_path         TEXT NOT NULL,
    fps                INTEGER NOT NULL,
    total_frames       INTEGER NOT NULL,
    upload_time        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_status  TEXT NOT NULL DEFAULT 'Pending'
                       CHECK (processing_status IN ('Pending','Processing','Completed','Failed')),
    FOREIGN KEY (user_id) REFERENCES USER(user_id)
);
CREATE INDEX IF NOT EXISTS idx_session_user   ON VIDEO_SESSION (user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_session_status ON VIDEO_SESSION (processing_status);

-- 5.2.3 FRAME — Individual Frame Metadata
CREATE TABLE IF NOT EXISTS FRAME (
    frame_id          TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    frame_index       INTEGER NOT NULL,
    timestamp_sec     REAL NOT NULL,
    is_keyframe       BOOLEAN NOT NULL DEFAULT 0,
    frame_image_path  TEXT NULL,
    FOREIGN KEY (session_id) REFERENCES VIDEO_SESSION(session_id)
);
CREATE INDEX IF NOT EXISTS idx_frame_session   ON FRAME (session_id, frame_index);
CREATE INDEX IF NOT EXISTS idx_frame_keyframe  ON FRAME (session_id, is_keyframe);

-- 5.2.4 DETECTED_OBJECT — YOLO Detection + BLIP Caption
CREATE TABLE IF NOT EXISTS DETECTED_OBJECT (
    object_id         TEXT PRIMARY KEY,
    frame_id          TEXT NOT NULL,
    yolo_label        TEXT NOT NULL,
    confidence        REAL NOT NULL,
    bbox_x            INTEGER NOT NULL,
    bbox_y            INTEGER NOT NULL,
    bbox_w            INTEGER NOT NULL,
    bbox_h            INTEGER NOT NULL,
    crop_image_path   TEXT NULL,
    blip_caption      TEXT NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES FRAME(frame_id)
);
CREATE INDEX IF NOT EXISTS idx_object_frame ON DETECTED_OBJECT (frame_id, object_id);
CREATE INDEX IF NOT EXISTS idx_object_label ON DETECTED_OBJECT (yolo_label);

-- 5.2.5 CHAT_LOG — User Query & RAG Audit Trail
CREATE TABLE IF NOT EXISTS CHAT_LOG (
    log_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL,
    session_id              TEXT NOT NULL,
    query_text              TEXT NOT NULL,
    answer_text             TEXT NOT NULL,
    retrieved_context_ids   TEXT NULL,  -- JSON array, validated via json_valid()
    timestamp               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USER(user_id),
    FOREIGN KEY (session_id) REFERENCES VIDEO_SESSION(session_id),
    CHECK (retrieved_context_ids IS NULL OR json_valid(retrieved_context_ids))
);
CREATE INDEX IF NOT EXISTS idx_chat_user      ON CHAT_LOG (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_session   ON CHAT_LOG (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON CHAT_LOG (timestamp);

-- 5.2.6 CHROMADB_VECTOR — Logical Bridge to Vector Store
-- Vectors physically live in ChromaDB; this table only carries the
-- object_id <-> vector_id mapping (plus an optional JSON copy for audit).
CREATE TABLE IF NOT EXISTS CHROMADB_VECTOR (
    vector_id        TEXT PRIMARY KEY,
    object_id        TEXT NOT NULL UNIQUE,
    embedding_768d    TEXT NULL,  -- JSON array, optional reference copy
    distance_metric   TEXT NOT NULL DEFAULT 'cosine',
    FOREIGN KEY (object_id) REFERENCES DETECTED_OBJECT(object_id),
    CHECK (embedding_768d IS NULL OR json_valid(embedding_768d))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vector_object ON CHROMADB_VECTOR (object_id);

-- 5.2.7 SYSTEM_LOG — System Audit Trail
CREATE TABLE IF NOT EXISTS SYSTEM_LOG (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NULL,
    action_type  VARCHAR(50) NOT NULL,
    details      TEXT NULL,
    event_time   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USER(user_id)
);
CREATE INDEX IF NOT EXISTS idx_syslog_user   ON SYSTEM_LOG (user_id);
CREATE INDEX IF NOT EXISTS idx_syslog_action ON SYSTEM_LOG (action_type);
CREATE INDEX IF NOT EXISTS idx_syslog_time   ON SYSTEM_LOG (event_time);
