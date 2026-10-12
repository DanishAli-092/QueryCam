# Query-Cam — Phase II Implementation

Offline, air-gapped Visual-RAG forensic video analysis desktop app.
Built exactly against the Phase II SDS (Class Diagram §4.1, Sequence
Diagrams §4.2.1/4.2.2, ERD §5.2, API Design §6, Test Design §9).

## Status: all 6 modules implemented and unit/integration-tested

| SDS Module | File(s) | Tested |
|---|---|---|
| 1. Layered Architecture | `app.py` → `core/controller.py` → `core/*` | ✅ import chain verified |
| 2. Security & Audit | `core/security/auth.py` | ✅ bcrypt + 3-attempt/5-min lockout |
| 3. Hardware Orchestration | `core/orchestration/{vram_sentinel,gpu_mutex}.py` | ✅ mutex acquire/release, CPU-fallback |
| 4. Data Ingestion & Filtration | `core/ingestion/motion_filter.py` | ✅ 60%+ keyframe reduction on synthetic video |
| 5. Vision-Language Processing | `core/models/{yolo_detector,blip_captioner}.py` | ✅ decode/NMS logic; lock-enforcement mocked |
| 6. RAG + Storage + Export | `core/rag/*`, `core/storage/*`, `core/export/*` | ✅ real ChromaDB + SQLite round-trips |
| Controller + UI | `core/controller.py`, `app.py` | ✅ end-to-end mocked pipeline (TC-03,04,06,07,08,10,11,13,19) |

## Running it (Windows, target hardware: Quadro M1200 4GB / 16GB RAM)

### As a real desktop application (recommended — this is what the jury sees)

```powershell
python -m venv venv
venv\Scripts\activate

# CUDA-enabled torch for BLIP (skip if CPU-only deployment):
pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cu121

# CUDA-enabled llama.cpp for Qwen (skip if CPU-only deployment):
set CMAKE_ARGS=-DGGML_CUDA=on
pip install llama-cpp-python==0.2.90 --no-cache-dir

pip install -r requirements.txt

python desktop_app.py
```

This opens Query-Cam in its own native window — no browser tab, no
address bar, a real taskbar entry. Under the hood it's still the exact
`StreamlitUI` from the SDS Class Diagram (`app.py` is untouched);
`desktop_app.py` just boots it as a headless, loopback-only
(`127.0.0.1`) local server and wraps it in a native OS WebView2 window
via `pywebview` — nothing is exposed to the network, so the
air-gapped/offline requirement (TC-15) is unaffected.

**Windows prerequisite:** the Microsoft Edge WebView2 Runtime, which
ships pre-installed on Windows 10 (2004+) and Windows 11. If it's
somehow missing, `pywebview` will prompt to install it, or grab it
from https://developer.microsoft.com/microsoft-edge/webview2/.

### Building the final standalone .exe (for the submission deliverable)

```powershell
pyinstaller --name QueryCam --windowed --onedir ^
    --add-data "app.py;." ^
    --add-data "core;core" ^
    --add-data "dto;dto" ^
    --add-data "config.py;." ^
    --add-data "data\weights;data\weights" ^
    desktop_app.py
```

Use `--onedir` (not `--onefile`) — Streamlit's own asset bundle and the
llama.cpp CUDA DLLs are large and slow to unpack from a single-file
archive on every launch. Ship the whole `dist\QueryCam\` folder.

### Bare Streamlit dev mode (for iterating on UI code only — NOT the deliverable)

```powershell
streamlit run app.py
```

This opens a browser tab, exactly like the SDS's own component actually
behaves by default — useful for fast UI iteration, but `desktop_app.py`
is what you demo and submit.

## Before you can air-gap the machine (one-time, ONLINE step)

Three model artifacts are referenced by `config.py` but are NOT bundled
in this zip (they're large binary weights, not source code):

1. **YOLOv11 Nano ONNX** — your own fine-tuned weights from the Colab
   training run (SDS §1.4). Export to ONNX and place at
   `data/weights/yolov11n_forensic_finetuned.onnx`.
2. **Qwen2.5-1.5B-Instruct GGUF (Q4_K_M)** — download once, place at
   `data/weights/qwen2.5-1.5b-instruct-q4_k_m.gguf`.
3. **BLIP-Base** and **all-MiniLM-L6-v2** — `transformers` /
   `sentence-transformers` auto-download and cache these from
   HuggingFace on first `load_model()` call. Run the app once with
   internet access so they land in the local HF cache, THEN disconnect
   — every subsequent run is 100% offline (satisfies TC-15).

## What's deliberately NOT built yet

- **Hardware telemetry dashboard widgets** (Sprint 6, SDS §8) — the
  data already exists via `controller.get_vram_status()`; only the
  polished sidebar gauge is missing.
- **Standalone .exe packaging** (PyInstaller/Nuitka) — Sprint 6.
- **Adaptive VRAM cap at runtime** (Sprint 6: "detect total VRAM at
  startup") — currently a fixed 4.0GB in `config.HardwareConfig`;
  swap for a `torch.cuda.get_device_properties(0).total_memory` read
  in `VRAMSentinel.__init__`.
- Real end-to-end test with actual YOLO/BLIP/Qwen weights loaded —
  everything here was verified with the exact wrapper *logic* (device
  resolution, lock enforcement, pre/post-processing, DB round-trips)
  mocked at the model-weights boundary, since this sandboxed dev
  environment has no GPU and no HuggingFace network access. Test this
  for real on your Quadro M1200 before the viva.

## Architecture map (for the jury walkthrough)

```
app.py (Streamlit, S1-S5 screens)
    └── core/controller.py  (QueryCamController — the ONLY class app.py talks to)
            ├── core/security/auth.py            (Module 2)
            ├── core/orchestration/               (Module 3 — the differentiator)
            │     ├── vram_sentinel.py
            │     └── gpu_mutex.py
            ├── core/ingestion/motion_filter.py   (Module 4)
            ├── core/models/                      (Module 5)
            │     ├── base.py            (AI_Model → CPU_Model / GPU_Model)
            │     ├── yolo_detector.py
            │     └── blip_captioner.py
            └── core/rag/                          (Module 6)
                  ├── vector_store.py   (ChromaDB)
                  ├── rag_engine.py     (SentenceEncoder + ChromaDB + SQLite + Qwen)
                  └── ../models/qwen_llm.py
            core/storage/sqlite_store.py           (Module 6 — the only SQL in the app)
            core/export/pdf_exporter.py            (Module 6 — US-11)
```
