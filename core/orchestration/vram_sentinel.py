# """
# core/orchestration/vram_sentinel.py
# ====================================
# VRAMSentinel — SDS §3.1 Module 3 / §3.2.C.

# "Polls GPU memory every 500ms using an nvidia-smi wrapper. If VRAM
# usage exceeds the 92% ceiling, it triggers emergency_gc() to force
# Python garbage collection and unload idle tensors."

# Design note: we prefer torch.cuda.mem_get_info() over shelling out to
# nvidia-smi where possible — it's an order of magnitude cheaper per
# poll and avoids spawning a subprocess every 500ms for the life of the
# app. The nvidia-smi wrapper is kept as the CPU-fallback / torch-absent
# path so the Sentinel still functions for diagnostics on a machine
# where torch isn't importable yet.
# """

# from __future__ import annotations

# import gc
# import logging
# import subprocess
# import threading
# import time
# from dataclasses import dataclass, field
# from typing import Callable, Optional

# logger = logging.getLogger("querycam.orchestration.vram_sentinel")

# try:
#     import torch
# except ImportError:  # pragma: no cover
#     torch = None


# @dataclass
# class VRAMSnapshot:
#     total_mb: float
#     used_mb: float
#     free_mb: float

#     @property
#     def used_fraction(self) -> float:
#         return 0.0 if self.total_mb == 0 else self.used_mb / self.total_mb


# class VRAMSentinel:
#     """
#     Background daemon — one instance shared app-wide (constructed once
#     inside GPUMutexOrchestrator, per SDS Class Diagram association).

#     Attributes (matching Class Diagram)
#     ------------------------------------
#     total_vram_gb : float   = 4.0   (Quadro M1200 hardware ceiling)
#     safety_cap    : float   = 0.92  (hard cap fraction, SDS §3.2.C)
#     """

#     def __init__(
#         self,
#         total_vram_gb: float = 4.0,
#         safety_cap: float = 0.92,
#         poll_interval_sec: float = 0.5,
#         on_alert: Optional[Callable[[VRAMSnapshot], None]] = None,
#     ) -> None:
#         self.total_vram_gb = total_vram_gb
#         self.safety_cap = safety_cap
#         self.poll_interval_sec = poll_interval_sec
#         self._on_alert = on_alert

#         self._stop_event = threading.Event()
#         self._thread: Optional[threading.Thread] = None
#         self._gpu_available = torch is not None and torch.cuda.is_available()

#         if not self._gpu_available:
#             logger.info(
#                 "VRAMSentinel: no CUDA device detected — running in "
#                 "CPU-fallback diagnostic mode (polling is a no-op)."
#             )

#     # ------------------------------------------------------------------ #
#     # Public API — names match the Class Diagram exactly
#     # ------------------------------------------------------------------ #

#     def get_free_vram_percent(self) -> float:
#         """Returns free VRAM as a percentage of total_vram_gb (0-100)."""
#         snap = self._read_vram()
#         if snap.total_mb == 0:
#             return 100.0  # CPU-only host: nothing to protect against
#         return round((snap.free_mb / snap.total_mb) * 100.0, 2)

#     def check_vram(self) -> VRAMSnapshot:
#         """One-shot synchronous check — used by GPUMutexOrchestrator.acquire_*_lock()
#         as the pre-flight 'check_vram() -> OK(<92%)' step in SDS Sequence Diagram §4.2."""
#         return self._read_vram()

#     def start(self) -> None:
#         """Launch the 500ms background polling loop (idempotent)."""
#         if self._thread is not None and self._thread.is_alive():
#             return
#         self._stop_event.clear()
#         self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="VRAMSentinel")
#         self._thread.start()
#         logger.info("VRAMSentinel started (poll=%.0fms, cap=%.0f%%)",
#                     self.poll_interval_sec * 1000, self.safety_cap * 100)

#     def stop(self) -> None:
#         self._stop_event.set()
#         if self._thread is not None:
#             self._thread.join(timeout=2.0)

#     def alert_orchestrator(self, snapshot: VRAMSnapshot) -> None:
#         """Invoked internally when the cap is breached; also externally
#         testable so unit tests can simulate an OOM-risk condition."""
#         logger.warning(
#             "VRAM ALERT: %.0f%% used (%.0fMB / %.0fMB) — cap is %.0f%%. "
#             "Triggering emergency_gc().",
#             snapshot.used_fraction * 100, snapshot.used_mb, snapshot.total_mb,
#             self.safety_cap * 100,
#         )
#         self.trigger_emergency_gc()
#         if self._on_alert is not None:
#             self._on_alert(snapshot)

#     def trigger_emergency_gc(self) -> None:
#         """Force Python + CUDA garbage collection to reclaim fragmented VRAM."""
#         gc.collect()
#         if self._gpu_available:
#             torch.cuda.empty_cache()
#             torch.cuda.ipc_collect()
#         logger.info("emergency_gc() complete.")

#     # ------------------------------------------------------------------ #
#     # Internals
#     # ------------------------------------------------------------------ #

#     def _poll_loop(self) -> None:
#         while not self._stop_event.is_set():
#             if self._gpu_available:
#                 snap = self._read_vram()
#                 if snap.used_fraction >= self.safety_cap:
#                     self.alert_orchestrator(snap)
#             self._stop_event.wait(self.poll_interval_sec)

#     def _read_vram(self) -> VRAMSnapshot:
#         """Prefer torch's cheap native query; fall back to nvidia-smi subprocess."""
#         if self._gpu_available:
#             free_b, total_b = torch.cuda.mem_get_info()
#             free_mb, total_mb = free_b / 1e6, total_b / 1e6
#             return VRAMSnapshot(total_mb=total_mb, used_mb=total_mb - free_mb, free_mb=free_mb)
#         return self._read_vram_via_nvidia_smi()

#     @staticmethod
#     def _read_vram_via_nvidia_smi() -> VRAMSnapshot:
#         """CPU-fallback / torch-absent path — parses nvidia-smi CSV output."""
#         try:
#             out = subprocess.check_output(
#                 [
#                     "nvidia-smi",
#                     "--query-gpu=memory.total,memory.used,memory.free",
#                     "--format=csv,noheader,nounits",
#                 ],
#                 timeout=2.0,
#             ).decode().strip()
#             total_mb, used_mb, free_mb = (float(v) for v in out.split(","))
#             return VRAMSnapshot(total_mb=total_mb, used_mb=used_mb, free_mb=free_mb)
#         except (subprocess.SubprocessError, FileNotFoundError, ValueError):
#             # No NVIDIA driver / no GPU at all — report an all-zero, non-fatal snapshot.
#             return VRAMSnapshot(total_mb=0.0, used_mb=0.0, free_mb=0.0)

from __future__ import annotations

import gc
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("querycam.orchestration.vram_sentinel")

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None


@dataclass
class VRAMSnapshot:
    total_mb: float
    used_mb: float
    free_mb: float

    @property
    def used_fraction(self) -> float:
        return 0.0 if self.total_mb == 0 else self.used_mb / self.total_mb


class VRAMSentinel:
    def __init__(
        self,
        total_vram_gb: float = 4.0,
        safety_cap: float = 0.92,
        poll_interval_sec: float = 0.5,
        on_alert: Optional[Callable[[VRAMSnapshot], None]] = None,
    ) -> None:
        self.total_vram_gb = total_vram_gb
        self.safety_cap = safety_cap
        self.poll_interval_sec = poll_interval_sec
        self._on_alert = on_alert

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpu_available = torch is not None and torch.cuda.is_available()

        # Timeline recording — OFF by default (no point burning cycles
        # storing history outside of a demo-worthy window). Controller
        # toggles this on for the duration of one ingestion run so the UI
        # can plot "VRAM over time" as live proof of the GPU Mutex Lock /
        # BLIP-then-Qwen handoff, instead of just claiming it happens.
        self._recording = False
        self._history: list[dict] = []
        self._record_start_t = 0.0

        if not self._gpu_available:
            logger.info("VRAMSentinel: no CUDA device detected — CPU-fallback diagnostic mode.")

    def get_free_vram_percent(self) -> float:
        snap = self._read_vram()
        if snap.total_mb == 0:
            return 100.0
        return round((snap.free_mb / snap.total_mb) * 100.0, 2)

    def check_vram(self) -> VRAMSnapshot:
        return self._read_vram()

    def start_recording(self) -> None:
        """Begin a fresh timeline capture — call at the start of an
        ingestion run. The background poll thread (already running from
        .start()) picks this up on its next tick, no restart needed."""
        self._history = []
        self._record_start_t = time.monotonic()
        self._recording = True

    def stop_recording(self) -> None:
        self._recording = False

    def get_history(self) -> list[dict]:
        """Returns [{"t": elapsed_seconds, "used_mb": float, "total_mb": float}, ...]
        captured since the most recent start_recording()."""
        return list(self._history)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="VRAMSentinel")
        self._thread.start()
        logger.info("VRAMSentinel started (poll=%.0fms, cap=%.0f%%)",
                    self.poll_interval_sec * 1000, self.safety_cap * 100)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def alert_orchestrator(self, snapshot: VRAMSnapshot) -> None:
        logger.warning("VRAM ALERT: %.0f%% used — cap is %.0f%%. Triggering emergency_gc().",
                        snapshot.used_fraction * 100, self.safety_cap * 100)
        self.trigger_emergency_gc()
        if self._on_alert is not None:
            self._on_alert(snapshot)

    def trigger_emergency_gc(self) -> None:
        gc.collect()
        if self._gpu_available:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        logger.info("emergency_gc() complete.")

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            # Skip the read entirely when idle on a CPU-only host — no
            # alert threshold to check, nothing to record. During an
            # active recording window (self._recording), always read:
            # _read_vram() falls back to nvidia-smi gracefully even
            # without torch, so this still works set up for GPU hosts
            # where torch itself isn't installed.
            if self._gpu_available or self._recording:
                snap = self._read_vram()
                if self._recording:
                    self._history.append({
                        "t": round(time.monotonic() - self._record_start_t, 2),
                        "used_mb": snap.used_mb,
                        "total_mb": snap.total_mb,
                    })
                if self._gpu_available and snap.used_fraction >= self.safety_cap:
                    self.alert_orchestrator(snap)
            self._stop_event.wait(self.poll_interval_sec)

    def _read_vram(self) -> VRAMSnapshot:
        if self._gpu_available:
            free_b, total_b = torch.cuda.mem_get_info()
            free_mb, total_mb = free_b / 1e6, total_b / 1e6
            return VRAMSnapshot(total_mb=total_mb, used_mb=total_mb - free_mb, free_mb=free_mb)
        return self._read_vram_via_nvidia_smi()

    @staticmethod
    def _read_vram_via_nvidia_smi() -> VRAMSnapshot:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
                 "--format=csv,noheader,nounits"], timeout=2.0,
            ).decode().strip()
            total_mb, used_mb, free_mb = (float(v) for v in out.split(","))
            return VRAMSnapshot(total_mb=total_mb, used_mb=used_mb, free_mb=free_mb)
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            return VRAMSnapshot(total_mb=0.0, used_mb=0.0, free_mb=0.0)