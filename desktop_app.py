# """
# desktop_app.py
# ================
# The REAL entry point for the packaged desktop application.

# `app.py` (Streamlit) still contains every screen and is still the
# literal `StreamlitUI` class from the SDS Class Diagram — nothing there
# changes. This file's only job is to stop the end user from ever
# seeing a browser: it boots Streamlit as a headless local-only HTTP
# server on a private port, then opens a native OS window (via
# pywebview — a thin wrapper around the OS's own WebView2/WebKit/GTK
# component, NOT a browser) pointed at that server.

# Result: double-click this (or the .exe built from it) and you get a
# window with a title bar, a taskbar icon, no address bar, no browser
# tabs, no "Deploy" button — indistinguishable in the viva room from a
# native desktop app, while every line of UI code stays exactly what
# the SDS documented.

# Air-gapped guarantee unaffected: the server binds to 127.0.0.1 only
# (never 0.0.0.0), so it is unreachable from outside this machine even
# on a network-connected host — see start_streamlit_server()'s bind_addr.
# """

# from __future__ import annotations

# import atexit
# import logging
# import socket
# import subprocess
# import sys
# import time
# from pathlib import Path

# logger = logging.getLogger("querycam.desktop_app")
# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# APP_DIR = Path(__file__).resolve().parent
# STREAMLIT_ENTRY = APP_DIR / "app.py"
# HOST = "127.0.0.1"   # loopback only — never exposed on the LAN (air-gapped requirement)
# PORT = 8765          # fixed, non-default port to avoid colliding with a dev instance
# WINDOW_TITLE = "Query-Cam — Offline Forensic Video Analysis"
# STARTUP_TIMEOUT_SEC = 25.0


# def _port_is_open(host: str, port: int) -> bool:
#     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
#         sock.settimeout(0.5)
#         return sock.connect_ex((host, port)) == 0


# def start_streamlit_server() -> subprocess.Popen:
#     """
#     Launches `streamlit run app.py` as a child process, fully headless
#     (--server.headless true suppresses Streamlit's own "opening browser"
#     behavior — pywebview does that job instead) and with telemetry off.
#     """
#     cmd = [
#         sys.executable, "-m", "streamlit", "run", str(STREAMLIT_ENTRY),
#         "--server.headless", "true",
#         "--server.address", HOST,
#         "--server.port", str(PORT),
#         "--server.enableCORS", "false",
#         "--server.enableXsrfProtection", "true",
#         "--browser.gatherUsageStats", "false",
#         "--global.developmentMode", "false",
#     ]
#     logger.info("Starting Streamlit backend: %s", " ".join(cmd))
#     # CREATE_NO_WINDOW keeps a stray console box from flashing up on Windows
#     # when this script is itself frozen into a windowed .exe (PyInstaller).
#     creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
#     process = subprocess.Popen(
#         cmd, cwd=str(APP_DIR),
#         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#         creationflags=creationflags,
#     )
#     return process


# def wait_for_server(host: str, port: int, timeout_sec: float) -> bool:
#     deadline = time.time() + timeout_sec
#     while time.time() < deadline:
#         if _port_is_open(host, port):
#             return True
#         time.sleep(0.25)
#     return False


# def main() -> None:
#     if _port_is_open(HOST, PORT):
#         logger.warning(
#             "Port %d is already in use — assuming a Query-Cam server is "
#             "already running and attaching the window to it.", PORT,
#         )
#         server_process = None
#     else:
#         server_process = start_streamlit_server()

#         def _cleanup() -> None:
#             if server_process is not None and server_process.poll() is None:
#                 logger.info("Shutting down the Streamlit backend ...")
#                 server_process.terminate()
#                 try:
#                     server_process.wait(timeout=5)
#                 except subprocess.TimeoutExpired:
#                     server_process.kill()

#         atexit.register(_cleanup)

#         if not wait_for_server(HOST, PORT, STARTUP_TIMEOUT_SEC):
#             logger.error(
#                 "Streamlit backend did not come up within %.0fs. "
#                 "Check the console/log output above for a startup error.",
#                 STARTUP_TIMEOUT_SEC,
#             )
#             sys.exit(1)

#     # Only import webview after we know we're actually going to use it —
#     # keeps `python app.py` (the plain Streamlit dev path) free of a
#     # pywebview import that a headless CI box might not have GUI libs for.
#     import webview

#     window = webview.create_window(
#         WINDOW_TITLE,
#         url=f"http://{HOST}:{PORT}",
#         width=1440,
#         height=900,
#         min_size=(1024, 700),
#         text_select=True,
#     )
#     # gui=None lets pywebview auto-pick the OS-native backend: WebView2 on
#     # Windows (Quadro M1200 target), Cocoa/WebKit on macOS, GTK/Qt on Linux.
#     webview.start()


# if __name__ == "__main__":
#     main()


# """
# desktop_app.py
# ================
# The REAL entry point for the packaged desktop application.

# `app.py` (Streamlit) still contains every screen and is still the
# literal `StreamlitUI` class from the SDS Class Diagram — nothing there
# changes. This file's only job is to stop the end user from ever
# seeing a browser: it boots Streamlit as a headless local-only HTTP
# server on a private port, then opens a native OS window (via
# pywebview — a thin wrapper around the OS's own WebView2/WebKit/GTK
# component, NOT a browser) pointed at that server.

# Result: double-click this (or the .exe built from it) and you get a
# window with a title bar, a taskbar icon, no address bar, no browser
# tabs, no "Deploy" button — indistinguishable in the viva room from a
# native desktop app, while every line of UI code stays exactly what
# the SDS documented.

# Air-gapped guarantee unaffected: the server binds to 127.0.0.1 only
# (never 0.0.0.0), so it is unreachable from outside this machine even
# on a network-connected host — see start_streamlit_server()'s bind_addr.
# """

# from __future__ import annotations

# import atexit
# import logging
# import socket
# import subprocess
# import sys
# import time
# from pathlib import Path

# logger = logging.getLogger("querycam.desktop_app")
# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# APP_DIR = Path(__file__).resolve().parent
# STREAMLIT_ENTRY = APP_DIR / "app.py"
# HOST = "127.0.0.1"   # loopback only — never exposed on the LAN (air-gapped requirement)
# PORT = 8765          # fixed, non-default port to avoid colliding with a dev instance
# WINDOW_TITLE = "Query-Cam — Offline Forensic Video Analysis"
# STARTUP_TIMEOUT_SEC = 25.0

# # Where the Streamlit/YOLO/BLIP/Qwen backend's console output goes when run
# # under the desktop shell. Writing to a real file (instead of an unread
# # subprocess.PIPE) means the backend never blocks once its log volume
# # exceeds the OS pipe buffer during heavy ingestion logging — see the
# # docstring on start_streamlit_server() for the full explanation of why
# # that used to freeze the app at "keyframe 1/1".
# BACKEND_LOG_PATH = APP_DIR / "data" / "desktop_backend.log"


# def _port_is_open(host: str, port: int) -> bool:
#     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
#         sock.settimeout(0.5)
#         return sock.connect_ex((host, port)) == 0


# def start_streamlit_server() -> tuple[subprocess.Popen, "object"]:
#     """
#     Launches `streamlit run app.py` as a child process, fully headless
#     (--server.headless true suppresses Streamlit's own "opening browser"
#     behavior — pywebview does that job instead) and with telemetry off.

#     stdout/stderr are redirected to BACKEND_LOG_PATH rather than
#     subprocess.PIPE. A PIPE's OS buffer is small (tens of KB); nothing in
#     this file was ever reading from it, so once YOLO/BLIP ingestion
#     produced enough log lines to fill that buffer, the backend process
#     would block on its own print()/logger calls — appearing in the UI as
#     ingestion frozen forever on the current keyframe, even though no
#     actual deadlock exists in the pipeline itself. Writing to a file
#     removes that ceiling entirely while still keeping the output
#     available for troubleshooting (see BACKEND_LOG_PATH).
#     """
#     cmd = [
#         sys.executable, "-m", "streamlit", "run", str(STREAMLIT_ENTRY),
#         "--server.headless", "true",
#         "--server.address", HOST,
#         "--server.port", str(PORT),
#         "--server.enableCORS", "false",
#         "--server.enableXsrfProtection", "true",
#         "--browser.gatherUsageStats", "false",
#         "--global.developmentMode", "false",
#     ]
#     logger.info("Starting Streamlit backend: %s", " ".join(cmd))
#     logger.info("Backend console output is being written to: %s", BACKEND_LOG_PATH)

#     BACKEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
#     log_file = open(BACKEND_LOG_PATH, "w", encoding="utf-8")

#     # CREATE_NO_WINDOW keeps a stray console box from flashing up on Windows
#     # when this script is itself frozen into a windowed .exe (PyInstaller).
#     creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
#     process = subprocess.Popen(
#         cmd, cwd=str(APP_DIR),
#         stdout=log_file, stderr=subprocess.STDOUT,
#         creationflags=creationflags,
#     )
#     return process, log_file


# def wait_for_server(host: str, port: int, timeout_sec: float) -> bool:
#     deadline = time.time() + timeout_sec
#     while time.time() < deadline:
#         if _port_is_open(host, port):
#             return True
#         time.sleep(0.25)
#     return False


# def main() -> None:
#     if _port_is_open(HOST, PORT):
#         logger.warning(
#             "Port %d is already in use — assuming a Query-Cam server is "
#             "already running and attaching the window to it.", PORT,
#         )
#         server_process = None
#         log_file = None
#     else:
#         server_process, log_file = start_streamlit_server()

#         def _cleanup() -> None:
#             if server_process is not None and server_process.poll() is None:
#                 logger.info("Shutting down the Streamlit backend ...")
#                 server_process.terminate()
#                 try:
#                     server_process.wait(timeout=5)
#                 except subprocess.TimeoutExpired:
#                     server_process.kill()
#             if log_file is not None and not log_file.closed:
#                 log_file.close()

#         atexit.register(_cleanup)

#         if not wait_for_server(HOST, PORT, STARTUP_TIMEOUT_SEC):
#             logger.error(
#                 "Streamlit backend did not come up within %.0fs. "
#                 "Check %s for a startup error.",
#                 STARTUP_TIMEOUT_SEC, BACKEND_LOG_PATH,
#             )
#             sys.exit(1)

#     # Only import webview after we know we're actually going to use it —
#     # keeps `python app.py` (the plain Streamlit dev path) free of a
#     # pywebview import that a headless CI box might not have GUI libs for.
#     import webview

#     window = webview.create_window(
#         WINDOW_TITLE,
#         url=f"http://{HOST}:{PORT}",
#         width=1440,
#         height=900,
#         min_size=(1024, 700),
#         text_select=True,
#     )
#     # gui=None lets pywebview auto-pick the OS-native backend: WebView2 on
#     # Windows (Quadro M1200 target), Cocoa/WebKit on macOS, GTK/Qt on Linux.
#     webview.start()


# if __name__ == "__main__":
#     main()

"""
desktop_app.py
================
The REAL entry point for the packaged desktop application.

`app.py` (Streamlit) still contains every screen and is still the
literal `StreamlitUI` class from the SDS Class Diagram — nothing there
changes. This file's only job is to stop the end user from ever
seeing a browser: it boots Streamlit as a headless local-only HTTP
server on a private port, then opens a native OS window (via
pywebview — a thin wrapper around the OS's own WebView2/WebKit/GTK
component, NOT a browser) pointed at that server.

Result: double-click this (or the .exe built from it) and you get a
window with a title bar, a taskbar icon, no address bar, no browser
tabs, no "Deploy" button — indistinguishable in the viva room from a
native desktop app, while every line of UI code stays exactly what
the SDS documented.

Air-gapped guarantee unaffected: the server binds to 127.0.0.1 only
(never 0.0.0.0), so it is unreachable from outside this machine even
on a network-connected host — see start_streamlit_server()'s bind_addr.
"""

from __future__ import annotations

import atexit
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("querycam.desktop_app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

APP_DIR = Path(__file__).resolve().parent
STREAMLIT_ENTRY = APP_DIR / "app.py"
HOST = "127.0.0.1"   # loopback only — never exposed on the LAN (air-gapped requirement)
PORT = 8765          # fixed, non-default port to avoid colliding with a dev instance
WINDOW_TITLE = "Query-Cam — Offline Forensic Video Analysis"
STARTUP_TIMEOUT_SEC = 25.0

# Where the Streamlit/YOLO/BLIP/Qwen backend's console output goes when run
# under the desktop shell. Writing to a real file (instead of an unread
# subprocess.PIPE) means the backend never blocks once its log volume
# exceeds the OS pipe buffer during heavy ingestion logging — this is what
# used to freeze the app at "keyframe 1/1" (child process blocks on its
# own stdout write() once the unread PIPE buffer fills).
BACKEND_LOG_PATH = APP_DIR / "data" / "desktop_backend.log"


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_streamlit_server() -> tuple[subprocess.Popen, "object"]:
    """
    Launches `streamlit run app.py` as a child process, fully headless
    (--server.headless true suppresses Streamlit's own "opening browser"
    behavior — pywebview does that job instead) and with telemetry off.

    stdout/stderr are redirected to BACKEND_LOG_PATH rather than
    subprocess.PIPE — see BACKEND_LOG_PATH's docstring for why.
    """
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(STREAMLIT_ENTRY),
        "--server.headless", "true",
        "--server.address", HOST,
        "--server.port", str(PORT),
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    logger.info("Starting Streamlit backend: %s", " ".join(cmd))
    logger.info("Backend console output is being written to: %s", BACKEND_LOG_PATH)

    BACKEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(BACKEND_LOG_PATH, "w", encoding="utf-8")

    # CREATE_NO_WINDOW keeps a stray console box from flashing up on Windows
    # when this script is itself frozen into a windowed .exe (PyInstaller).
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(
        cmd, cwd=str(APP_DIR),
        stdout=log_file, stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return process, log_file


def wait_for_server(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _port_is_open(host, port):
            return True
        time.sleep(0.25)
    return False


def main() -> None:
    if _port_is_open(HOST, PORT):
        logger.warning(
            "Port %d is already in use — assuming a Query-Cam server is "
            "already running and attaching the window to it.", PORT,
        )
        server_process = None
        log_file = None
    else:
        server_process, log_file = start_streamlit_server()

        def _cleanup() -> None:
            if server_process is not None and server_process.poll() is None:
                logger.info("Shutting down the Streamlit backend ...")
                server_process.terminate()
                try:
                    server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server_process.kill()
            if log_file is not None and not log_file.closed:
                log_file.close()

        atexit.register(_cleanup)

        if not wait_for_server(HOST, PORT, STARTUP_TIMEOUT_SEC):
            logger.error(
                "Streamlit backend did not come up within %.0fs. "
                "Check %s for a startup error.",
                STARTUP_TIMEOUT_SEC, BACKEND_LOG_PATH,
            )
            sys.exit(1)

    # Only import webview after we know we're actually going to use it —
    # keeps `python app.py` (the plain Streamlit dev path) free of a
    # pywebview import that a headless CI box might not have GUI libs for.
    import webview

    # File downloads (st.download_button -> PDF report, CSV audit export)
    # are DISABLED BY DEFAULT in pywebview's WebView2/EdgeChromium backend
    # — the button is fully clickable and the click event fires, but the
    # actual save-to-disk is silently swallowed unless this is set. This
    # MUST be set before webview.start(); setting it after create_window()
    # but before start() is fine (settings are read when the webview
    # engine actually launches, not at create_window() time).
    webview.settings["ALLOW_DOWNLOADS"] = True

    window = webview.create_window(
        WINDOW_TITLE,
        url=f"http://{HOST}:{PORT}",
        width=1440,
        height=900,
        min_size=(1024, 700),
        text_select=True,
    )
    # gui=None lets pywebview auto-pick the OS-native backend: WebView2 on
    # Windows (Quadro M1200 target), Cocoa/WebKit on macOS, GTK/Qt on Linux.
    webview.start()


if __name__ == "__main__":
    main()