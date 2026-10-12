"""
core/models/blip_captioner.py
================================
BLIPCaptioner — SDS §3.1 Module 5 (VLP) / §4.1 Class Diagram.

"A heavyweight generative vision-language model that strictly utilizes
the GPU to synthesize rich semantic textual captions from the cropped
visual data."

Initialized at torch.float16 (Ingestion Pipeline spec) to roughly halve
BLIP-Base's VRAM footprint versus fp32 — this is a memory-capacity
optimization, not a Tensor Core speed optimization: the Quadro M1200
(Maxwell, SM 5.0) predates hardware fp16 tensor cores, so compute
still runs at fp32 throughput internally on many ops. We accept that
trade explicitly because VRAM headroom, not speed, is the binding
constraint on this GPU (system prompt Hardware Constraints).

VRAM Safeguard enforcement (defense in depth): generate_caption()
optionally accepts the live GPUMutexOrchestrator and refuses to run if
the ingestion lock is not currently held by the caller. This does NOT
replace the Controller's responsibility to wrap calls in
`with gpu_locked(Phase.INGESTION):` — it is a second, cheap assertion
so a coding mistake elsewhere in the pipeline fails loudly instead of
silently double-booking the GPU.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

import config
from core.models.base import GPU_Model
from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase

logger = logging.getLogger("querycam.models.blip_captioner")

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    from transformers import BlipForConditionalGeneration, BlipProcessor
except ImportError:  # pragma: no cover
    BlipForConditionalGeneration = None
    BlipProcessor = None


class ModelNotLoadedError(RuntimeError):
    pass


class GPULockViolationError(RuntimeError):
    """Raised when a GPU_Model is asked to run outside its mutex window."""


class BLIPCaptioner(GPU_Model):
    """processor: transformers.BlipProcessor — SDS Class Diagram attribute."""

    def __init__(
        self,
        model_path: str = config.MODELS.blip_model_id,
        max_allocation_gb: float = 1.5,
        max_new_tokens: int = 40,
    ) -> None:
        super().__init__(model_path, max_allocation_gb)
        self.processor = None
        self.max_new_tokens = max_new_tokens

    # ------------------------------------------------------------------ #
    # AI_Model contract
    # ------------------------------------------------------------------ #

    def load_model(self) -> None:
        if BlipForConditionalGeneration is None or BlipProcessor is None:
            raise RuntimeError(
                "transformers is not installed. `pip install transformers`."
            )
        if torch is None:
            raise RuntimeError("torch is not installed — required for BLIP inference.")

        logger.info("Loading BLIP-Base VLM from %s onto device=%s ...", self.model_path, self.device)
        self.processor = BlipProcessor.from_pretrained(self.model_path)

        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self._model = BlipForConditionalGeneration.from_pretrained(
            self.model_path, torch_dtype=dtype
        )
        self._model.eval()

        # transfer_to_vram() (GPU_Model) moves + .half()'s the model when
        # self.device == 'cuda'; on CPU fallback it is a no-op placement.
        self.transfer_to_vram()
        self.is_loaded = True
        logger.info("BLIP-Base ready on %s (dtype=%s).", self.device, dtype)

    def unload_memory(self) -> None:
        self.processor = None
        super().unload_memory()  # GPU_Model.clear_cuda_cache()

    # ------------------------------------------------------------------ #
    # generate_caption() -> str — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def generate_caption(
        self,
        crop: np.ndarray,
        orchestrator: GPUMutexOrchestrator | None = None,
    ) -> str:
        """
        crop: BGR ndarray produced by YOLOv11Detector.crop_entities().

        SDS Sequence Diagram §4.2.1 step 15: 'caption()' is called once
        per detected object crop, inside the Mutex-locked Shift-1 window.
        """
        if not self.is_loaded or self._model is None:
            raise ModelNotLoadedError("Call load_model() before generate_caption().")
        self._assert_lock_held(orchestrator)

        if Image is None:
            raise RuntimeError("Pillow is not installed. `pip install pillow`.")

        pil_image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        inputs = self.processor(pil_image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        if self.device == "cuda":
            inputs = {
                k: (v.half() if torch.is_floating_point(v) else v)
                for k, v in inputs.items()
            }

        with torch.no_grad():
            output_ids = self._model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        caption = self.processor.decode(output_ids[0], skip_special_tokens=True)
        return caption.strip()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _assert_lock_held(orchestrator: GPUMutexOrchestrator | None) -> None:
        if orchestrator is None:
            return  # caller opted out of the defense-in-depth check
        if orchestrator.active_phase != Phase.INGESTION:
            raise GPULockViolationError(
                "BLIPCaptioner.generate_caption() called without the GPU "
                f"ingestion lock held (active_phase={orchestrator.active_phase.value}). "
                "Wrap the ingestion loop in `with gpu_locked(Phase.INGESTION):`."
            )
