# QueryCam pipeline setup script
# Run this inside your querycam_test folder in VS Code's PowerShell terminal

Write-Host 'Removing old structure...' -ForegroundColor Yellow
Remove-Item -Recurse -Force data, models, QueryCam, runs -ErrorAction SilentlyContinue
Remove-Item -Force test_yolo.py -ErrorAction SilentlyContinue

Write-Host 'Creating pipeline files...' -ForegroundColor Yellow
@'
"""
Central config for QueryCam pipeline test app.
Update paths to match your local setup.
"""

# --- Model paths ---
BASE_YOLO_MODEL = "yolov11n.pt"              # pretrained COCO weights
CUSTOM_YOLO_MODEL = "runs/train/best.pt"     # your fine-tuned weights (guns, bags, violence)

# --- Custom model class names (must match your training config) ---
CUSTOM_CLASSES = ["gun", "abandoned_bag", "violence"]

# --- BLIP model ---
BLIP_MODEL_NAME = "Salesforce/blip-image-captioning-base"

# --- Frame extraction ---
FRAME_INTERVAL_SEC = 1.0     # extract 1 frame every N seconds
MAX_FRAMES = 300             # safety cap for long videos during testing

# --- Detection thresholds ---
CONF_THRESHOLD = 0.35

# --- Device ---
DEVICE = "cuda"   # falls back to "cpu" automatically if cuda unavailable, handled in code

'@ | Set-Content -Path 'config.py' -Encoding UTF8

@'
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
    """Quick metadata check — useful for displaying in the UI."""
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

'@ | Set-Content -Path 'video_ingestion.py' -Encoding UTF8

@'
"""
Stage 2: Detection
Runs BOTH the base (pretrained) YOLOv11n and your custom fine-tuned YOLOv11n
on the same frame, so results can be compared side by side in the UI.
"""

from dataclasses import dataclass, field
from typing import List
import torch
from ultralytics import YOLO
import config


@dataclass
class Detection:
    class_name: str
    confidence: float
    box: List[float]  # [x1, y1, x2, y2]


@dataclass
class DetectionResult:
    annotated_frame: "any"     # frame with boxes drawn (numpy array, BGR)
    detections: List[Detection] = field(default_factory=list)


class DualYoloDetector:
    """
    Loads both the base and custom YOLO models once, then runs inference
    on demand. Loading once avoids reloading weights per frame (expensive
    on a 4GB VRAM card).
    """

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.base_model = YOLO(config.BASE_YOLO_MODEL)
        self.custom_model = YOLO(config.CUSTOM_YOLO_MODEL)

    def _run(self, model: YOLO, frame) -> DetectionResult:
        results = model.predict(
            source=frame,
            conf=config.CONF_THRESHOLD,
            device=self.device,
            verbose=False,
        )[0]

        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].tolist()
            class_name = model.names[cls_id]
            detections.append(Detection(class_name=class_name, confidence=conf, box=xyxy))

        annotated = results.plot()  # BGR numpy array with boxes drawn
        return DetectionResult(annotated_frame=annotated, detections=detections)

    def run_base(self, frame) -> DetectionResult:
        return self._run(self.base_model, frame)

    def run_custom(self, frame) -> DetectionResult:
        return self._run(self.custom_model, frame)

    def run_both(self, frame):
        """Convenience method returning (base_result, custom_result)."""
        return self.run_base(frame), self.run_custom(frame)

'@ | Set-Content -Path 'detection.py' -Encoding UTF8

@'
"""
Stage 3: Captioning (BLIP)
Only run on frames that had at least one detection, to save VRAM/time
on the 4GB budget card.
"""

import torch
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import config


class BlipCaptioner:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = BlipProcessor.from_pretrained(config.BLIP_MODEL_NAME)
        self.model = BlipForConditionalGeneration.from_pretrained(
            config.BLIP_MODEL_NAME
        ).to(self.device)

    def caption(self, frame_bgr) -> str:
        """
        frame_bgr: numpy array in BGR (as read by OpenCV).
        Returns a natural-language caption string.
        """
        # Convert BGR (OpenCV) -> RGB (PIL) before feeding BLIP
        rgb = frame_bgr[:, :, ::-1]
        image = Image.fromarray(rgb)

        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        output_ids = self.model.generate(**inputs, max_new_tokens=40)
        caption = self.processor.decode(output_ids[0], skip_special_tokens=True)
        return caption

'@ | Set-Content -Path 'captioning.py' -Encoding UTF8

@'
"""
QueryCam — Pipeline Test UI (Streamlit)
Stages: Video Ingestion -> Detection (base vs custom YOLO) -> BLIP captioning
(Qwen2.5 query layer to be wired in once ChromaDB integration is ready.)
"""

import tempfile
import cv2
import streamlit as st

import config
from video_ingestion import extract_frames, get_video_metadata
from detection import DualYoloDetector
from captioning import BlipCaptioner


st.set_page_config(page_title="QueryCam — Pipeline Test", layout="wide")
st.title("QueryCam — Pipeline Test (Streamlit)")

# --- Cache heavy model loads across reruns ---
@st.cache_resource
def load_detector():
    return DualYoloDetector()

@st.cache_resource
def load_captioner():
    return BlipCaptioner()


uploaded_video = st.file_uploader("Upload a video", type=["mp4", "avi", "mov", "mkv"])

if uploaded_video:
    # Save to a temp file so OpenCV can read it
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_video.read())
    video_path = tfile.name

    meta = get_video_metadata(video_path)
    st.caption(
        f"Duration: {meta['duration_sec']:.1f}s | FPS: {meta['fps']:.1f} | "
        f"Resolution: {meta['width']}x{meta['height']}"
    )

    interval = st.slider("Frame extraction interval (seconds)", 0.5, 5.0, config.FRAME_INTERVAL_SEC)

    if st.button("Run Pipeline"):
        with st.status("Stage 1: Ingesting video...", expanded=False):
            frames = extract_frames(video_path, interval_sec=interval)
            st.write(f"Extracted {len(frames)} frames")

        detector = load_detector()
        captioner = load_captioner()

        st.subheader("Stage 2 & 3: Detection (Base vs Custom) + Captioning")

        for ef in frames:
            base_result, custom_result = detector.run_both(ef.frame)

            # Only run BLIP if either model found something — saves VRAM/time
            has_detection = bool(base_result.detections or custom_result.detections)

            with st.expander(f"Frame {ef.index} — t={ef.timestamp_sec:.1f}s "
                              f"{'(detection found)' if has_detection else ''}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.image(
                        cv2.cvtColor(base_result.annotated_frame, cv2.COLOR_BGR2RGB),
                        caption="Base YOLOv11n (COCO pretrained)",
                    )
                    if base_result.detections:
                        st.table([
                            {"class": d.class_name, "confidence": f"{d.confidence:.2f}"}
                            for d in base_result.detections
                        ])
                    else:
                        st.write("No detections")

                with col2:
                    st.image(
                        cv2.cvtColor(custom_result.annotated_frame, cv2.COLOR_BGR2RGB),
                        caption="Custom Fine-tuned YOLOv11n (gun / bag / violence)",
                    )
                    if custom_result.detections:
                        st.table([
                            {"class": d.class_name, "confidence": f"{d.confidence:.2f}"}
                            for d in custom_result.detections
                        ])
                    else:
                        st.write("No detections")

                if has_detection:
                    caption = captioner.caption(ef.frame)
                    st.info(f"**BLIP caption:** {caption}")

        st.success("Pipeline run complete. Qwen2.5 query layer will plug in here once ChromaDB is wired up.")

'@ | Set-Content -Path 'app.py' -Encoding UTF8

@'
streamlit
opencv-python
ultralytics
torch
torchvision
transformers
Pillow

'@ | Set-Content -Path 'requirements.txt' -Encoding UTF8

Write-Host 'Done. Verifying structure:' -ForegroundColor Green
Get-ChildItem

Write-Host 'Now pushing to GitHub...' -ForegroundColor Yellow
git add -A
git commit -m 'Remove old structure, add clean pipeline architecture'
git push -u origin main