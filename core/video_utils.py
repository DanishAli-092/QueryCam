from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("querycam.video_utils")


def ensure_browser_playable(src_path: str | Path) -> str:
    """st.video() only reliably plays H.264-in-MP4. Transcodes once to a
    cached H.264 MP4 next to the source file, reusing the cache on
    subsequent calls unless the source is newer. Never raises — falls
    back to the original path on any failure."""
    src_path = Path(src_path)
    preview_path = src_path.with_name(src_path.stem + "_preview.mp4")
    if preview_path.exists() and preview_path.stat().st_mtime >= src_path.stat().st_mtime:
        return str(preview_path)

    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y", "-i", str(src_path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
            str(preview_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0 or not preview_path.exists():
            logger.warning("Preview transcode failed (rc=%s): %s", result.returncode,
                           result.stderr.decode(errors="ignore")[-400:])
            return str(src_path)
        return str(preview_path)
    except Exception:  # noqa: BLE001
        logger.exception("Preview transcode raised — returning the original file.")
        return str(src_path)


def get_video_properties(video_path: str | Path) -> dict:
    """
    Reads container-level properties for display right after upload:
    resolution, FPS, total frame count, duration, and file size.
    Pure metadata read via cv2's header parsing — does not decode the
    video body, so this is fast even for large files.
    """
    import os
    import cv2

    video_path = Path(video_path)
    props = {
        "width": None, "height": None, "fps": None,
        "total_frames": None, "duration_sec": None,
        "file_size_mb": round(os.path.getsize(video_path) / (1024 * 1024), 2) if video_path.exists() else None,
    }
    cap = cv2.VideoCapture(str(video_path))
    try:
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            props.update({
                "width": width or None,
                "height": height or None,
                "fps": round(fps, 2) if fps else None,
                "total_frames": total_frames or None,
                "duration_sec": round(total_frames / fps, 2) if fps else None,
            })
    finally:
        cap.release()
    return props


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
