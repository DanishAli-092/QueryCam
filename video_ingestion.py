"""
Stage 1: Video Ingestion
Extracts frames from an uploaded video at a fixed time interval.
"""

import cv2
from dataclasses import dataclass
from typing import List
import config


@dataclass
class ExtractedFrame:
    index: int
    timestamp_sec: float
    frame: "cv2.typing.MatLike"


def extract_frames(video_path: str,
                    interval_sec: float = config.FRAME_INTERVAL_SEC,
                    max_frames: int = config.MAX_FRAMES) -> List[ExtractedFrame]:
    """
    Reads a video file and extracts frames every `interval_sec` seconds.
    Returns a list of ExtractedFrame objects (raw BGR numpy arrays).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, int(fps * interval_sec))

    extracted = []
    frame_idx = 0
    saved_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            timestamp = frame_idx / fps
            extracted.append(ExtractedFrame(index=saved_idx, timestamp_sec=timestamp, frame=frame))
            saved_idx += 1

            if saved_idx >= max_frames:
                break

        frame_idx += 1

    cap.release()
    return extracted


def get_video_metadata(video_path: str) -> dict:
    """Quick metadata check â€” useful for displaying in the UI."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    meta = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    meta["duration_sec"] = meta["frame_count"] / meta["fps"] if meta["fps"] else 0
    cap.release()
    return meta

