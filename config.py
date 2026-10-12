# """
# config.py
# =========
# Single source of truth for every hardware ceiling, path, and tunable
# constant referenced across Query-Cam's six modules (SDS §3.1).

# Nothing in core/ should hard-code a magic number that appears here —
# this is what lets the jury panel (and future-you) audit the 4GB VRAM
# budget in one glance, and what lets Module Decomposition (SDS §3.1)
# claim "loosely coupled" with a straight face.
# """

# from __future__ import annotations

# import os
# from dataclasses import dataclass, field
# from pathlib import Path

# # --------------------------------------------------------------------------- #
# # Filesystem layout (all local — zero network I/O anywhere in this app)
# # --------------------------------------------------------------------------- #
# BASE_DIR = Path(__file__).resolve().parent
# DATA_DIR = BASE_DIR / "data"
# UPLOAD_DIR = DATA_DIR / "uploads"
# CROP_DIR = DATA_DIR / "crops"
# DB_DIR = DATA_DIR / "db"
# VECTOR_STORE_DIR = DATA_DIR / "vector_store"
# MODEL_WEIGHTS_DIR = DATA_DIR / "weights"

# SQLITE_DB_PATH = DB_DIR / "querycam.sqlite3"
# CHROMA_PERSIST_PATH = str(VECTOR_STORE_DIR)

# for _d in (UPLOAD_DIR, CROP_DIR, DB_DIR, VECTOR_STORE_DIR, MODEL_WEIGHTS_DIR):
#     _d.mkdir(parents=True, exist_ok=True)


# @dataclass(frozen=True)
# class HardwareConfig:
#     """Edge-computing ceiling — SDS §1 Hardware Constraints."""

#     total_vram_gb: float = 4.0
#     total_ram_gb: float = 16.0

#     # VRAM Sentinel — SDS §3.2.C: hard cap at 92%, polled every 500ms.
#     vram_safety_cap_pct: float = 0.92
#     vram_poll_interval_sec: float = 0.5

#     # "Active peak allocation must never breach 3.20GB" — architect directive.
#     absolute_peak_vram_gb: float = 3.20

#     # Maxwell SM 5.0 has no native fp16 tensor cores, but BLIP-Base is loaded
#     # at torch.float16 anyway purely to halve its VRAM footprint (weight
#     # storage benefit still applies even without fp16 compute acceleration).
#     cuda_compute_capability: str = "5.0"


# @dataclass(frozen=True)
# class PipelineConfig:
#     """Ingestion pipeline tunables — SDS §3.1 Module 4 (Data Ingestion)."""

#     target_fps: int = 5                 # 5 FPS temporal downsampling
#     frame_size: tuple[int, int] = (640, 640)
#     motion_diff_threshold: float = 25.0  # pixel-differencing sensitivity
#     min_keyframe_reduction_pct: float = 0.60  # SDS target: >=60% discard rate

#     yolo_confidence_threshold: float = 0.45
#     # Fine-tuned YOLO11n export order (Colab: best.pt -> ONNX, opset=17):
#     # class 0 = gun, class 1 = abandoned_bag, class 2 = violence.
#     # ONNX output shape is (1, 4 + len(yolo_classes), num_anchors) — this
#     # tuple's length MUST equal the model's actual class count, or
#     # YOLOv11Detector will silently mislabel every detection.
#     # yolo_classes: tuple[str, ...] = (
#     #     "gun",
#     #     "abandoned_bag",
#     #     "violence",
#     # )
#         # FINE-TUNED (baad mein wapas lagana):
#     # yolo_classes = ("gun", "abandoned_bag", "violence")

#     # PRETRAINED COCO (temporary testing):
#     yolo_classes: tuple[str, ...] = (
#         "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
#         "truck", "boat", "traffic light", "fire hydrant", "stop sign",
#         "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
#         "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
#         "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
#         "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
#         "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
#         "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
#         "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
#         "couch", "potted plant", "bed", "dining table", "toilet", "tv",
#         "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
#         "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
#         "scissors", "teddy bear", "hair drier", "toothbrush",
#     )

#     embedding_dimension: int = 384       # all-MiniLM-L6-v2 output dim
#     rag_top_k: int = 5

#     qwen_context_window: int = 4096
#     qwen_max_new_tokens: int = 512


# @dataclass(frozen=True)
# class SecurityConfig:
#     """Security & Audit Module — SDS §3.1 Module 2."""

#     max_failed_attempts: int = 3
#     lockout_duration_minutes: int = 5
#     bcrypt_rounds: int = 12


# @dataclass(frozen=True)
# class ModelPaths:
#     yolo_onnx: Path = MODEL_WEIGHTS_DIR / "yolov11n_forensic_finetuned.onnx"
#     blip_model_id: str = "Salesforce/blip-image-captioning-base"
#     sentence_transformer_id: str = "sentence-transformers/all-MiniLM-L6-v2"
#     qwen_gguf: Path = MODEL_WEIGHTS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"


# HARDWARE = HardwareConfig()
# PIPELINE = PipelineConfig()
# SECURITY = SecurityConfig()
# MODELS = ModelPaths()

# # Force CPU-only mode regardless of detected CUDA (useful for grading on a
# # jury laptop with no NVIDIA GPU) — CPU Fallback Logic is still evaluated
# # per-model even when this is False; this is an explicit override switch.
# FORCE_CPU_ONLY: bool = os.environ.get("QUERYCAM_FORCE_CPU", "0") == "1"

"""
config.py
=========
Single source of truth for every hardware ceiling, path, and tunable
constant referenced across Query-Cam's six modules (SDS §3.1).

Nothing in core/ should hard-code a magic number that appears here —
this is what lets the jury panel (and future-you) audit the 4GB VRAM
budget in one glance, and what lets Module Decomposition (SDS §3.1)
claim "loosely coupled" with a straight face.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Filesystem layout (all local — zero network I/O anywhere in this app)
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CROP_DIR = DATA_DIR / "crops"
DB_DIR = DATA_DIR / "db"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
MODEL_WEIGHTS_DIR = DATA_DIR / "weights"
PROCESSED_VIDEO_DIR = DATA_DIR / "processed_videos"

SQLITE_DB_PATH = DB_DIR / "querycam.sqlite3"
CHROMA_PERSIST_PATH = str(VECTOR_STORE_DIR)

for _d in (UPLOAD_DIR, CROP_DIR, DB_DIR, VECTOR_STORE_DIR, MODEL_WEIGHTS_DIR, PROCESSED_VIDEO_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class HardwareConfig:
    """Edge-computing ceiling — SDS §1 Hardware Constraints."""

    total_vram_gb: float = 4.0
    total_ram_gb: float = 16.0

    # VRAM Sentinel — SDS §3.2.C: hard cap at 92%, polled every 500ms.
    vram_safety_cap_pct: float = 0.92
    vram_poll_interval_sec: float = 0.5

    # "Active peak allocation must never breach 3.20GB" — architect directive.
    absolute_peak_vram_gb: float = 3.20

    # Maxwell SM 5.0 has no native fp16 tensor cores, but BLIP-Base is loaded
    # at torch.float16 anyway purely to halve its VRAM footprint (weight
    # storage benefit still applies even without fp16 compute acceleration).
    cuda_compute_capability: str = "5.0"


@dataclass(frozen=True)
class PipelineConfig:
    """Ingestion pipeline tunables — SDS §3.1 Module 4 (Data Ingestion)."""

    target_fps: int = 5                 # 5 FPS temporal downsampling
    frame_size: tuple[int, int] = (640, 640)
    motion_diff_threshold: float = 25.0  # pixel-differencing sensitivity
    min_keyframe_reduction_pct: float = 0.60  # SDS target: >=60% discard rate

    yolo_confidence_threshold: float = 0.45
    # Fine-tuned YOLO11n export order (Colab: best.pt -> ONNX, opset=17):
    # class 0 = gun, class 1 = abandoned_bag, class 2 = violence.
    # ONNX output shape is (1, 4 + len(yolo_classes), num_anchors) — this
    # tuple's length MUST equal the model's actual class count, or
    # YOLOv11Detector will silently mislabel every detection.
    yolo_classes: tuple[str, ...] = (
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
            "truck", "boat", "traffic light", "fire hydrant", "stop sign",
            "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
            "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
            "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
            "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
            "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
            "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
            "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
            "couch", "potted plant", "bed", "dining table", "toilet", "tv",
            "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
            "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
            "scissors", "teddy bear", "hair drier", "toothbrush",
        )

    embedding_dimension: int = 384       # all-MiniLM-L6-v2 output dim
    rag_top_k: int = 5

    qwen_context_window: int = 4096
    qwen_max_new_tokens: int = 512


@dataclass(frozen=True)
class SecurityConfig:
    """Security & Audit Module — SDS §3.1 Module 2."""

    max_failed_attempts: int = 3
    lockout_duration_minutes: int = 5
    bcrypt_rounds: int = 12


@dataclass(frozen=True)
class ModelPaths:
    yolo_onnx: Path = MODEL_WEIGHTS_DIR / "yolov11n_forensic_finetuned.onnx"
    blip_model_id: str = "Salesforce/blip-image-captioning-base"
    sentence_transformer_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    qwen_gguf: Path = MODEL_WEIGHTS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"


HARDWARE = HardwareConfig()
PIPELINE = PipelineConfig()
SECURITY = SecurityConfig()
MODELS = ModelPaths()

# Force CPU-only mode regardless of detected CUDA (useful for grading on a
# jury laptop with no NVIDIA GPU) — CPU Fallback Logic is still evaluated
# per-model even when this is False; this is an explicit override switch.
FORCE_CPU_ONLY: bool = os.environ.get("QUERYCAM_FORCE_CPU", "0") == "1"