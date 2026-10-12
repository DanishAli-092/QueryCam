"""
core/ingestion/motion_filter.py
=================================
OpenCVMotionFilter — SDS §3.1 Module 4 (Data Ingestion & Filtration) /
§4.1 Class Diagram.

"Validate local MP4/AVI files and parse video streams. Calculates exact
millisecond timestamps. Applies structural pixel-differencing to
aggressively discard temporally redundant static frames (targeting a
>=60% reduction) before they reach the AI pipeline."

Two public methods, matching the Class Diagram exactly:
    extract_frames(video_path: str) -> List[Frame]
    compute_timestamps(video_path: str) -> List[str]

Design note on the two-pass split: extract_frames() does the expensive
full decode + resize + pixel-diff pass (this is where the >=60%
keyframe-reduction target is enforced). compute_timestamps() is
deliberately a *cheap, metadata-only* second pass — it reads only
CAP_PROP_FPS / CAP_PROP_FRAME_COUNT (no frame decoding) so calling it
separately, as the Sequence Diagram (§4.2.1, steps 7 & 9) shows, never
means paying for two full video decodes.

Execution Environment: CPU-Pinned (SDS §3.1 Module 4) — this class
never touches CUDA. It is pure OpenCV + NumPy.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

import config
from dto.entities import Frame

logger = logging.getLogger("querycam.ingestion.motion_filter")

_SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


class VideoValidationError(ValueError):
    """Raised when an uploaded file fails the US-03/US-04 validity check."""


class OpenCVMotionFilter:
    """fps_target: int, diff_threshold: float — SDS Class Diagram attributes."""

    def __init__(
        self,
        fps_target: int = config.PIPELINE.target_fps,
        diff_threshold: float = config.PIPELINE.motion_diff_threshold,
        frame_size: tuple[int, int] = config.PIPELINE.frame_size,
    ) -> None:
        self.fps_target = fps_target
        self.diff_threshold = diff_threshold
        self.frame_size = frame_size
        # frame_id -> resized BGR ndarray, populated only for detected
        # keyframes so the AI pipeline (YOLO/BLIP loop) never re-decodes
        # the video — this is the "Batch Ingestion" optimization mandate.
        self._keyframe_cache: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------ #
    # Validation (US-03: "ingests local MP4/AVI files ... without any
    # external network calls")
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_video(video_path: str) -> None:
        path = Path(video_path)
        if not path.exists():
            raise VideoValidationError(f"File not found: {video_path}")
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise VideoValidationError(
                f"Unsupported container '{path.suffix}'. Expected one of {_SUPPORTED_EXTENSIONS}."
            )
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            raise VideoValidationError(f"OpenCV could not open/decode: {video_path}")
        cap.release()

    # ------------------------------------------------------------------ #
    # extract_frames() -> List[Frame] — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def extract_frames(self, video_path: str, session_id: str) -> list[Frame]:
        """
        Single decode pass:
          1. Downsample native FPS -> self.fps_target (temporal downsampling).
          2. Resize every sampled frame to self.frame_size (640x640).
          3. Structural pixel-differencing against the previous *sampled*
             frame; frames whose mean absolute difference exceeds
             diff_threshold are flagged is_keyframe=True.
          4. Only keyframe pixel data is cached in memory (self._keyframe_cache)
             for the downstream YOLO pass — static frames are discarded
             immediately to respect the 16GB RAM ceiling.

        Returns metadata-only Frame DTOs; SQLiteMetadataStore.save_frame_metadata()
        persists each one (see QueryCamController.process_video_ingestion()).
        """
        self.validate_video(video_path)
        self._keyframe_cache.clear()

        cap = cv2.VideoCapture(video_path)
        native_fps = cap.get(cv2.CAP_PROP_FPS) or self.fps_target
        sample_stride = max(1, round(native_fps / self.fps_target))

        frames: list[Frame] = []
        prev_gray: np.ndarray | None = None
        native_index = 0
        sampled_index = 0
        keyframe_count = 0

        while True:
            ok, raw_frame = cap.read()
            if not ok:
                break

            if native_index % sample_stride == 0:
                resized = cv2.resize(raw_frame, self.frame_size, interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)

                is_keyframe = prev_gray is None or self._is_motion_detected(prev_gray, gray)
                prev_gray = gray

                timestamp_sec = native_index / native_fps
                frame = Frame(
                    session_id=session_id,
                    frame_index=sampled_index,
                    timestamp_sec=round(timestamp_sec, 3),
                    is_keyframe=is_keyframe,
                )

                if is_keyframe:
                    self._keyframe_cache[frame.frame_id] = resized
                    keyframe_count += 1

                frames.append(frame)
                sampled_index += 1

            native_index += 1

        cap.release()

        reduction_pct = 1.0 - (keyframe_count / max(sampled_index, 1))
        logger.info(
            "extract_frames(%s): %d sampled @ %dFPS -> %d keyframes (%.1f%% discarded, target >=%.0f%%)",
            Path(video_path).name, sampled_index, self.fps_target, keyframe_count,
            reduction_pct * 100, config.PIPELINE.min_keyframe_reduction_pct * 100,
        )
        if sampled_index > 0 and reduction_pct < config.PIPELINE.min_keyframe_reduction_pct:
            logger.warning(
                "Motion filter reduction (%.1f%%) fell short of the SDS >=60%% target "
                "— consider raising diff_threshold for this footage.", reduction_pct * 100,
            )
        return frames

    def get_keyframe_array(self, frame_id: str) -> np.ndarray | None:
        """Retrieves the cached pixel array for a keyframe produced by the
        most recent extract_frames() call — used by YOLOv11Detector.detect()
        in the ingestion loop so the video is never re-opened."""
        return self._keyframe_cache.get(frame_id)

    def iter_keyframes(self, frames: list[Frame]) -> Iterator[tuple[Frame, np.ndarray]]:
        """Convenience generator over only the flagged keyframes, in order —
        exactly the population the SDS Sequence Diagram's 'loop / AI Pipeline
        on Keyframes' block iterates over."""
        for f in frames:
            if f.is_keyframe:
                arr = self._keyframe_cache.get(f.frame_id)
                if arr is not None:
                    yield f, arr

    # ------------------------------------------------------------------ #
    # compute_timestamps() -> List[str] — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def compute_timestamps(self, video_path: str) -> list[str]:
        """
        Cheap metadata-only pass: derives one HH:MM:SS.mmm string per
        sampled frame index directly from native FPS / frame count,
        without decoding a single frame. This is the millisecond-precision
        timestamp source referenced in US-04 and persisted to SQLite's
        FRAME.timestamp_sec (this method's formatted-string output is what
        the Streamlit UI displays; the raw float is what extract_frames()
        already wrote per-frame).
        """
        cap = cv2.VideoCapture(video_path)
        native_fps = cap.get(cv2.CAP_PROP_FPS) or self.fps_target
        total_native_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        sample_stride = max(1, round(native_fps / self.fps_target))
        timestamps: list[str] = []
        for native_index in range(0, total_native_frames, sample_stride):
            timestamps.append(self._format_timestamp(native_index / native_fps))
        return timestamps

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        millis = int(round((seconds - int(seconds)) * 1000))
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"

    def _is_motion_detected(self, prev_gray: np.ndarray, curr_gray: np.ndarray) -> bool:
        diff = cv2.absdiff(prev_gray, curr_gray)
        mean_diff = float(np.mean(diff))
        return mean_diff > self.diff_threshold
