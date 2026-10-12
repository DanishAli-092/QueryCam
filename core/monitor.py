"""
core/monitor.py
=================
SystemMonitor — lightweight, read-only CPU/RAM/GPU/VRAM stats for the
Streamlit sidebar.

Deliberately separate from VRAMSentinel (which exists purely for the
emergency_gc() safety loop inside the mutex/lock contract, SDS §3.2.C)
— this is a UI-facing convenience with zero coupling to ingestion or
query logic.

Uses `nvidia-smi` via subprocess rather than `torch.cuda`, on purpose:
importing torch and querying `torch.cuda.mem_get_info()` from inside
the Streamlit process would initialize a CUDA context in a process
that never itself runs GPU inference — an avoidable ~200-300MB VRAM
reservation that eats directly into the 4GB budget for no benefit.
"""

from __future__ import annotations

import subprocess

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def get_system_stats() -> dict:
    """
    Returns:
        {
          "cpu_pct": float,
          "ram_used_gb": float, "ram_total_gb": float,
          "gpu_util_pct": float | None,      # None on a non-NVIDIA host
          "vram_used_mb": float | None,
          "vram_total_mb": float | None,
        }
    """
    stats: dict = {
        "cpu_pct": None, "ram_used_gb": None, "ram_total_gb": None,
        "gpu_util_pct": None, "vram_used_mb": None, "vram_total_mb": None,
    }

    if psutil is not None:
        stats["cpu_pct"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        stats["ram_used_gb"] = round(mem.used / 1e9, 2)
        stats["ram_total_gb"] = round(mem.total / 1e9, 2)

    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            timeout=2.0,
        ).decode().strip()
        gpu_util, vram_used, vram_total = (float(v) for v in out.split(","))
        stats["gpu_util_pct"] = gpu_util
        stats["vram_used_mb"] = vram_used
        stats["vram_total_mb"] = vram_total
    except (subprocess.SubprocessError, FileNotFoundError, ValueError):
        pass  # No NVIDIA driver / no GPU on this host — leave GPU fields as None.

    return stats
