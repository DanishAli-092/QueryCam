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

