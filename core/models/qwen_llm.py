"""
core/models/qwen_llm.py
=========================
QwenLLMEngine — SDS §3.1 Module 6 (RAG) / §4.1 Class Diagram.

"A quantized local language model that acquires the GPU lock to
synthesize retrieved context and generate accurate, timestamped
forensic answers."

Deployment note: llama.cpp's GPU offload is configured at construction
time via n_gpu_layers, NOT via a post-hoc .to(device) call like a
standard torch nn.Module. This means QwenLLMEngine does NOT use
GPU_Model.transfer_to_vram()/clear_cuda_cache() the way BLIPCaptioner
does — load_model() passes n_gpu_layers directly to the Llama
constructor based on self.device, and unload_memory() simply drops the
reference (llama.cpp's destructor frees the CUDA context). We still
inherit GPU_Model rather than duplicating device-resolution logic,
since resolve_device() and the mutex-lock contract are identical.

Why 4-bit GGUF: Qwen2.5-1.5B-Instruct at Q4_K_M quantization occupies
roughly ~1.0-1.1GB of VRAM at n_ctx=4096 — comfortably inside the
remaining VRAM budget after BLIP has been fully unloaded by the
Mutex/Sentinel handoff (SDS §3.2.B: 'Hardware Orchestrator acquires
the GPU lock exclusively for the LLM').
"""

from __future__ import annotations

import logging
import os
import sys

import config
from core.models.base import GPU_Model
from core.orchestration.gpu_mutex import GPUMutexOrchestrator, Phase

logger = logging.getLogger("querycam.models.qwen_llm")


def _add_cuda_dlls() -> None:
    """
    Windows-only: the prebuilt CUDA wheel for llama-cpp-python (installed
    via `--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124`,
    see requirements.txt) links against the CUDA runtime and cuBLAS DLLs
    but does NOT bundle them — it expects either a full CUDA Toolkit
    install, or (what this project uses instead, to avoid a multi-GB
    Toolkit install on the grading machine) the redistributable
    `nvidia-cuda-runtime-cu12` / `nvidia-cublas-cu12` pip packages.

    Those packages drop their DLLs inside the venv's site-packages, which
    is NOT on Windows' DLL search path by default — importing llama_cpp
    without this fails with "Could not find module ... or one of its
    dependencies" even though the DLLs are sitting right there on disk.
    os.add_dll_directory() (Python 3.8+, Windows-only) is the fix.

    Safe to call on non-Windows platforms or if the nvidia-* packages
    aren't installed (e.g. a CPU-only deployment) — it just no-ops.
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia.cuda_runtime  # type: ignore
        import nvidia.cublas  # type: ignore
    except ImportError:
        return  # CPU-only deployment — nothing to add, GGML falls back to CPU.

    for pkg in (nvidia.cuda_runtime, nvidia.cublas):
        bin_dir = os.path.join(os.path.dirname(pkg.__file__), "bin")
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass  # Python <3.8 or already added — fall through to PATH prepend
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            logger.debug("Added CUDA DLL search path: %s", bin_dir)


_add_cuda_dlls()  # MUST run before `from llama_cpp import Llama` below

try:
    from llama_cpp import Llama
except (ImportError, RuntimeError, OSError) as e:
    # RuntimeError/OSError (not just ImportError): a missing CUDA DLL
    # surfaces as one of these depending on the ctypes loader, NOT a
    # clean ImportError — catch both so a CUDA-DLL problem degrades to
    # "llama-cpp-python not installed" instead of crashing module import.
    Llama = None
    logger.warning("llama-cpp-python could not be imported (%s: %s) — "
                    "QwenLLMEngine.load_model() will raise if called.", type(e).__name__, e)

_SYSTEM_PROMPT = (
    "You are Query-Cam, an offline forensic video analysis assistant. "
    "You are given a user's question about surveillance footage, along "
    "with retrieved visual-caption context and the exact video timestamps "
    "where each caption was observed. Answer ONLY using the provided "
    "context. Always cite the relevant timestamp(s) in your answer. If "
    "the context does not contain the answer, say so plainly instead of "
    "guessing."
)


class ModelNotLoadedError(RuntimeError):
    pass


class GPULockViolationError(RuntimeError):
    pass


class QwenLLMEngine(GPU_Model):
    """quantization: str = "4-bit GGUF" — SDS Class Diagram attribute."""

    def __init__(
        self,
        model_path: str = str(config.MODELS.qwen_gguf),
        max_allocation_gb: float = 1.2,
        context_window: int = config.PIPELINE.qwen_context_window,
        max_new_tokens: int = config.PIPELINE.qwen_max_new_tokens,
    ) -> None:
        super().__init__(model_path, max_allocation_gb)
        self.quantization: str = "4-bit GGUF"
        self.context_window = context_window
        self.max_new_tokens = max_new_tokens

    # ------------------------------------------------------------------ #
    # AI_Model contract
    # ------------------------------------------------------------------ #

    def load_model(self) -> None:
        if Llama is None:
            raise RuntimeError(
                "llama-cpp-python is not installed. Build it with the CUDA "
                "backend for GPU inference: "
                "CMAKE_ARGS=\"-DGGML_CUDA=on\" pip install llama-cpp-python"
            )
        from pathlib import Path
        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"Qwen2.5-1.5B GGUF weights not found at {self.model_path}. "
                "Download the Q4_K_M quantization and place it there."
            )

        n_gpu_layers = -1 if self.device == "cuda" else 0  # -1 = offload all layers
        logger.info(
            "Loading Qwen2.5-1.5B-Instruct (%s) — device=%s, n_gpu_layers=%s, n_ctx=%d",
            self.quantization, self.device, n_gpu_layers, self.context_window,
        )
        self._model = Llama(
            model_path=self.model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=self.context_window,
            verbose=False,
        )
        self.is_loaded = True
        logger.info("Qwen2.5-1.5B ready.")

    def unload_memory(self) -> None:
        # llama.cpp frees its CUDA context in Llama.__del__ when the last
        # reference drops; we still call the parent's gc/empty_cache pass
        # for any torch-side fragmentation left by the previous BLIP phase.
        #
        # Calling .close() explicitly (llama-cpp-python >=0.2.60) tears
        # down the C++ context deterministically, right here, instead of
        # leaving it to __del__ at some later, unpredictable garbage-
        # collection point — that's what produces the harmless-but-noisy
        # "AttributeError: 'NoneType' object is not callable" message
        # during interpreter shutdown on 0.2.x. Best-effort: older
        # bindings without .close() just fall through to the old behavior.
        if self._model is not None and hasattr(self._model, "close"):
            try:
                self._model.close()
            except Exception:  # noqa: BLE001 — never let cleanup itself crash the app
                logger.debug("Llama.close() raised during unload_memory() — ignoring.", exc_info=True)
        self._model = None
        super().unload_memory()  # GPU_Model.clear_cuda_cache()

    # ------------------------------------------------------------------ #
    # generate_answer(prompt, context) -> str — SDS Class Diagram
    # ------------------------------------------------------------------ #

    def generate_answer(
        self,
        prompt: str,
        context: list[str],
        orchestrator: GPUMutexOrchestrator | None = None,
    ) -> str:
        """
        prompt  : the user's raw natural-language query.
        context : formatted strings, one per retrieved chunk, e.g.
                  "[00:01:04.200] a person wearing a black backpack ..."
                  — this is exactly the RAGEngine's job to assemble
                  (see core/rag/rag_engine.py) from ChromaDB hits +
                  SQLiteMetadataStore.fetch_timestamps().

        SDS Sequence Diagram §4.2.2 step 13: 'generate_answer()' is
        called once, inside the Mutex-locked Shift-2 window.
        """
        if not self.is_loaded or self._model is None:
            raise ModelNotLoadedError("Call load_model() before generate_answer().")
        self._assert_lock_held(orchestrator)

        context_block = "\n".join(f"- {c}" for c in context) if context else "(no relevant context found)"
        user_message = (
            f"Retrieved context:\n{context_block}\n\n"
            f"Question: {prompt}"
        )

        completion = self._model.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=self.max_new_tokens,
            temperature=0.2,  # low temperature — forensic answers should be literal, not creative
        )
        answer = completion["choices"][0]["message"]["content"]
        return answer.strip()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _assert_lock_held(orchestrator: GPUMutexOrchestrator | None) -> None:
        if orchestrator is None:
            return
        if orchestrator.active_phase != Phase.QUERY:
            raise GPULockViolationError(
                "QwenLLMEngine.generate_answer() called without the GPU "
                f"query lock held (active_phase={orchestrator.active_phase.value}). "
                "Wrap the call in `with gpu_locked(Phase.QUERY):`."
            )
