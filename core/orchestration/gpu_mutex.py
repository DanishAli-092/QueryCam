"""
core/orchestration/gpu_mutex.py
=================================
GPUMutexOrchestrator — <<Singleton>>, SDS §3.1 Module 3 / §4.1 Class Diagram.

This is the architectural centerpiece: it is the ONLY object in the
codebase permitted to grant GPU access to a GPU_Model. BLIPCaptioner
and QwenLLMEngine must never call transfer_to_vram()/clear_cuda_cache()
directly outside of a lock acquired here.

Sequence contract (matches SDS §4.2.1 and §4.2.2 exactly):

    1. acquire_ingestion_lock() / acquire_query_lock()
    2.   -> internally calls VRAMSentinel.check_vram()
    3.   -> if OK (<92%): sets _active_phase, returns True ("Locked")
    4.   -> if NOT OK: blocks (or raises, depending on caller policy)
    5. caller runs its Shift 1 / Shift 2 work
    6. release_lock()
    7.   -> trigger_gc() via VRAMSentinel
    8.   -> _active_phase reset to None

Because BLIP (ingestion) and Qwen (query) can never run concurrently
by hardware necessity, this is implemented as a single asyncio.Lock
guarding a phase name, not two independent locks — two independent
locks would allow both models to be "acquired" at once, which is
exactly the OOM scenario the whole architecture exists to prevent.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import Enum
from typing import Optional

from core.orchestration.vram_sentinel import VRAMSentinel

logger = logging.getLogger("querycam.orchestration.gpu_mutex")


class Phase(str, Enum):
    IDLE = "idle"
    INGESTION = "ingestion"   # BLIP holds the GPU
    QUERY = "query"           # Qwen holds the GPU


class GPUMutexOrchestrator:
    """
    <<Singleton>> — one instance per process, shared by every module
    that needs GPU access. Use GPUMutexOrchestrator.instance() rather
    than constructing directly.
    """

    _instance: Optional["GPUMutexOrchestrator"] = None
    _instance_lock = threading.Lock()

    def __init__(self, vram_sentinel: Optional[VRAMSentinel] = None) -> None:
        if GPUMutexOrchestrator._instance is not None:
            raise RuntimeError(
                "GPUMutexOrchestrator is a singleton — use .instance() instead "
                "of constructing it directly."
            )
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()  # for the sync wrapper API below
        self._active_phase: Phase = Phase.IDLE
        self.vram_sentinel = vram_sentinel or VRAMSentinel()

    @classmethod
    def instance(cls) -> "GPUMutexOrchestrator":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def active_phase(self) -> Phase:
        return self._active_phase

    def is_locked(self) -> bool:
        return self._active_phase != Phase.IDLE

    # ------------------------------------------------------------------ #
    # Synchronous API — Streamlit's execution model is single-threaded
    # per request, so the app calls these directly rather than awaiting.
    # ------------------------------------------------------------------ #

    def acquire_ingestion_lock(self, timeout_sec: float = 30.0) -> bool:
        """Blocks the calling thread for BLIP's Shift-1 GPU window."""
        return self._acquire_sync(Phase.INGESTION, timeout_sec)

    def acquire_query_lock(self, timeout_sec: float = 30.0) -> bool:
        """Blocks the calling thread for Qwen's Shift-2 GPU window."""
        return self._acquire_sync(Phase.QUERY, timeout_sec)

    def release_lock(self) -> None:
        """
        Releases whichever phase is currently active, then immediately
        triggers VRAM garbage collection (SDS: 'orchestrator aggressively
        clears VRAM and releases the GPU lock'). Safe to call even if
        nothing is held (idempotent no-op with a warning log).
        """
        with self._sync_lock:
            if self._active_phase == Phase.IDLE:
                logger.warning("release_lock() called with no active phase — ignoring.")
                return
            released_phase = self._active_phase
            self._active_phase = Phase.IDLE
            if self._lock.locked():
                self._lock.release()

        self.vram_sentinel.trigger_emergency_gc()
        logger.info("GPU lock released (was: %s). VRAM cleared.", released_phase.value)

    # ------------------------------------------------------------------ #
    # Async API — for a future FastAPI/asyncio backend (SDS §6 API Design
    # implies REST endpoints); kept alongside the sync API so Module 6
    # (RAG) and Module 5 (VLP) can be exercised from async test harnesses
    # without duplicating the acquisition/VRAM-check logic.
    # ------------------------------------------------------------------ #

    async def async_acquire_ingestion_lock(self) -> bool:
        return await self._acquire_async(Phase.INGESTION)

    async def async_acquire_query_lock(self) -> bool:
        return await self._acquire_async(Phase.QUERY)

    async def _acquire_async(self, phase: Phase) -> bool:
        await self._lock.acquire()
        snap = self.vram_sentinel.check_vram()
        if snap.used_fraction >= self.vram_sentinel.safety_cap:
            self.vram_sentinel.trigger_emergency_gc()
            snap = self.vram_sentinel.check_vram()
            if snap.used_fraction >= self.vram_sentinel.safety_cap:
                self._lock.release()
                logger.error("Refusing to grant %s lock — VRAM still >= cap after GC.", phase.value)
                return False
        self._active_phase = phase
        logger.info("GPU lock acquired for phase=%s (VRAM used=%.1f%%)",
                    phase.value, snap.used_fraction * 100)
        return True

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _acquire_sync(self, phase: Phase, timeout_sec: float) -> bool:
        acquired = self._run_coro_blocking(self._lock.acquire(), timeout_sec)
        if not acquired:
            logger.error("Timed out waiting %ss for GPU mutex (phase=%s).", timeout_sec, phase.value)
            return False

        snap = self.vram_sentinel.check_vram()
        if snap.used_fraction >= self.vram_sentinel.safety_cap:
            self.vram_sentinel.trigger_emergency_gc()
            snap = self.vram_sentinel.check_vram()
            if snap.used_fraction >= self.vram_sentinel.safety_cap:
                self._lock.release()
                logger.error(
                    "Refusing %s lock — VRAM %.1f%% still >= %.0f%% cap after emergency_gc().",
                    phase.value, snap.used_fraction * 100, self.vram_sentinel.safety_cap * 100,
                )
                return False

        with self._sync_lock:
            self._active_phase = phase
        logger.info("GPU lock acquired for phase=%s (VRAM used=%.1f%%)",
                    phase.value, snap.used_fraction * 100)
        return True

    @staticmethod
    def _run_coro_blocking(coro, timeout_sec: float) -> bool:
        """Runs an asyncio coroutine to completion from sync (Streamlit) code."""
        async def _wrapped():
            try:
                await asyncio.wait_for(coro, timeout=timeout_sec)
                return True
            except asyncio.TimeoutError:
                return False

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            # Streamlit's ScriptRunner thread has no running loop in practice,
            # but guard defensively for environments that do (e.g. Jupyter).
            return asyncio.run_coroutine_threadsafe(_wrapped(), loop).result()
        return loop.run_until_complete(_wrapped())


class gpu_locked:
    """
    Context manager sugar so pipeline code reads exactly like the
    sequence diagrams: `with gpu_locked(Phase.INGESTION): ...`
    Guarantees release_lock() runs even if the wrapped model raises.
    """

    def __init__(self, phase: Phase, orchestrator: Optional[GPUMutexOrchestrator] = None):
        self.phase = phase
        self.orchestrator = orchestrator or GPUMutexOrchestrator.instance()
        self._granted = False

    def __enter__(self) -> GPUMutexOrchestrator:
        if self.phase == Phase.INGESTION:
            self._granted = self.orchestrator.acquire_ingestion_lock()
        elif self.phase == Phase.QUERY:
            self._granted = self.orchestrator.acquire_query_lock()
        else:
            raise ValueError(f"Cannot lock for phase={self.phase}")
        if not self._granted:
            raise RuntimeError(
                f"Could not acquire GPU lock for phase={self.phase.value} "
                "— VRAM remained above the safety cap after emergency_gc()."
            )
        return self.orchestrator

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._granted:
            self.orchestrator.release_lock()
