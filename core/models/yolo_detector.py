"""
core/models/yolo_detector.py
==============================
YOLOv11Detector — SDS §3.1 Module 5 (VLP) / §4.1 Class Diagram.

"A highly optimized object detection model executing on system RAM to
identify and crop critical entities from dynamic motion key frames."

Architectural note — WHY THIS IS A CPU_Model, NOT A GPU_Model:
Per SDS §1.4 (Compliance with Idea Defence Feedback), the fine-tuned
YOLOv11 Nano is deliberately deployed via onnxruntime's CPU execution
provider, even on a machine where CUDA is available. This is not a
missed optimization — it is the architectural decision that keeps the
entire 4GB VRAM budget exclusively reserved for BLIP-Base and Qwen2.5,
which is the whole premise of the GPU Mutex Lock. Do not "optimize"
this to CUDAExecutionProvider without revisiting the VRAM budget in
config.py first.

Inherits CPU_Model (SDS Class Diagram): confidence_thresh is this
class's own attribute; device/max_allocation_gb/pin_to_ram() come from
the parent.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

import config
from core.models.base import CPU_Model
from dto.entities import BoundingBox

logger = logging.getLogger("querycam.models.yolo_detector")

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None
    logger.warning("onnxruntime not installed — YOLOv11Detector cannot load_model().")


class ModelNotLoadedError(RuntimeError):
    pass


class YOLOv11Detector(CPU_Model):
    """confidence_thresh: float — SDS Class Diagram attribute."""

    def __init__(
        self,
        model_path: str = str(config.MODELS.yolo_onnx),
        confidence_thresh: float = config.PIPELINE.yolo_confidence_threshold,
        input_size: tuple[int, int] = config.PIPELINE.frame_size,
        class_names: tuple[str, ...] = config.PIPELINE.yolo_classes,
        nms_iou_thresh: float = 0.45,
    ) -> None:
        super().__init__(model_path, max_allocation_gb=0.5)
        self.confidence_thresh = confidence_thresh
        self.input_size = input_size
        self.class_names = class_names
        self.nms_iou_thresh = nms_iou_thresh
        self._session: "ort.InferenceSession | None" = None

    # ------------------------------------------------------------------ #
    # AI_Model contract
    # ------------------------------------------------------------------ #

    def load_model(self) -> None:
        if ort is None:
            raise RuntimeError(
                "onnxruntime is not installed. `pip install onnxruntime` "
                "(CPU) or `onnxruntime-gpu` if you intend to override the "
                "CPU-only deployment decision documented above."
            )
        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"Fine-tuned YOLOv11 Nano ONNX weights not found at {self.model_path}. "
                "Export from the Colab fine-tuning run (SDS §1.4) and place it there."
            )

        # Deliberately CPU-only — see module docstring.
        self.pin_to_ram()
        self._session = ort.InferenceSession(
            self.model_path, providers=["CPUExecutionProvider"]
        )
        self.is_loaded = True
        # Diagnostic visibility: chromadb (and some transformers extras) can
        # pull in the CPU-only `onnxruntime` package alongside `onnxruntime-gpu`,
        # silently shadowing the GPU build. This is harmless for YOLO here
        # (it's CPU-pinned by design — see module docstring), but log the
        # actually-available providers so a mismatch is visible in the console
        # rather than assumed. If you ever DO want YOLO on GPU, this line is
        # where you'd confirm 'CUDAExecutionProvider' is really present.
        logger.info("onnxruntime available providers: %s", ort.get_available_providers())
        logger.info("YOLOv11Detector loaded from %s (CPUExecutionProvider).", self.model_path)

    def unload_memory(self) -> None:
        self._session = None
        super().unload_memory()

    # ------------------------------------------------------------------ #
    # detect() -> List[BoundingBox] — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        frame: a single BGR ndarray, already resized to config.PIPELINE.frame_size
        by OpenCVMotionFilter (SDS Sequence Diagram: 'detect(frame)' is called
        per-keyframe inside the ingestion loop).
        """
        if not self.is_loaded or self._session is None:
            raise ModelNotLoadedError("Call load_model() before detect().")

        input_tensor = self._preprocess(frame)
        input_name = self._session.get_inputs()[0].name
        raw_output = self._session.run(None, {input_name: input_tensor})[0]
        return self._postprocess(raw_output, orig_shape=frame.shape[:2])

    def crop_entities(self, frame: np.ndarray, boxes: list[BoundingBox]) -> list[np.ndarray]:
        """
        crop_entities() -> List[Image] — SDS Class Diagram. Returned as
        BGR ndarrays rather than PIL.Image objects to avoid a redundant
        conversion; BLIPCaptioner.generate_caption() converts to PIL/RGB
        internally right before the processor call.
        """
        crops: list[np.ndarray] = []
        h, w = frame.shape[:2]
        for box in boxes:
            x1, y1, x2, y2 = box.as_xyxy()
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                logger.debug("Skipping degenerate crop for box=%s", box)
                continue
            crops.append(frame[y1:y2, x1:x2].copy())
        return crops

    # ------------------------------------------------------------------ #
    # Pre/post-processing internals
    # ------------------------------------------------------------------ #

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, self.input_size, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))  # HWC -> CHW
        return np.expand_dims(chw, axis=0)  # NCHW, batch=1

    def _postprocess(self, raw_output: np.ndarray, orig_shape: tuple[int, int]) -> list[BoundingBox]:
        """
        Decodes YOLOv11's native ONNX export layout: (1, 4 + num_classes, num_anchors),
        cx/cy/w/h in the model's 640x640 input space, followed by per-class scores
        (Ultralytics does NOT apply sigmoid or objectness separately in this head).
        """
        predictions = np.squeeze(raw_output, axis=0).T  # -> (num_anchors, 4 + num_classes)
        if predictions.shape[1] < 5:
            logger.error("Unexpected YOLO output shape %s — check ONNX export.", raw_output.shape)
            return []

        num_classes_from_model = predictions.shape[1] - 4
        if num_classes_from_model != len(self.class_names):
            # This is the exact failure mode that silently mislabeled every
            # detection before config.PIPELINE.yolo_classes was corrected to
            # (gun, abandoned_bag, violence) — catch it loudly next time
            # instead of quietly assigning wrong labels.
            logger.warning(
                "ONNX output implies %d classes but class_names has %d entries %s — "
                "labels WILL be wrong. Update config.PIPELINE.yolo_classes to match "
                "the classes your fine-tuned model was exported with.",
                num_classes_from_model, len(self.class_names), self.class_names,
            )

        class_scores = predictions[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]

        keep = confidences >= self.confidence_thresh
        predictions, class_ids, confidences = predictions[keep], class_ids[keep], confidences[keep]
        if len(predictions) == 0:
            return []

        orig_h, orig_w = orig_shape
        scale_x, scale_y = orig_w / self.input_size[0], orig_h / self.input_size[1]

        boxes_xywh = []
        for cx, cy, w, h in predictions[:, :4]:
            x = (cx - w / 2) * scale_x
            y = (cy - h / 2) * scale_y
            boxes_xywh.append([x, y, w * scale_x, h * scale_y])

        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes_xywh, scores=confidences.tolist(),
            score_threshold=self.confidence_thresh, nms_threshold=self.nms_iou_thresh,
        )
        indices = np.array(indices).flatten() if len(indices) > 0 else []

        results: list[BoundingBox] = []
        for i in indices:
            x, y, w, h = boxes_xywh[i]
            label = (
                self.class_names[class_ids[i]]
                if class_ids[i] < len(self.class_names) else f"class_{class_ids[i]}"
            )
            results.append(BoundingBox(
                x=int(round(x)), y=int(round(y)),
                w=int(round(w)), h=int(round(h)),
                label=label, confidence=float(confidences[i]),
            ))
        return results
