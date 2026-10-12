"""
core/models/base.py
====================
Abstract inheritance hierarchy exactly as drawn in SDS §4.1 (Class Diagram):

                    <<abstract>>
                      AI_Model
                    /          \\
        <<abstract>>          <<abstract>>
         CPU_Model              GPU_Model

Every concrete model in the pipeline (YOLOv11Detector, BLIPCaptioner,
SentenceTransformerEncoder, QwenLLMEngine) inherits one of the two
branches. This is what gives the Hardware Orchestration Module (VRAM
Sentinel + GPU Mutex) a single, uniform surface to manage: it never
needs to know *which* model it's holding a lock for — only whether
that model is a GPU_Model (contends for the mutex) or a CPU_Model
(never does).

Dynamic Hardware Check (system rule #2): GPU_Model.to_device() always
verifies torch.cuda.is_available() before touching CUDA and silently
degrades to CPU execution if the jury's grading machine has no NVIDIA
GPU. This must never raise — a missing GPU is a supported deployment
target, not an error state.
"""

from __future__ import annotations

import abc
import gc
import logging

logger = logging.getLogger("querycam.models")

try:
    import torch
except ImportError:  # pragma: no cover — torch is a hard requirement in prod,
    torch = None      # but we degrade gracefully so this module stays importable
    logger.warning("PyTorch not found — GPU_Model subclasses will run CPU-only.")


class AI_Model(abc.ABC):
    """
    Root of the model hierarchy (SDS §4.1).

    Attributes
    ----------
    model_path : str
        Filesystem path or HuggingFace repo id the concrete model was
        constructed from. Kept for audit/logging (SYSTEM_LOG traceability).
    is_loaded : bool
        Whether load_model() has been called and weights currently
        occupy memory (RAM or VRAM depending on subclass).
    """

    def __init__(self, model_path: str) -> None:
        self.model_path: str = model_path
        self.is_loaded: bool = False
        self._model = None  # concrete subclasses assign the real weights object here

    @abc.abstractmethod
    def load_model(self) -> None:
        """Materialize weights into memory. Must set self.is_loaded = True."""
        raise NotImplementedError

    @abc.abstractmethod
    def unload_memory(self) -> None:
        """
        Release weights from memory. Must set self.is_loaded = False.

        For GPU_Model subclasses this is the hook the VRAM Sentinel calls
        during emergency_gc() (SDS §3.2.C) — it MUST be safe to call
        repeatedly and MUST be fast (no re-download, no disk I/O).
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        state = "loaded" if self.is_loaded else "unloaded"
        return f"<{self.__class__.__name__} path={self.model_path!r} state={state}>"


class CPU_Model(AI_Model):
    """
    Branch for models pinned to system RAM (16GB budget) — never
    contends for the GPU Mutex Lock. Per SDS §3.1 Module 4/5, this
    covers YOLOv11 Nano ONNX and the Sentence-Transformer encoder.
    """

    device: str = "cpu"

    def __init__(self, model_path: str, max_allocation_gb: float = 2.0) -> None:
        super().__init__(model_path)
        self.max_allocation_gb = max_allocation_gb

    def pin_to_ram(self) -> None:
        """
        No-op placement hook kept for symmetry with GPU_Model.transfer_to_vram().

        Most CPU-bound runtimes here (onnxruntime CPUExecutionProvider,
        sentence-transformers on 'cpu') place tensors in system RAM by
        construction, so this exists primarily as an explicit, auditable
        step in load_model() rather than a real data movement operation.
        """
        logger.debug("%s: pinned to system RAM (budget=%.2fGB)",
                     self.__class__.__name__, self.max_allocation_gb)

    def unload_memory(self) -> None:
        self._model = None
        self.is_loaded = False
        gc.collect()


class GPU_Model(AI_Model):
    """
    Branch for models that MUST acquire the GPUMutexOrchestrator lock
    before load_model() is called. Per SDS §3.1 Module 5/6, this covers
    BLIP-Base VLM and Qwen2.5-1.5B GGUF. These two must NEVER hold
    tensors on the GPU at the same time (system rule: VRAM Safeguard).

    CPU Fallback Logic (system rule #2): every subclass calls
    resolve_device() rather than assuming 'cuda' is available, so the
    exact same code path runs correctly on a non-GPU grading machine.
    """

    device: str = "cuda"

    def __init__(self, model_path: str, max_allocation_gb: float = 1.5) -> None:
        super().__init__(model_path)
        self.max_allocation_gb = max_allocation_gb
        self.device = self.resolve_device()

    @staticmethod
    def resolve_device() -> str:
        """Dynamic Hardware Check — never assume CUDA is present."""
        import config  # local import avoids a hard circular dependency at module load

        if config.FORCE_CPU_ONLY:
            return "cpu"
        if torch is not None and torch.cuda.is_available():
            return "cuda"
        logger.info("CUDA unavailable — falling back to CPU execution.")
        return "cpu"

    def transfer_to_vram(self) -> None:
        """
        Move an already-instantiated model object to self.device.

        Concrete subclasses call this from load_model() AFTER acquiring
        the GPU Mutex Lock — never before. This class does not acquire
        the lock itself; that responsibility belongs to
        GPUMutexOrchestrator so the orchestration policy stays in one
        place (SDS §3.1 Module 3).
        """
        if self._model is None:
            raise RuntimeError(
                f"{self.__class__.__name__}.transfer_to_vram() called before "
                "the underlying model object was constructed."
            )
        if self.device == "cuda":
            self._model = self._model.to(self.device)
            if torch is not None:
                self._model = self._model.half() if hasattr(self._model, "half") else self._model
        logger.info("%s materialized on device=%s", self.__class__.__name__, self.device)

    def clear_cuda_cache(self) -> None:
        """
        Hard VRAM release, invoked by VRAMSentinel.trigger_emergency_gc()
        and by GPUMutexOrchestrator.release_lock() after every Shift.
        """
        self._model = None
        self.is_loaded = False
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        logger.info("%s: CUDA cache cleared, VRAM released.", self.__class__.__name__)

    def unload_memory(self) -> None:
        self.clear_cuda_cache()
