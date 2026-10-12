"""
dto/entities.py
================
Plain data carriers mirroring SDS §4.1 (Class Diagram) and §5.2 (Schema
Tables) 1:1. These are intentionally dumb — no business logic, no I/O.
Any behavior belongs in core/storage/sqlite_store.py or the relevant
module, never here. Keeping entities anemic is what lets
SQLiteMetadataStore be the *only* class that knows SQL exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class BoundingBox:
    """<<DTO>> — SDS Class Diagram. One YOLO detection on one frame."""

    x: int
    y: int
    w: int
    h: int
    label: str
    confidence: float

    def as_xyxy(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.w, self.y + self.h


@dataclass
class User:
    """USER table — SDS §5.2.1."""

    username: str
    hashed_password: str
    user_id: Optional[int] = None
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VideoSession:
    """VIDEO_SESSION table — SDS §5.2.2."""

    user_id: int
    video_path: str
    fps: int
    total_frames: int
    session_id: str = field(default_factory=_new_uuid)
    upload_time: datetime = field(default_factory=datetime.utcnow)
    processing_status: str = "Pending"  # Pending|Processing|Completed|Failed


@dataclass
class Frame:
    """FRAME table — SDS §5.2.3."""

    session_id: str
    frame_index: int
    timestamp_sec: float
    frame_id: str = ""
    is_keyframe: bool = False
    frame_image_path: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.frame_id:
            self.frame_id = f"{self.session_id}_frame_{self.frame_index}"


@dataclass
class DetectedObject:
    """DETECTED_OBJECT table — SDS §5.2.4."""

    frame_id: str
    yolo_label: str
    confidence: float
    bbox: BoundingBox
    blip_caption: str
    object_id: str = field(default_factory=_new_uuid)
    crop_image_path: Optional[str] = None


@dataclass
class ChatRecord:
    """CHAT_LOG table — SDS §5.2.5."""

    user_id: int
    session_id: str
    query_text: str
    answer_text: str
    log_id: Optional[int] = None
    retrieved_context_ids: Optional[list[str]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SystemLog:
    """SYSTEM_LOG table — SDS §5.2.7."""

    action_type: str  # LOGIN | INGESTION | QUERY | PDF_EXPORT | CLEAR_HISTORY
    details: str
    user_id: Optional[int] = None
    log_id: Optional[int] = None
    event_time: datetime = field(default_factory=datetime.utcnow)
