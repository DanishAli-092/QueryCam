# # # """
# # # app.py
# # # ======
# # # Streamlit entrypoint — SDS §7 UI/UX Design.

# # # Five screens, matching the wireframes/mockups 1:1:
# # #     S1 - Login Screen                (US-01, US-02)
# # #     S2 - Video Upload Screen         (US-03 to US-06)
# # #     S3 - Forensic Query Screen       (US-07 to US-11)
# # #     S4 - Chat History Screen         (US-10, US-12)
# # #     S5 - PDF Export Screen           (US-11)
# # # Plus a System Audit Logs screen (US-12) reachable from the sidebar.

# # # This file contains ZERO business logic — every action is a single
# # # call into QueryCamController. If you find yourself importing
# # # core.models.* or core.storage.* here, stop: that logic belongs in
# # # core/controller.py.
# # # """

# # # from __future__ import annotations

# # # import logging
# # # import subprocess

# # # import streamlit as st

# # # import config
# # # from core.controller import QueryCamController
# # # from core.monitor import get_system_stats

# # # logger = logging.getLogger("querycam.app")

# # # logging.basicConfig(level=logging.INFO)
# # # st.set_page_config(page_title="Query-Cam", page_icon="🎥", layout="wide")

# # # # Strip every visible trace of "this is a web app" — the hamburger menu,
# # # # the Streamlit "Deploy" button, the footer, and even the browser-tab
# # # # right-click context menu — so inside the desktop_app.py native window
# # # # this is indistinguishable from a native GUI, per the jury's expectation
# # # # of a real desktop application.
# # # st.markdown(
# # #     """
# # #     <style>
# # #         #MainMenu {visibility: hidden;}
# # #         header {visibility: hidden;}
# # #         footer {visibility: hidden;}
# # #         [data-testid="stToolbar"] {visibility: hidden;}
# # #         [data-testid="stDecoration"] {visibility: hidden;}

# # #         /* --- Model / lock status pills --- */
# # #         .qc-pill {
# # #             display: inline-flex; align-items: center; gap: 5px;
# # #             padding: 3px 10px; border-radius: 999px;
# # #             font-size: 0.78rem; font-weight: 600; margin: 2px 4px 2px 0;
# # #             white-space: nowrap;
# # #         }
# # #         .qc-pill-locked  { background: #3a1414; color: #ff8080; border: 1px solid #ff8080; }
# # #         .qc-pill-loaded  { background: #123a1e; color: #4ade80; border: 1px solid #4ade80; }
# # #         .qc-pill-idle    { background: #23262d; color: #9aa1ac; border: 1px solid #444a55; }

# # #         /* --- Sidebar status card --- */
# # #         .qc-card {
# # #             border: 1px solid #333844; border-radius: 10px;
# # #             padding: 10px 12px; margin-bottom: 10px; background: #14161b;
# # #         }
# # #         .qc-card-title { font-size: 0.72rem; text-transform: uppercase;
# # #                           letter-spacing: 0.06em; color: #8b93a1; margin-bottom: 6px; }
# # #     </style>
# # #     """,
# # #     unsafe_allow_html=True,
# # # )


# # # def _pill(label: str, kind: str) -> str:
# # #     """kind: 'locked' | 'loaded' | 'idle' — returns an HTML badge span."""
# # #     icon = {"locked": "🔒", "loaded": "🟢", "idle": "⚪"}[kind]
# # #     return f'<span class="qc-pill qc-pill-{kind}">{icon} {label}</span>'


# # # def render_system_status_sidebar(ctrl: QueryCamController) -> None:
# # #     """
# # #     Live dashboard: VRAM gauge + per-model lock/loaded status. This is
# # #     what makes the GPU Mutex Lock / VRAM Sentinel innovation (SDS §3.2)
# # #     VISIBLE to whoever is watching the demo, instead of being an
# # #     invisible backend guarantee.
# # #     """
# # #     if st.button("🔄 Refresh status", use_container_width=True):
# # #         st.rerun()

# # #     stats = get_system_stats()

# # #     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# # #     st.markdown('<div class="qc-card-title">VRAM (4GB budget)</div>', unsafe_allow_html=True)
# # #     if stats["vram_used_mb"] is not None:
# # #         used, total = stats["vram_used_mb"], stats["vram_total_mb"]
# # #         pct = used / total if total else 0.0
# # #         st.progress(min(pct, 1.0))
# # #         st.caption(f"{used:,.0f} MB used · {total - used:,.0f} MB free · {total:,.0f} MB total "
# # #                    f"({stats['gpu_util_pct']:.0f}% GPU util)")
# # #     else:
# # #         st.caption("No NVIDIA GPU detected on this host — running CPU-only.")
# # #     st.markdown('</div>', unsafe_allow_html=True)

# # #     if stats["cpu_pct"] is not None:
# # #         st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# # #         st.markdown('<div class="qc-card-title">CPU / RAM (16GB budget)</div>', unsafe_allow_html=True)
# # #         st.progress(min(stats["ram_used_gb"] / stats["ram_total_gb"], 1.0))
# # #         st.caption(f"CPU {stats['cpu_pct']:.0f}%  ·  RAM {stats['ram_used_gb']:.1f}/{stats['ram_total_gb']:.1f} GB")
# # #         st.markdown('</div>', unsafe_allow_html=True)

# # #     model_status = ctrl.get_model_status()
# # #     phase = model_status["gpu_lock_phase"]  # "idle" | "ingestion" | "query"

# # #     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# # #     st.markdown('<div class="qc-card-title">Model status (GPU Mutex Lock)</div>', unsafe_allow_html=True)
# # #     badges = []
# # #     for m in model_status["models"]:
# # #         if not m["gpu"]:
# # #             kind = "loaded" if m["loaded"] else "idle"
# # #             text = "Loaded" if m["loaded"] else "Idle"
# # #         else:
# # #             # A GPU model's own is_loaded flag IS the lock signal — see
# # #             # QueryCamController.get_model_status() docstring.
# # #             kind = "locked" if m["loaded"] else "idle"
# # #             text = f"Locked ({phase})" if m["loaded"] else "Released"
# # #         badges.append(_pill(f"{m['name']}: {text}", kind))
# # #     st.markdown("".join(badges), unsafe_allow_html=True)
# # #     st.markdown('</div>', unsafe_allow_html=True)


# # # # ---------------------------------------------------------------------- #
# # # # Controller lifecycle — one instance per Streamlit session
# # # # ---------------------------------------------------------------------- #

# # # def get_controller() -> QueryCamController:
# # #     if "controller" not in st.session_state:
# # #         st.session_state.controller = QueryCamController()
# # #     return st.session_state.controller


# # # def is_authenticated() -> bool:
# # #     return st.session_state.get("user_id") is not None


# # # def _ensure_browser_playable(src_path) -> str:
# # #     """
# # #     st.video() hands the file straight to an HTML5 <video> element —
# # #     inside a real browser AND inside the pywebview/WebView2 desktop
# # #     shell (desktop_app.py) — which only reliably plays H.264-in-MP4.
# # #     Arbitrary AVI/XVID/MJPEG/MPEG4-part-2 containers that OpenCV itself
# # #     reads fine (motion_filter.py, YOLO) will NOT play there — the video
# # #     element just shows a black box with a 0:00 timer forever.

# # #     Transcode once to a cached H.264 MP4 sitting next to the upload,
# # #     purely for the preview widget. The ORIGINAL file, untouched, is
# # #     still what gets passed to process_video_ingestion() — the AI
# # #     pipeline never touches this transcoded copy.
# # #     """
# # #     from pathlib import Path
# # #     src_path = Path(src_path)
# # #     preview_path = src_path.with_name(src_path.stem + "_preview.mp4")
# # #     if preview_path.exists() and preview_path.stat().st_mtime >= src_path.stat().st_mtime:
# # #         return str(preview_path)

# # #     try:
# # #         import imageio_ffmpeg
# # #         ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
# # #         cmd = [
# # #             ffmpeg_exe, "-y", "-i", str(src_path),
# # #             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
# # #             "-pix_fmt", "yuv420p",       # some players choke on yuv444/other formats
# # #             "-movflags", "+faststart",   # lets the <video> tag start playback before full download
# # #             "-an",                       # CCTV footage rarely has audio worth keeping; drops audio-codec edge cases
# # #             str(preview_path),
# # #         ]
# # #         result = subprocess.run(cmd, capture_output=True, timeout=120)
# # #         if result.returncode != 0 or not preview_path.exists():
# # #             logger.warning(
# # #                 "Preview transcode failed (rc=%s): %s — showing the original file instead "
# # #                 "(it may not play in-browser, but ingestion is unaffected).",
# # #                 result.returncode, result.stderr.decode(errors="ignore")[-400:],
# # #             )
# # #             return str(src_path)
# # #         return str(preview_path)
# # #     except Exception:  # noqa: BLE001 — preview is cosmetic; never let it block ingestion
# # #         logger.exception("Preview transcode raised — showing the original file instead.")
# # #         return str(src_path)


# # # def _get_video_info(path) -> dict:
# # #     """
# # #     Read-only look at the ORIGINAL uploaded file's container metadata
# # #     (resolution, fps, frame count, duration, size). Purely informational
# # #     for the UI — no frames are decoded or processed here.
# # #     """
# # #     from pathlib import Path

# # #     import cv2

# # #     cap = cv2.VideoCapture(str(path))
# # #     try:
# # #         fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
# # #         frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
# # #         return {
# # #             "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
# # #             "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
# # #             "fps": fps,
# # #             "total_frames": frames,
# # #             "duration_sec": frames / fps if fps else 0.0,
# # #             "size_mb": Path(path).stat().st_size / (1024 * 1024),
# # #         }
# # #     finally:
# # #         cap.release()


# # # # ---------------------------------------------------------------------- #
# # # # S1 — Login Screen (US-01, US-02)
# # # # ---------------------------------------------------------------------- #

# # # def render_login(ctrl: QueryCamController) -> None:
# # #     st.title("🎥 Query-Cam")
# # #     st.caption("Offline Forensic Video Analysis — 100% air-gapped, no cloud dependency.")

# # #     tab_login, tab_register = st.tabs(["Login", "Create Account"])

# # #     with tab_login:
# # #         with st.form("login_form"):
# # #             username = st.text_input("Username")
# # #             password = st.text_input("Password", type="password")
# # #             submitted = st.form_submit_button("Login", use_container_width=True)
# # #         if submitted:
# # #             result = ctrl.auth.authenticate(username, password)
# # #             if result.success:
# # #                 st.session_state.user_id = result.user.user_id
# # #                 st.session_state.username = result.user.username
# # #                 st.session_state.session_token = result.token
# # #                 ctrl.update_ui_display("login_success")
# # #                 st.rerun()
# # #             else:
# # #                 # TC-02: "Account locked. Contact admin." on lockout;
# # #                 # otherwise the generic invalid-credentials message.
# # #                 if "locked" in result.message.lower():
# # #                     st.error("Account locked. Contact admin.")
# # #                 else:
# # #                     st.error(result.message)

# # #     with tab_register:
# # #         with st.form("register_form"):
# # #             new_username = st.text_input("Choose a username")
# # #             new_password = st.text_input("Choose a password", type="password")
# # #             reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
# # #         if reg_submitted:
# # #             result = ctrl.auth.register(new_username, new_password)
# # #             (st.success if result.success else st.error)(result.message)


# # # # ---------------------------------------------------------------------- #
# # # # S2 — Video Upload / Ingestion Screen (US-03 to US-06)
# # # # ---------------------------------------------------------------------- #

# # # def render_ingestion_tab(ctrl: QueryCamController) -> None:
# # #     st.subheader("📤 Video Ingestion")
# # #     st.caption("Upload local CCTV footage (MP4/AVI). Processing never leaves this machine.")

# # #     uploaded = st.file_uploader("Select video file", type=["mp4", "avi", "mov", "mkv"])
# # #     if uploaded is not None:
# # #         dest_path = config.UPLOAD_DIR / uploaded.name
# # #         if not dest_path.exists() or st.session_state.get("_last_upload_name") != uploaded.name:
# # #             with open(dest_path, "wb") as f:
# # #                 f.write(uploaded.getbuffer())
# # #             st.session_state["_last_upload_name"] = uploaded.name

# # #         # Uploaded video preview — lets the person confirm they picked the
# # #         # right file before spending several minutes on the AI pipeline.
# # #         # Transcoded to browser-playable H.264 first (see
# # #         # _ensure_browser_playable's docstring for why the raw upload
# # #         # often shows a black, frozen 0:00 player otherwise).
# # #         st.markdown("**Uploaded video**")
# # #         with st.spinner("Preparing preview..."):
# # #             preview_path = _ensure_browser_playable(dest_path)
# # #         st.video(preview_path)

# # #         # Video properties — read from the ORIGINAL upload, not the
# # #         # transcoded preview (the preview's resolution/duration can differ).
# # #         info = _get_video_info(dest_path)
# # #         c1, c2, c3, c4, c5 = st.columns(5)
# # #         c1.metric("Resolution", f"{info['width']}x{info['height']}")
# # #         c2.metric("FPS", f"{info['fps']:.1f}")
# # #         c3.metric("Total frames", f"{info['total_frames']:,}")
# # #         c4.metric("Duration", f"{info['duration_sec']:.1f}s")
# # #         c5.metric("File size", f"{info['size_mb']:.1f} MB")

# # #         if st.button("Start Ingestion", type="primary"):
# # #             # st.status() gives a live-updating "which stage / which model
# # #             # is active" box instead of one opaque spinner for the whole
# # #             # ingestion — wired to QueryCamController's progress_callback.
# # #             with st.status("Starting ingestion...", expanded=True) as status_box:
# # #                 def _on_progress(stage: str) -> None:
# # #                     status_box.update(label=stage)
# # #                     status_box.write(stage)

# # #                 result = ctrl.process_video_ingestion(
# # #                     str(dest_path), st.session_state.user_id, progress_callback=_on_progress,
# # #                 )
# # #                 status_box.update(
# # #                     label="Ingestion complete" if result.success else "Ingestion failed",
# # #                     state="complete" if result.success else "error",
# # #                 )
# # #             ctrl.update_ui_display(result.message)

# # #             if result.success:
# # #                 st.success(f"{result.message} ({result.keyframe_count} keyframes indexed "
# # #                            f"of {result.total_frames} sampled frames)")
# # #                 st.session_state.active_session_id = result.session_id
# # #                 # Kept in session_state so the summary below survives reruns
# # #                 # (button clicks, tab switches) instead of vanishing.
# # #                 st.session_state["ingestion_stats"] = {
# # #                     "session_id": result.session_id,
# # #                     "video_frames": info["total_frames"],
# # #                     "sampled": result.total_frames,
# # #                     "kept": result.keyframe_count,
# # #                 }
# # #             else:
# # #                 st.error(result.message)

# # #     # Processing summary — how much of the video was actually analysed
# # #     # vs. skipped by the motion filter.
# # #     stats = st.session_state.get("ingestion_stats")
# # #     if stats and stats["session_id"] == st.session_state.get("active_session_id"):
# # #         st.markdown("**Processing summary**")
# # #         skipped = max(stats["sampled"] - stats["kept"], 0)
# # #         reduction = (skipped / stats["sampled"] * 100) if stats["sampled"] else 0.0
# # #         s1, s2, s3, s4, s5 = st.columns(5)
# # #         s1.metric("Video frames", f"{stats['video_frames']:,}")
# # #         s2.metric(f"Sampled ({config.PIPELINE.target_fps} FPS)", f"{stats['sampled']:,}")
# # #         s3.metric("Keyframes kept", f"{stats['kept']:,}")
# # #         s4.metric("Static frames skipped", f"{skipped:,}")
# # #         s5.metric("Reduction", f"{reduction:.0f}%")

# # #     # Processed Results gallery — shows every keyframe YOLO actually found
# # #     # something in, with bounding boxes drawn, so "the processed video"
# # #     # is visible, not just a success message. Renders on every rerun as
# # #     # long as a session is active, not only right after the button click.
# # #     session_id = st.session_state.get("active_session_id")
# # #     if session_id:
# # #         gallery = ctrl.get_session_gallery(session_id)
# # #         st.markdown("**Processed results** (keyframes with detections)")
# # #         if not gallery:
# # #             st.caption("No detections yet for the active session.")
# # #         else:
# # #             cols = st.columns(3)
# # #             for i, item in enumerate(gallery):
# # #                 with cols[i % 3]:
# # #                     st.image(item["frame_image_path"], width=220)
# # #                     st.caption(f"⏱ {item['timestamp_sec']:.2f}s — {item['labels']}")


# # # # ---------------------------------------------------------------------- #
# # # # S3 — Forensic Query Screen (US-07 to US-11)
# # # # ---------------------------------------------------------------------- #

# # # def render_query_tab(ctrl: QueryCamController) -> None:
# # #     st.subheader("🔎 Forensic Query")

# # #     if not st.session_state.get("active_session_id"):
# # #         st.info("Ingest a video first (Video Ingestion tab) to enable querying.")
# # #         return

# # #     session_id = st.session_state.active_session_id
# # #     st.caption(f"Active session: `{session_id}`")

# # #     for msg in st.session_state.get("chat_display", []):
# # #         with st.chat_message(msg["role"]):
# # #             st.write(msg["content"])
# # #             if msg.get("timestamps"):
# # #                 st.caption("Timestamps: " + ", ".join(msg["timestamps"]))

# # #     query_text = st.chat_input("Ask a question about this footage ...")
# # #     if query_text:
# # #         st.session_state.setdefault("chat_display", []).append({"role": "user", "content": query_text})
# # #         with st.spinner("Retrieving evidence and generating answer (GPU locked for Qwen) ..."):
# # #             result = ctrl.handle_forensic_query(session_id, st.session_state.user_id, query_text)
# # #         ctrl.update_ui_display(result.answer)

# # #         if result.success:
# # #             st.session_state.chat_display.append(
# # #                 {"role": "assistant", "content": result.answer, "timestamps": result.timestamps}
# # #             )
# # #         else:
# # #             st.session_state.chat_display.append({"role": "assistant", "content": f"⚠️ {result.message}"})
# # #         st.rerun()


# # # # ---------------------------------------------------------------------- #
# # # # S4 — Chat History Screen (US-10, US-12)
# # # # ---------------------------------------------------------------------- #

# # # def render_history_tab(ctrl: QueryCamController) -> None:
# # #     st.subheader("🕘 Chat History")

# # #     if not st.session_state.get("active_session_id"):
# # #         st.info("No active session yet.")
# # #         return

# # #     session_id = st.session_state.active_session_id
# # #     history = ctrl.get_chat_history(session_id)

# # #     if not history:
# # #         st.caption("No interactions recorded for this session yet.")
# # #     else:
# # #         st.dataframe(
# # #             [{"Time": r.timestamp, "Query": r.query_text, "Answer": r.answer_text} for r in history],
# # #             use_container_width=True,
# # #         )

# # #     col1, col2 = st.columns(2)
# # #     with col1:
# # #         if st.button("🗑️ Clear history for this session"):
# # #             st.session_state["_confirm_clear"] = True
# # #     with col2:
# # #         if st.session_state.get("_confirm_clear"):
# # #             if st.button("Confirm delete (irreversible)", type="primary"):
# # #                 ok = ctrl.clear_chat_history(session_id, st.session_state.user_id)
# # #                 st.session_state["_confirm_clear"] = False
# # #                 if ok:
# # #                     st.success("All chat logs for this session were deleted.")
# # #                     st.rerun()
# # #                 else:
# # #                     st.error("Could not clear history — see application logs.")


# # # # ---------------------------------------------------------------------- #
# # # # S5 — PDF Export Screen (US-11)
# # # # ---------------------------------------------------------------------- #

# # # def render_export_tab(ctrl: QueryCamController) -> None:
# # #     st.subheader("📄 Export PDF Report")

# # #     if not st.session_state.get("active_session_id"):
# # #         st.info("No active session yet.")
# # #         return

# # #     session_id = st.session_state.active_session_id
# # #     history = ctrl.get_chat_history(session_id)
# # #     if not history:
# # #         st.caption("No interactions to export yet.")
# # #         return

# # #     options = {f"[{r.log_id}] {r.timestamp} — {r.query_text[:60]}": r.log_id for r in history}
# # #     selected_labels = st.multiselect("Select interactions to include", list(options.keys()))
# # #     include_frames = st.checkbox("Embed annotated YOLO evidence frames", value=True)

# # #     if st.button("Export PDF", type="primary"):
# # #         # TC-19: export with nothing selected.
# # #         if not selected_labels:
# # #             st.error("Select at least one interaction.")
# # #             return
# # #         log_ids = [options[label] for label in selected_labels]
# # #         try:
# # #             pdf_path = ctrl.export_pdf(session_id, st.session_state.user_id, log_ids, include_frames)
# # #             st.success(f"PDF report generated: {pdf_path}")
# # #             with open(pdf_path, "rb") as f:
# # #                 st.download_button("Download report", f, file_name=pdf_path.split("/")[-1])
# # #         except Exception as e:  # noqa: BLE001 — surfaced to the user, then re-logged
# # #             st.error(f"Export failed: {e}")


# # # # ---------------------------------------------------------------------- #
# # # # System Audit Logs (US-12, TC-13, TC-14)
# # # # ---------------------------------------------------------------------- #

# # # def render_audit_logs(ctrl: QueryCamController) -> None:
# # #     st.subheader("🛡️ System Audit Logs")
# # #     logs = ctrl.get_system_logs(st.session_state.user_id)

# # #     action_types = sorted({log.action_type for log in logs}) or ["(none yet)"]
# # #     selected_type = st.selectbox("Filter by action type", ["ALL"] + action_types)

# # #     filtered = logs if selected_type == "ALL" else [l for l in logs if l.action_type == selected_type]
# # #     rows = [{"Time": l.event_time, "Action": l.action_type, "Details": l.details} for l in filtered]
# # #     st.dataframe(rows, use_container_width=True)

# # #     if rows:
# # #         import io
# # #         import csv
# # #         buf = io.StringIO()
# # #         writer = csv.DictWriter(buf, fieldnames=["Time", "Action", "Details"])
# # #         writer.writeheader()
# # #         writer.writerows(rows)
# # #         st.download_button("Export filtered logs as CSV", buf.getvalue(), file_name="querycam_audit_logs.csv")


# # # # ---------------------------------------------------------------------- #
# # # # Main
# # # # ---------------------------------------------------------------------- #

# # # def main() -> None:
# # #     ctrl = get_controller()

# # #     if not is_authenticated():
# # #         render_login(ctrl)
# # #         return

# # #     with st.sidebar:
# # #         st.markdown(f"**Signed in as:** {st.session_state.username}")
# # #         render_system_status_sidebar(ctrl)

# # #         if st.button("Log out"):
# # #             ctrl.auth.logout(st.session_state.get("session_token", ""))
# # #             for key in ("user_id", "username", "session_token", "active_session_id", "chat_display",
# # #                         "ingestion_stats"):
# # #                 st.session_state.pop(key, None)
# # #             st.rerun()

# # #     tabs = st.tabs(["Video Ingestion", "Forensic Query", "Chat History", "Export PDF", "System Audit"])
# # #     with tabs[0]:
# # #         render_ingestion_tab(ctrl)
# # #     with tabs[1]:
# # #         render_query_tab(ctrl)
# # #     with tabs[2]:
# # #         render_history_tab(ctrl)
# # #     with tabs[3]:
# # #         render_export_tab(ctrl)
# # #     with tabs[4]:
# # #         render_audit_logs(ctrl)


# # # if __name__ == "__main__":
# # #     main()

# # """
# # app.py
# # ======
# # Streamlit entrypoint — SDS §7 UI/UX Design.

# # Five screens, matching the wireframes/mockups 1:1:
# #     S1 - Login Screen                (US-01, US-02)
# #     S2 - Video Upload Screen         (US-03 to US-06)
# #     S3 - Forensic Query Screen       (US-07 to US-11)
# #     S4 - Chat History Screen         (US-10, US-12)
# #     S5 - PDF Export Screen           (US-11)
# # Plus a System Audit Logs screen (US-12) reachable from the sidebar.

# # This file contains ZERO business logic — every action is a single
# # call into QueryCamController. If you find yourself importing
# # core.models.* or core.storage.* here, stop: that logic belongs in
# # core/controller.py.
# # """

# # from __future__ import annotations

# # import logging

# # import streamlit as st

# # import config
# # from core.controller import QueryCamController
# # from core.monitor import get_system_stats
# # from core.video_utils import ensure_browser_playable as _ensure_browser_playable

# # logger = logging.getLogger("querycam.app")

# # logging.basicConfig(level=logging.INFO)
# # st.set_page_config(page_title="Query-Cam", page_icon="🎥", layout="wide")

# # # Strip every visible trace of "this is a web app" — the hamburger menu,
# # # the Streamlit "Deploy" button, the footer, and even the browser-tab
# # # right-click context menu — so inside the desktop_app.py native window
# # # this is indistinguishable from a native GUI, per the jury's expectation
# # # of a real desktop application.
# # st.markdown(
# #     """
# #     <style>
# #         #MainMenu {visibility: hidden;}
# #         header {visibility: hidden;}
# #         footer {visibility: hidden;}
# #         [data-testid="stToolbar"] {visibility: hidden;}
# #         [data-testid="stDecoration"] {visibility: hidden;}

# #         /* --- Model / lock status pills --- */
# #         .qc-pill {
# #             display: inline-flex; align-items: center; gap: 5px;
# #             padding: 3px 10px; border-radius: 999px;
# #             font-size: 0.78rem; font-weight: 600; margin: 2px 4px 2px 0;
# #             white-space: nowrap;
# #         }
# #         .qc-pill-locked  { background: #3a1414; color: #ff8080; border: 1px solid #ff8080; }
# #         .qc-pill-loaded  { background: #123a1e; color: #4ade80; border: 1px solid #4ade80; }
# #         .qc-pill-idle    { background: #23262d; color: #9aa1ac; border: 1px solid #444a55; }

# #         /* --- Sidebar status card --- */
# #         .qc-card {
# #             border: 1px solid #333844; border-radius: 10px;
# #             padding: 10px 12px; margin-bottom: 10px; background: #14161b;
# #         }
# #         .qc-card-title { font-size: 0.72rem; text-transform: uppercase;
# #                           letter-spacing: 0.06em; color: #8b93a1; margin-bottom: 6px; }
# #     </style>
# #     """,
# #     unsafe_allow_html=True,
# # )


# # def _pill(label: str, kind: str) -> str:
# #     """kind: 'locked' | 'loaded' | 'idle' — returns an HTML badge span."""
# #     icon = {"locked": "🔒", "loaded": "🟢", "idle": "⚪"}[kind]
# #     return f'<span class="qc-pill qc-pill-{kind}">{icon} {label}</span>'


# # def render_system_status_sidebar(ctrl: QueryCamController) -> None:
# #     """
# #     Live dashboard: VRAM gauge + per-model lock/loaded status. This is
# #     what makes the GPU Mutex Lock / VRAM Sentinel innovation (SDS §3.2)
# #     VISIBLE to whoever is watching the demo, instead of being an
# #     invisible backend guarantee.
# #     """
# #     if st.button("🔄 Refresh status", use_container_width=True):
# #         st.rerun()

# #     stats = get_system_stats()

# #     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# #     st.markdown('<div class="qc-card-title">VRAM (4GB budget)</div>', unsafe_allow_html=True)
# #     if stats["vram_used_mb"] is not None:
# #         used, total = stats["vram_used_mb"], stats["vram_total_mb"]
# #         pct = used / total if total else 0.0
# #         st.progress(min(pct, 1.0))
# #         st.caption(f"{used:,.0f} MB used · {total - used:,.0f} MB free · {total:,.0f} MB total "
# #                    f"({stats['gpu_util_pct']:.0f}% GPU util)")
# #     else:
# #         st.caption("No NVIDIA GPU detected on this host — running CPU-only.")
# #     st.markdown('</div>', unsafe_allow_html=True)

# #     if stats["cpu_pct"] is not None:
# #         st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# #         st.markdown('<div class="qc-card-title">CPU / RAM (16GB budget)</div>', unsafe_allow_html=True)
# #         st.progress(min(stats["ram_used_gb"] / stats["ram_total_gb"], 1.0))
# #         st.caption(f"CPU {stats['cpu_pct']:.0f}%  ·  RAM {stats['ram_used_gb']:.1f}/{stats['ram_total_gb']:.1f} GB")
# #         st.markdown('</div>', unsafe_allow_html=True)

# #     model_status = ctrl.get_model_status()
# #     phase = model_status["gpu_lock_phase"]  # "idle" | "ingestion" | "query"

# #     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
# #     st.markdown('<div class="qc-card-title">Model status (GPU Mutex Lock)</div>', unsafe_allow_html=True)
# #     badges = []
# #     for m in model_status["models"]:
# #         if not m["gpu"]:
# #             kind = "loaded" if m["loaded"] else "idle"
# #             text = "Loaded" if m["loaded"] else "Idle"
# #         else:
# #             # A GPU model's own is_loaded flag IS the lock signal — see
# #             # QueryCamController.get_model_status() docstring.
# #             kind = "locked" if m["loaded"] else "idle"
# #             text = f"Locked ({phase})" if m["loaded"] else "Released"
# #         badges.append(_pill(f"{m['name']}: {text}", kind))
# #     st.markdown("".join(badges), unsafe_allow_html=True)
# #     st.markdown('</div>', unsafe_allow_html=True)


# # # ---------------------------------------------------------------------- #
# # # Controller lifecycle — one instance per Streamlit session
# # # ---------------------------------------------------------------------- #

# # def get_controller() -> QueryCamController:
# #     if "controller" not in st.session_state:
# #         st.session_state.controller = QueryCamController()
# #     return st.session_state.controller


# # def is_authenticated() -> bool:
# #     return st.session_state.get("user_id") is not None




# # # ---------------------------------------------------------------------- #
# # # S1 — Login Screen (US-01, US-02)
# # # ---------------------------------------------------------------------- #

# # def render_login(ctrl: QueryCamController) -> None:
# #     st.title("🎥 Query-Cam")
# #     st.caption("Offline Forensic Video Analysis — 100% air-gapped, no cloud dependency.")

# #     tab_login, tab_register = st.tabs(["Login", "Create Account"])

# #     with tab_login:
# #         with st.form("login_form"):
# #             username = st.text_input("Username")
# #             password = st.text_input("Password", type="password")
# #             submitted = st.form_submit_button("Login", use_container_width=True)
# #         if submitted:
# #             result = ctrl.auth.authenticate(username, password)
# #             if result.success:
# #                 st.session_state.user_id = result.user.user_id
# #                 st.session_state.username = result.user.username
# #                 st.session_state.session_token = result.token
# #                 ctrl.update_ui_display("login_success")
# #                 st.rerun()
# #             else:
# #                 # TC-02: "Account locked. Contact admin." on lockout;
# #                 # otherwise the generic invalid-credentials message.
# #                 if "locked" in result.message.lower():
# #                     st.error("Account locked. Contact admin.")
# #                 else:
# #                     st.error(result.message)

# #     with tab_register:
# #         with st.form("register_form"):
# #             new_username = st.text_input("Choose a username")
# #             new_password = st.text_input("Choose a password", type="password")
# #             reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
# #         if reg_submitted:
# #             result = ctrl.auth.register(new_username, new_password)
# #             (st.success if result.success else st.error)(result.message)


# # # ---------------------------------------------------------------------- #
# # # S2 — Video Upload / Ingestion Screen (US-03 to US-06)
# # # ---------------------------------------------------------------------- #

# # def render_ingestion_tab(ctrl: QueryCamController) -> None:
# #     st.subheader("📤 Video Ingestion")
# #     st.caption("Upload local CCTV footage (MP4/AVI). Processing never leaves this machine.")

# #     uploaded = st.file_uploader("Select video file", type=["mp4", "avi", "mov", "mkv"])
# #     if uploaded is not None:
# #         dest_path = config.UPLOAD_DIR / uploaded.name
# #         if not dest_path.exists() or st.session_state.get("_last_upload_name") != uploaded.name:
# #             with open(dest_path, "wb") as f:
# #                 f.write(uploaded.getbuffer())
# #             st.session_state["_last_upload_name"] = uploaded.name

# #         # Uploaded video preview — lets the person confirm they picked the
# #         # right file before spending several minutes on the AI pipeline.
# #         # Transcoded to browser-playable H.264 first (see
# #         # _ensure_browser_playable's docstring for why the raw upload
# #         # often shows a black, frozen 0:00 player otherwise).
# #         st.markdown("**Uploaded video**")
# #         with st.spinner("Preparing preview..."):
# #             preview_path = _ensure_browser_playable(dest_path)
# #         st.video(preview_path)

# #         if st.button("Start Ingestion", type="primary"):
# #             # st.status() gives a live-updating "which stage / which model
# #             # is active" box instead of one opaque spinner for the whole
# #             # ingestion — wired to QueryCamController's progress_callback.
# #             with st.status("Starting ingestion...", expanded=True) as status_box:
# #                 def _on_progress(stage: str) -> None:
# #                     status_box.update(label=stage)
# #                     status_box.write(stage)

# #                 result = ctrl.process_video_ingestion(
# #                     str(dest_path), st.session_state.user_id, progress_callback=_on_progress,
# #                 )
# #                 status_box.update(
# #                     label="Ingestion complete" if result.success else "Ingestion failed",
# #                     state="complete" if result.success else "error",
# #                 )
# #             ctrl.update_ui_display(result.message)

# #             if result.success:
# #                 st.success(f"{result.message} ({result.keyframe_count} keyframes indexed "
# #                            f"of {result.total_frames} sampled frames)")
# #                 st.session_state.active_session_id = result.session_id
# #             else:
# #                 st.error(result.message)

# #     # Everything below renders on EVERY rerun as long as a session is
# #     # active — not only right after the "Start Ingestion" button click —
# #     # so switching tabs and coming back still shows the results.
# #     session_id = st.session_state.get("active_session_id")
# #     if session_id:
# #         # Processed video — continuous playback with bounding boxes drawn
# #         # on EVERY frame (not just the sparse motion-filtered keyframes
# #         # used for RAG indexing). Rendered once by
# #         # QueryCamController.render_annotated_video() during ingestion
# #         # and cached on disk.
# #         processed_path = ctrl.get_processed_video_path(session_id)
# #         if processed_path:
# #             st.markdown("**Processed video** (bounding boxes drawn on every frame)")
# #             st.video(processed_path)

# #         # Processed Results gallery — per-detection crops + captions,
# #         # for quickly scanning what was found without scrubbing the video.
# #         detections = ctrl.get_session_gallery(session_id)
# #         st.markdown("**Processed results** (keyframes with detections)")
# #         if not detections:
# #             st.caption("No detections yet for the active session.")
# #         else:
# #             # Re-group the flat per-object rows back into per-frame blocks
# #             # (dict preserves insertion order, and `detections` already
# #             # arrives sorted by timestamp, so this stays chronological).
# #             frames: dict[str, dict] = {}
# #             for d in detections:
# #                 frames.setdefault(d["frame_id"], {
# #                     "timestamp_sec": d["timestamp_sec"],
# #                     "frame_image_path": d["frame_image_path"],
# #                     "objects": [],
# #                 })["objects"].append(d)

# #             for frame_id, block in frames.items():
# #                 st.image(block["frame_image_path"], width=480)
# #                 st.caption(f"⏱ {block['timestamp_sec']:.2f}s — {len(block['objects'])} detection(s)")

# #                 obj_cols = st.columns(min(len(block["objects"]), 5))
# #                 for i, obj in enumerate(block["objects"]):
# #                     with obj_cols[i % len(obj_cols)]:
# #                         st.image(obj["crop_image_path"], width=120)
# #                         st.caption(f"{obj['yolo_label']} ({obj['confidence']:.2f})")
# #                 st.divider()


# # # ---------------------------------------------------------------------- #
# # # S3 — Forensic Query Screen (US-07 to US-11)
# # # ---------------------------------------------------------------------- #

# # def render_query_tab(ctrl: QueryCamController) -> None:
# #     st.subheader("🔎 Forensic Query")

# #     if not st.session_state.get("active_session_id"):
# #         st.info("Ingest a video first (Video Ingestion tab) to enable querying.")
# #         return

# #     session_id = st.session_state.active_session_id
# #     st.caption(f"Active session: `{session_id}`")

# #     for msg in st.session_state.get("chat_display", []):
# #         with st.chat_message(msg["role"]):
# #             st.write(msg["content"])
# #             if msg.get("timestamps"):
# #                 st.caption("Timestamps: " + ", ".join(msg["timestamps"]))

# #     query_text = st.chat_input("Ask a question about this footage ...")
# #     if query_text:
# #         st.session_state.setdefault("chat_display", []).append({"role": "user", "content": query_text})
# #         with st.spinner("Retrieving evidence and generating answer (GPU locked for Qwen) ..."):
# #             result = ctrl.handle_forensic_query(session_id, st.session_state.user_id, query_text)
# #         ctrl.update_ui_display(result.answer)

# #         if result.success:
# #             st.session_state.chat_display.append(
# #                 {"role": "assistant", "content": result.answer, "timestamps": result.timestamps}
# #             )
# #         else:
# #             st.session_state.chat_display.append({"role": "assistant", "content": f"⚠️ {result.message}"})
# #         st.rerun()


# # # ---------------------------------------------------------------------- #
# # # S4 — Chat History Screen (US-10, US-12)
# # # ---------------------------------------------------------------------- #

# # def render_history_tab(ctrl: QueryCamController) -> None:
# #     st.subheader("🕘 Chat History")

# #     if not st.session_state.get("active_session_id"):
# #         st.info("No active session yet.")
# #         return

# #     session_id = st.session_state.active_session_id
# #     history = ctrl.get_chat_history(session_id)

# #     if not history:
# #         st.caption("No interactions recorded for this session yet.")
# #     else:
# #         st.dataframe(
# #             [{"Time": r.timestamp, "Query": r.query_text, "Answer": r.answer_text} for r in history],
# #             use_container_width=True,
# #         )

# #     col1, col2 = st.columns(2)
# #     with col1:
# #         if st.button("🗑️ Clear history for this session"):
# #             st.session_state["_confirm_clear"] = True
# #     with col2:
# #         if st.session_state.get("_confirm_clear"):
# #             if st.button("Confirm delete (irreversible)", type="primary"):
# #                 ok = ctrl.clear_chat_history(session_id, st.session_state.user_id)
# #                 st.session_state["_confirm_clear"] = False
# #                 if ok:
# #                     st.success("All chat logs for this session were deleted.")
# #                     st.rerun()
# #                 else:
# #                     st.error("Could not clear history — see application logs.")


# # # ---------------------------------------------------------------------- #
# # # S5 — PDF Export Screen (US-11)
# # # ---------------------------------------------------------------------- #

# # def render_export_tab(ctrl: QueryCamController) -> None:
# #     st.subheader("📄 Export PDF Report")

# #     if not st.session_state.get("active_session_id"):
# #         st.info("No active session yet.")
# #         return

# #     session_id = st.session_state.active_session_id
# #     history = ctrl.get_chat_history(session_id)
# #     if not history:
# #         st.caption("No interactions to export yet.")
# #         return

# #     options = {f"[{r.log_id}] {r.timestamp} — {r.query_text[:60]}": r.log_id for r in history}
# #     selected_labels = st.multiselect("Select interactions to include", list(options.keys()))
# #     include_frames = st.checkbox("Embed annotated YOLO evidence frames", value=True)

# #     if st.button("Export PDF", type="primary"):
# #         # TC-19: export with nothing selected.
# #         if not selected_labels:
# #             st.error("Select at least one interaction.")
# #             return
# #         log_ids = [options[label] for label in selected_labels]
# #         try:
# #             pdf_path = ctrl.export_pdf(session_id, st.session_state.user_id, log_ids, include_frames)
# #             st.success(f"PDF report generated: {pdf_path}")
# #             with open(pdf_path, "rb") as f:
# #                 st.download_button("Download report", f, file_name=pdf_path.split("/")[-1])
# #         except Exception as e:  # noqa: BLE001 — surfaced to the user, then re-logged
# #             st.error(f"Export failed: {e}")


# # # ---------------------------------------------------------------------- #
# # # System Audit Logs (US-12, TC-13, TC-14)
# # # ---------------------------------------------------------------------- #

# # def render_audit_logs(ctrl: QueryCamController) -> None:
# #     st.subheader("🛡️ System Audit Logs")
# #     logs = ctrl.get_system_logs(st.session_state.user_id)

# #     action_types = sorted({log.action_type for log in logs}) or ["(none yet)"]
# #     selected_type = st.selectbox("Filter by action type", ["ALL"] + action_types)

# #     filtered = logs if selected_type == "ALL" else [l for l in logs if l.action_type == selected_type]
# #     rows = [{"Time": l.event_time, "Action": l.action_type, "Details": l.details} for l in filtered]
# #     st.dataframe(rows, use_container_width=True)

# #     if rows:
# #         import io
# #         import csv
# #         buf = io.StringIO()
# #         writer = csv.DictWriter(buf, fieldnames=["Time", "Action", "Details"])
# #         writer.writeheader()
# #         writer.writerows(rows)
# #         st.download_button("Export filtered logs as CSV", buf.getvalue(), file_name="querycam_audit_logs.csv")


# # # ---------------------------------------------------------------------- #
# # # Main
# # # ---------------------------------------------------------------------- #

# # def main() -> None:
# #     ctrl = get_controller()

# #     if not is_authenticated():
# #         render_login(ctrl)
# #         return

# #     with st.sidebar:
# #         st.markdown(f"**Signed in as:** {st.session_state.username}")
# #         render_system_status_sidebar(ctrl)

# #         if st.button("Log out"):
# #             ctrl.auth.logout(st.session_state.get("session_token", ""))
# #             for key in ("user_id", "username", "session_token", "active_session_id", "chat_display"):
# #                 st.session_state.pop(key, None)
# #             st.rerun()

# #     tabs = st.tabs(["Video Ingestion", "Forensic Query", "Chat History", "Export PDF", "System Audit"])
# #     with tabs[0]:
# #         render_ingestion_tab(ctrl)
# #     with tabs[1]:
# #         render_query_tab(ctrl)
# #     with tabs[2]:
# #         render_history_tab(ctrl)
# #     with tabs[3]:
# #         render_export_tab(ctrl)
# #     with tabs[4]:
# #         render_audit_logs(ctrl)


# # if __name__ == "__main__":
# #     main()

# """
# app.py
# ======
# Streamlit entrypoint — SDS §7 UI/UX Design.
# """

# from __future__ import annotations

# import logging

# import streamlit as st

# import config
# from core.controller import QueryCamController
# from core.monitor import get_system_stats
# from core.video_utils import ensure_browser_playable as _ensure_browser_playable
# from core.video_utils import get_video_properties, format_duration

# logger = logging.getLogger("querycam.app")

# logging.basicConfig(level=logging.INFO)
# st.set_page_config(page_title="Query-Cam", page_icon="🎥", layout="wide")

# st.markdown(
#     """
#     <style>
#         #MainMenu {visibility: hidden;}
#         header {visibility: hidden;}
#         footer {visibility: hidden;}
#         [data-testid="stToolbar"] {visibility: hidden;}
#         [data-testid="stDecoration"] {visibility: hidden;}

#         .qc-pill {
#             display: inline-flex; align-items: center; gap: 5px;
#             padding: 3px 10px; border-radius: 999px;
#             font-size: 0.78rem; font-weight: 600; margin: 2px 4px 2px 0;
#             white-space: nowrap;
#         }
#         .qc-pill-locked  { background: #3a1414; color: #ff8080; border: 1px solid #ff8080; }
#         .qc-pill-loaded  { background: #123a1e; color: #4ade80; border: 1px solid #4ade80; }
#         .qc-pill-idle    { background: #23262d; color: #9aa1ac; border: 1px solid #444a55; }

#         .qc-card {
#             border: 1px solid #333844; border-radius: 10px;
#             padding: 10px 12px; margin-bottom: 10px; background: #14161b;
#         }
#         .qc-card-title { font-size: 0.72rem; text-transform: uppercase;
#                           letter-spacing: 0.06em; color: #8b93a1; margin-bottom: 6px; }
#     </style>
#     """,
#     unsafe_allow_html=True,
# )


# def _pill(label: str, kind: str) -> str:
#     icon = {"locked": "🔒", "loaded": "🟢", "idle": "⚪"}[kind]
#     return f'<span class="qc-pill qc-pill-{kind}">{icon} {label}</span>'


# def render_system_status_sidebar(ctrl: QueryCamController) -> None:
#     if st.button("🔄 Refresh status", use_container_width=True):
#         st.rerun()

#     stats = get_system_stats()

#     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#     st.markdown('<div class="qc-card-title">VRAM (4GB budget)</div>', unsafe_allow_html=True)
#     if stats["vram_used_mb"] is not None:
#         used, total = stats["vram_used_mb"], stats["vram_total_mb"]
#         pct = used / total if total else 0.0
#         st.progress(min(pct, 1.0))
#         st.caption(f"{used:,.0f} MB used · {total - used:,.0f} MB free · {total:,.0f} MB total "
#                    f"({stats['gpu_util_pct']:.0f}% GPU util)")
#     else:
#         st.caption("No NVIDIA GPU detected on this host — running CPU-only.")
#     st.markdown('</div>', unsafe_allow_html=True)

#     if stats["cpu_pct"] is not None:
#         st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#         st.markdown('<div class="qc-card-title">CPU / RAM (16GB budget)</div>', unsafe_allow_html=True)
#         st.progress(min(stats["ram_used_gb"] / stats["ram_total_gb"], 1.0))
#         st.caption(f"CPU {stats['cpu_pct']:.0f}%  ·  RAM {stats['ram_used_gb']:.1f}/{stats['ram_total_gb']:.1f} GB")
#         st.markdown('</div>', unsafe_allow_html=True)

#     model_status = ctrl.get_model_status()
#     phase = model_status["gpu_lock_phase"]

#     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#     st.markdown('<div class="qc-card-title">Model status (GPU Mutex Lock)</div>', unsafe_allow_html=True)
#     badges = []
#     for m in model_status["models"]:
#         if not m["gpu"]:
#             kind = "loaded" if m["loaded"] else "idle"
#             text = "Loaded" if m["loaded"] else "Idle"
#         else:
#             kind = "locked" if m["loaded"] else "idle"
#             text = f"Locked ({phase})" if m["loaded"] else "Released"
#         badges.append(_pill(f"{m['name']}: {text}", kind))
#     st.markdown("".join(badges), unsafe_allow_html=True)
#     st.markdown('</div>', unsafe_allow_html=True)


# def get_controller() -> QueryCamController:
#     if "controller" not in st.session_state:
#         st.session_state.controller = QueryCamController()
#     return st.session_state.controller


# def is_authenticated() -> bool:
#     return st.session_state.get("user_id") is not None


# def render_login(ctrl: QueryCamController) -> None:
#     st.title("🎥 Query-Cam")
#     st.caption("Offline Forensic Video Analysis — 100% air-gapped, no cloud dependency.")

#     tab_login, tab_register = st.tabs(["Login", "Create Account"])

#     with tab_login:
#         with st.form("login_form"):
#             username = st.text_input("Username")
#             password = st.text_input("Password", type="password")
#             submitted = st.form_submit_button("Login", use_container_width=True)
#         if submitted:
#             result = ctrl.auth.authenticate(username, password)
#             if result.success:
#                 st.session_state.user_id = result.user.user_id
#                 st.session_state.username = result.user.username
#                 st.session_state.session_token = result.token
#                 ctrl.update_ui_display("login_success")
#                 st.rerun()
#             else:
#                 if "locked" in result.message.lower():
#                     st.error("Account locked. Contact admin.")
#                 else:
#                     st.error(result.message)

#     with tab_register:
#         with st.form("register_form"):
#             new_username = st.text_input("Choose a username")
#             new_password = st.text_input("Choose a password", type="password")
#             reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
#         if reg_submitted:
#             result = ctrl.auth.register(new_username, new_password)
#             (st.success if result.success else st.error)(result.message)


# def render_ingestion_tab(ctrl: QueryCamController) -> None:
#     st.subheader("📤 Video Ingestion")
#     st.caption("Upload local CCTV footage (MP4/AVI). Processing never leaves this machine.")

#     uploaded = st.file_uploader("Select video file", type=["mp4", "avi", "mov", "mkv"])
#     if uploaded is not None:
#         dest_path = config.UPLOAD_DIR / uploaded.name
#         if not dest_path.exists() or st.session_state.get("_last_upload_name") != uploaded.name:
#             with open(dest_path, "wb") as f:
#                 f.write(uploaded.getbuffer())
#             st.session_state["_last_upload_name"] = uploaded.name

#         # Video properties — resolution, FPS, total frames, duration, file
#         # size — shown immediately on upload, before any processing starts.
#         props = get_video_properties(dest_path)
#         st.markdown("**Video properties**")
#         p1, p2, p3, p4, p5 = st.columns(5)
#         p1.metric("Resolution", f"{props['width']}×{props['height']}" if props["width"] else "—")
#         p2.metric("FPS", f"{props['fps']:.1f}" if props["fps"] else "—")
#         p3.metric("Total Frames", f"{props['total_frames']:,}" if props["total_frames"] else "—")
#         p4.metric("Duration", format_duration(props["duration_sec"]))
#         p5.metric("File Size", f"{props['file_size_mb']:.1f} MB" if props["file_size_mb"] else "—")

#         # Uploaded video preview — transcoded to browser-playable H.264
#         # first (raw AVI/XVID uploads otherwise show a frozen 0:00 player).
#         st.markdown("**Uploaded video**")
#         with st.spinner("Preparing preview..."):
#             preview_path = _ensure_browser_playable(dest_path)
#         st.video(preview_path)

#         if st.button("Start Ingestion", type="primary"):
#             with st.status("Starting ingestion...", expanded=True) as status_box:
#                 def _on_progress(stage: str) -> None:
#                     status_box.update(label=stage)
#                     status_box.write(stage)

#                 result = ctrl.process_video_ingestion(
#                     str(dest_path), st.session_state.user_id, progress_callback=_on_progress,
#                 )
#                 status_box.update(
#                     label="Ingestion complete" if result.success else "Ingestion failed",
#                     state="complete" if result.success else "error",
#                 )
#             ctrl.update_ui_display(result.message)

#             if result.success:
#                 st.success(f"{result.message} ({result.keyframe_count} keyframes indexed "
#                            f"of {result.total_frames} sampled frames)")
#                 st.session_state.active_session_id = result.session_id
#             else:
#                 st.error(result.message)

#     # Everything below renders on EVERY rerun as long as a session is
#     # active — not only right after the "Start Ingestion" button click.
#     session_id = st.session_state.get("active_session_id")
#     if session_id:
#         processed_path = ctrl.get_processed_video_path(session_id)
#         if processed_path:
#             st.markdown("**Processed video** (bounding boxes drawn on every frame)")
#             st.video(processed_path)

#         detections = ctrl.get_session_gallery(session_id)
#         st.markdown("**Processed results** (keyframes with detections)")
#         if not detections:
#             st.caption("No detections yet for the active session.")
#         else:
#             frames: dict[str, dict] = {}
#             for d in detections:
#                 frames.setdefault(d["frame_id"], {
#                     "timestamp_sec": d["timestamp_sec"],
#                     "frame_image_path": d["frame_image_path"],
#                     "objects": [],
#                 })["objects"].append(d)

#             for frame_id, block in frames.items():
#                 st.image(block["frame_image_path"], width=480)
#                 st.caption(f"⏱ {block['timestamp_sec']:.2f}s — {len(block['objects'])} detection(s)")

#                 obj_cols = st.columns(min(len(block["objects"]), 5))
#                 for i, obj in enumerate(block["objects"]):
#                     with obj_cols[i % len(obj_cols)]:
#                         st.image(obj["crop_image_path"], width=120)
#                         st.caption(f"{obj['yolo_label']} ({obj['confidence']:.2f})")
#                 st.divider()


# def render_query_tab(ctrl: QueryCamController) -> None:
#     st.subheader("🔎 Forensic Query")

#     if not st.session_state.get("active_session_id"):
#         st.info("Ingest a video first (Video Ingestion tab) to enable querying.")
#         return

#     session_id = st.session_state.active_session_id
#     st.caption(f"Active session: `{session_id}`")

#     for msg in st.session_state.get("chat_display", []):
#         with st.chat_message(msg["role"]):
#             st.write(msg["content"])
#             if msg.get("timestamps"):
#                 st.caption("Timestamps: " + ", ".join(msg["timestamps"]))

#     query_text = st.chat_input("Ask a question about this footage ...")
#     if query_text:
#         st.session_state.setdefault("chat_display", []).append({"role": "user", "content": query_text})
#         with st.spinner("Retrieving evidence and generating answer (GPU locked for Qwen) ..."):
#             result = ctrl.handle_forensic_query(session_id, st.session_state.user_id, query_text)
#         ctrl.update_ui_display(result.answer)

#         if result.success:
#             st.session_state.chat_display.append(
#                 {"role": "assistant", "content": result.answer, "timestamps": result.timestamps})
#         else:
#             st.session_state.chat_display.append({"role": "assistant", "content": f"⚠️ {result.message}"})
#         st.rerun()


# def render_history_tab(ctrl: QueryCamController) -> None:
#     st.subheader("🕘 Chat History")

#     if not st.session_state.get("active_session_id"):
#         st.info("No active session yet.")
#         return

#     session_id = st.session_state.active_session_id
#     history = ctrl.get_chat_history(session_id)

#     if not history:
#         st.caption("No interactions recorded for this session yet.")
#     else:
#         st.dataframe(
#             [{"Time": r.timestamp, "Query": r.query_text, "Answer": r.answer_text} for r in history],
#             use_container_width=True,
#         )

#     col1, col2 = st.columns(2)
#     with col1:
#         if st.button("🗑️ Clear history for this session"):
#             st.session_state["_confirm_clear"] = True
#     with col2:
#         if st.session_state.get("_confirm_clear"):
#             if st.button("Confirm delete (irreversible)", type="primary"):
#                 ok = ctrl.clear_chat_history(session_id, st.session_state.user_id)
#                 st.session_state["_confirm_clear"] = False
#                 if ok:
#                     st.success("All chat logs for this session were deleted.")
#                     st.rerun()
#                 else:
#                     st.error("Could not clear history — see application logs.")


# def render_export_tab(ctrl: QueryCamController) -> None:
#     st.subheader("📄 Export PDF Report")

#     if not st.session_state.get("active_session_id"):
#         st.info("No active session yet.")
#         return

#     session_id = st.session_state.active_session_id
#     history = ctrl.get_chat_history(session_id)
#     if not history:
#         st.caption("No interactions to export yet.")
#         return

#     options = {f"[{r.log_id}] {r.timestamp} — {r.query_text[:60]}": r.log_id for r in history}
#     selected_labels = st.multiselect("Select interactions to include", list(options.keys()))
#     include_frames = st.checkbox("Embed annotated YOLO evidence frames", value=True)

#     if st.button("Export PDF", type="primary"):
#         if not selected_labels:
#             st.error("Select at least one interaction.")
#             return
#         log_ids = [options[label] for label in selected_labels]
#         try:
#             pdf_path = ctrl.export_pdf(session_id, st.session_state.user_id, log_ids, include_frames)
#             st.success(f"PDF report generated: {pdf_path}")
#             with open(pdf_path, "rb") as f:
#                 st.download_button("Download report", f, file_name=pdf_path.split("/")[-1])
#         except Exception as e:  # noqa: BLE001
#             st.error(f"Export failed: {e}")


# def render_audit_logs(ctrl: QueryCamController) -> None:
#     st.subheader("🛡️ System Audit Logs")
#     logs = ctrl.get_system_logs(st.session_state.user_id)

#     action_types = sorted({log.action_type for log in logs}) or ["(none yet)"]
#     selected_type = st.selectbox("Filter by action type", ["ALL"] + action_types)

#     filtered = logs if selected_type == "ALL" else [l for l in logs if l.action_type == selected_type]
#     rows = [{"Time": l.event_time, "Action": l.action_type, "Details": l.details} for l in filtered]
#     st.dataframe(rows, use_container_width=True)

#     if rows:
#         import io
#         import csv
#         buf = io.StringIO()
#         writer = csv.DictWriter(buf, fieldnames=["Time", "Action", "Details"])
#         writer.writeheader()
#         writer.writerows(rows)
#         st.download_button("Export filtered logs as CSV", buf.getvalue(), file_name="querycam_audit_logs.csv")


# def main() -> None:
#     ctrl = get_controller()

#     if not is_authenticated():
#         render_login(ctrl)
#         return

#     with st.sidebar:
#         st.markdown(f"**Signed in as:** {st.session_state.username}")
#         render_system_status_sidebar(ctrl)

#         if st.button("Log out"):
#             ctrl.auth.logout(st.session_state.get("session_token", ""))
#             for key in ("user_id", "username", "session_token", "active_session_id", "chat_display"):
#                 st.session_state.pop(key, None)
#             st.rerun()

#     tabs = st.tabs(["Video Ingestion", "Forensic Query", "Chat History", "Export PDF", "System Audit"])
#     with tabs[0]:
#         render_ingestion_tab(ctrl)
#     with tabs[1]:
#         render_query_tab(ctrl)
#     with tabs[2]:
#         render_history_tab(ctrl)
#     with tabs[3]:
#         render_export_tab(ctrl)
#     with tabs[4]:
#         render_audit_logs(ctrl)


# if __name__ == "__main__":
#     main()

# """
# app.py
# ======
# Streamlit entrypoint — SDS §7 UI/UX Design.
# """

# from __future__ import annotations

# import logging

# import pandas as pd
# import streamlit as st

# import config
# from core.controller import QueryCamController
# from core.monitor import get_system_stats
# from core.video_utils import ensure_browser_playable as _ensure_browser_playable
# from core.video_utils import get_video_properties, format_duration

# logger = logging.getLogger("querycam.app")

# logging.basicConfig(level=logging.INFO)
# st.set_page_config(page_title="Query-Cam", page_icon="🎥", layout="wide")

# st.markdown(
#     """
#     <style>
#         #MainMenu {visibility: hidden;}
#         header {visibility: hidden;}
#         footer {visibility: hidden;}
#         [data-testid="stToolbar"] {visibility: hidden;}
#         [data-testid="stDecoration"] {visibility: hidden;}

#         .qc-pill {
#             display: inline-flex; align-items: center; gap: 5px;
#             padding: 3px 10px; border-radius: 999px;
#             font-size: 0.78rem; font-weight: 600; margin: 2px 4px 2px 0;
#             white-space: nowrap;
#         }
#         .qc-pill-locked  { background: #3a1414; color: #ff8080; border: 1px solid #ff8080; }
#         .qc-pill-loaded  { background: #123a1e; color: #4ade80; border: 1px solid #4ade80; }
#         .qc-pill-idle    { background: #23262d; color: #9aa1ac; border: 1px solid #444a55; }

#         .qc-card {
#             border: 1px solid #333844; border-radius: 10px;
#             padding: 10px 12px; margin-bottom: 10px; background: #14161b;
#         }
#         .qc-card-title { font-size: 0.72rem; text-transform: uppercase;
#                           letter-spacing: 0.06em; color: #8b93a1; margin-bottom: 6px; }
#     </style>
#     """,
#     unsafe_allow_html=True,
# )


# def _pill(label: str, kind: str) -> str:
#     icon = {"locked": "🔒", "loaded": "🟢", "idle": "⚪"}[kind]
#     return f'<span class="qc-pill qc-pill-{kind}">{icon} {label}</span>'


# def render_system_status_sidebar(ctrl: QueryCamController) -> None:
#     if st.button("🔄 Refresh status", use_container_width=True):
#         st.rerun()

#     stats = get_system_stats()

#     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#     st.markdown('<div class="qc-card-title">VRAM (4GB budget)</div>', unsafe_allow_html=True)
#     if stats["vram_used_mb"] is not None:
#         used, total = stats["vram_used_mb"], stats["vram_total_mb"]
#         pct = used / total if total else 0.0
#         st.progress(min(pct, 1.0))
#         st.caption(f"{used:,.0f} MB used · {total - used:,.0f} MB free · {total:,.0f} MB total "
#                    f"({stats['gpu_util_pct']:.0f}% GPU util)")
#     else:
#         st.caption("No NVIDIA GPU detected on this host — running CPU-only.")
#     st.markdown('</div>', unsafe_allow_html=True)

#     if stats["cpu_pct"] is not None:
#         st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#         st.markdown('<div class="qc-card-title">CPU / RAM (16GB budget)</div>', unsafe_allow_html=True)
#         st.progress(min(stats["ram_used_gb"] / stats["ram_total_gb"], 1.0))
#         st.caption(f"CPU {stats['cpu_pct']:.0f}%  ·  RAM {stats['ram_used_gb']:.1f}/{stats['ram_total_gb']:.1f} GB")
#         st.markdown('</div>', unsafe_allow_html=True)

#     model_status = ctrl.get_model_status()
#     phase = model_status["gpu_lock_phase"]

#     st.markdown('<div class="qc-card">', unsafe_allow_html=True)
#     st.markdown('<div class="qc-card-title">Model status (GPU Mutex Lock)</div>', unsafe_allow_html=True)
#     badges = []
#     for m in model_status["models"]:
#         if not m["gpu"]:
#             kind = "loaded" if m["loaded"] else "idle"
#             text = "Loaded" if m["loaded"] else "Idle"
#         else:
#             kind = "locked" if m["loaded"] else "idle"
#             text = f"Locked ({phase})" if m["loaded"] else "Released"
#         badges.append(_pill(f"{m['name']}: {text}", kind))
#     st.markdown("".join(badges), unsafe_allow_html=True)
#     st.markdown('</div>', unsafe_allow_html=True)


# def render_hardware_proof(ctrl: QueryCamController, session_id: str) -> None:
#     """
#     Live proof of the two SDS §3.2 design targets, computed from the
#     ACTUAL just-completed ingestion run — not claimed, measured:
#       1. Motion filter keyframe reduction (target: >=60% discarded)
#       2. Peak VRAM during ingestion (target: never breaches 3.20GB)
#     Plus the VRAM-over-time chart that makes the BLIP-then-Qwen GPU
#     Mutex handoff visually obvious instead of an invisible guarantee.
#     """
#     frame_stats = ctrl.get_frame_stats(session_id)
#     peak_status = ctrl.get_peak_vram_status(session_id)
#     history = ctrl.get_vram_history(session_id)

#     if frame_stats is None and peak_status is None:
#         return  # nothing recorded yet for this session (e.g. ingestion not run this app session)

#     st.markdown("**Hardware constraint proof** (this run)")
#     c1, c2 = st.columns(2)

#     with c1:
#         if frame_stats is not None:
#             target_pct = config.PIPELINE.min_keyframe_reduction_pct * 100
#             actual_pct = frame_stats["reduction_pct"] * 100
#             met = actual_pct >= target_pct
#             st.metric(
#                 "Motion filter reduction",
#                 f"{actual_pct:.1f}%",
#                 delta=f"{'✅ meets' if met else '⚠️ below'} {target_pct:.0f}% target",
#                 delta_color="normal" if met else "inverse",
#             )
#             st.caption(
#                 f"{frame_stats['total_native_frames']:,} native frames → "
#                 f"{frame_stats['sampled_frame_count']:,} sampled (5 FPS) → "
#                 f"{frame_stats['keyframe_count']:,} keyframes kept"
#             )

#     with c2:
#         if peak_status is not None:
#             met = peak_status["within_budget"]
#             st.metric(
#                 "Peak VRAM this run",
#                 f"{peak_status['peak_gb']:.2f} GB",
#                 delta=f"{'✅ within' if met else '⚠️ exceeded'} {peak_status['budget_gb']:.2f}GB budget",
#                 delta_color="normal" if met else "inverse",
#             )
#             st.caption(f"Hard ceiling: {config.HARDWARE.total_vram_gb:.0f}GB total VRAM "
#                       f"(Quadro M1200) · Safety cap: {config.HARDWARE.vram_safety_cap_pct*100:.0f}%")

#     # total_mb == 0 is VRAMSentinel's explicit "no real GPU reading"
#     # sentinel (CPU-only host / nvidia-smi unavailable) — exclude those
#     # before deciding whether there's a real timeline to plot.
#     real_readings = [h for h in history if h["total_mb"] > 0]
#     if real_readings:
#         df = pd.DataFrame(real_readings).set_index("t")[["used_mb"]]
#         df.columns = ["VRAM Used (MB)"]
#         st.line_chart(df, height=220)
#         st.caption(
#             "Timeline spans the full ingestion run — the dip after the peak is "
#             "BLIP unloading (Mutex release + emergency_gc()) before the GPU is "
#             "freed again."
#         )
#     else:
#         st.caption("No VRAM samples recorded — likely a CPU-only host (no NVIDIA GPU detected).")


# def get_controller() -> QueryCamController:
#     if "controller" not in st.session_state:
#         st.session_state.controller = QueryCamController()
#     return st.session_state.controller


# def is_authenticated() -> bool:
#     return st.session_state.get("user_id") is not None


# def render_login(ctrl: QueryCamController) -> None:
#     st.title("🎥 Query-Cam")
#     st.caption("Offline Forensic Video Analysis — 100% air-gapped, no cloud dependency.")

#     tab_login, tab_register = st.tabs(["Login", "Create Account"])

#     with tab_login:
#         with st.form("login_form"):
#             username = st.text_input("Username")
#             password = st.text_input("Password", type="password")
#             submitted = st.form_submit_button("Login", use_container_width=True)
#         if submitted:
#             result = ctrl.auth.authenticate(username, password)
#             if result.success:
#                 st.session_state.user_id = result.user.user_id
#                 st.session_state.username = result.user.username
#                 st.session_state.session_token = result.token
#                 ctrl.update_ui_display("login_success")
#                 st.rerun()
#             else:
#                 if "locked" in result.message.lower():
#                     st.error("Account locked. Contact admin.")
#                 else:
#                     st.error(result.message)

#     with tab_register:
#         with st.form("register_form"):
#             new_username = st.text_input("Choose a username")
#             new_password = st.text_input("Choose a password", type="password")
#             reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
#         if reg_submitted:
#             result = ctrl.auth.register(new_username, new_password)
#             (st.success if result.success else st.error)(result.message)


# def render_ingestion_tab(ctrl: QueryCamController) -> None:
#     st.subheader("📤 Video Ingestion")
#     st.caption("Upload local CCTV footage (MP4/AVI). Processing never leaves this machine.")

#     uploaded = st.file_uploader("Select video file", type=["mp4", "avi", "mov", "mkv"])
#     if uploaded is not None:
#         dest_path = config.UPLOAD_DIR / uploaded.name
#         if not dest_path.exists() or st.session_state.get("_last_upload_name") != uploaded.name:
#             with open(dest_path, "wb") as f:
#                 f.write(uploaded.getbuffer())
#             st.session_state["_last_upload_name"] = uploaded.name

#         # Video properties — resolution, FPS, total frames, duration, file
#         # size — shown immediately on upload, before any processing starts.
#         props = get_video_properties(dest_path)
#         st.markdown("**Video properties**")
#         p1, p2, p3, p4, p5 = st.columns(5)
#         p1.metric("Resolution", f"{props['width']}×{props['height']}" if props["width"] else "—")
#         p2.metric("FPS", f"{props['fps']:.1f}" if props["fps"] else "—")
#         p3.metric("Total Frames", f"{props['total_frames']:,}" if props["total_frames"] else "—")
#         p4.metric("Duration", format_duration(props["duration_sec"]))
#         p5.metric("File Size", f"{props['file_size_mb']:.1f} MB" if props["file_size_mb"] else "—")

#         # Uploaded video preview — transcoded to browser-playable H.264
#         # first (raw AVI/XVID uploads otherwise show a frozen 0:00 player).
#         st.markdown("**Uploaded video**")
#         with st.spinner("Preparing preview..."):
#             preview_path = _ensure_browser_playable(dest_path)
#         st.video(preview_path)

#         if st.button("Start Ingestion", type="primary"):
#             with st.status("Starting ingestion...", expanded=True) as status_box:
#                 def _on_progress(stage: str) -> None:
#                     status_box.update(label=stage)
#                     status_box.write(stage)

#                 result = ctrl.process_video_ingestion(
#                     str(dest_path), st.session_state.user_id, progress_callback=_on_progress,
#                 )
#                 status_box.update(
#                     label="Ingestion complete" if result.success else "Ingestion failed",
#                     state="complete" if result.success else "error",
#                 )
#             ctrl.update_ui_display(result.message)

#             if result.success:
#                 st.success(f"{result.message} ({result.keyframe_count} keyframes indexed "
#                            f"of {result.total_frames} sampled frames)")
#                 st.session_state.active_session_id = result.session_id
#             else:
#                 st.error(result.message)

#     # Everything below renders on EVERY rerun as long as a session is
#     # active — not only right after the "Start Ingestion" button click.
#     session_id = st.session_state.get("active_session_id")
#     if session_id:
#         render_hardware_proof(ctrl, session_id)

#         processed_path = ctrl.get_processed_video_path(session_id)
#         if processed_path:
#             st.markdown("**Processed video** (bounding boxes drawn on every frame)")
#             st.video(processed_path)

#         detections = ctrl.get_session_gallery(session_id)
#         st.markdown("**Processed results** (keyframes with detections)")
#         if not detections:
#             st.caption("No detections yet for the active session.")
#         else:
#             frames: dict[str, dict] = {}
#             for d in detections:
#                 frames.setdefault(d["frame_id"], {
#                     "timestamp_sec": d["timestamp_sec"],
#                     "frame_image_path": d["frame_image_path"],
#                     "objects": [],
#                 })["objects"].append(d)

#             for frame_id, block in frames.items():
#                 st.image(block["frame_image_path"], width=480)
#                 st.caption(f"⏱ {block['timestamp_sec']:.2f}s — {len(block['objects'])} detection(s)")

#                 obj_cols = st.columns(min(len(block["objects"]), 5))
#                 for i, obj in enumerate(block["objects"]):
#                     with obj_cols[i % len(obj_cols)]:
#                         st.image(obj["crop_image_path"], width=120)
#                         st.caption(f"{obj['yolo_label']} ({obj['confidence']:.2f})")
#                 st.divider()


# def render_query_tab(ctrl: QueryCamController) -> None:
#     st.subheader("🔎 Forensic Query")

#     if not st.session_state.get("active_session_id"):
#         st.info("Ingest a video first (Video Ingestion tab) to enable querying.")
#         return

#     session_id = st.session_state.active_session_id
#     st.caption(f"Active session: `{session_id}`")

#     for msg in st.session_state.get("chat_display", []):
#         with st.chat_message(msg["role"]):
#             st.write(msg["content"])
#             if msg.get("timestamps"):
#                 st.caption("Timestamps: " + ", ".join(msg["timestamps"]))

#     query_text = st.chat_input("Ask a question about this footage ...")
#     if query_text:
#         st.session_state.setdefault("chat_display", []).append({"role": "user", "content": query_text})
#         with st.spinner("Retrieving evidence and generating answer (GPU locked for Qwen) ..."):
#             result = ctrl.handle_forensic_query(session_id, st.session_state.user_id, query_text)
#         ctrl.update_ui_display(result.answer)

#         if result.success:
#             st.session_state.chat_display.append(
#                 {"role": "assistant", "content": result.answer, "timestamps": result.timestamps})
#         else:
#             st.session_state.chat_display.append({"role": "assistant", "content": f"⚠️ {result.message}"})
#         st.rerun()


# def render_history_tab(ctrl: QueryCamController) -> None:
#     st.subheader("🕘 Chat History")

#     if not st.session_state.get("active_session_id"):
#         st.info("No active session yet.")
#         return

#     session_id = st.session_state.active_session_id
#     history = ctrl.get_chat_history(session_id)

#     if not history:
#         st.caption("No interactions recorded for this session yet.")
#     else:
#         st.dataframe(
#             [{"Time": r.timestamp, "Query": r.query_text, "Answer": r.answer_text} for r in history],
#             use_container_width=True,
#         )

#     col1, col2 = st.columns(2)
#     with col1:
#         if st.button("🗑️ Clear history for this session"):
#             st.session_state["_confirm_clear"] = True
#     with col2:
#         if st.session_state.get("_confirm_clear"):
#             if st.button("Confirm delete (irreversible)", type="primary"):
#                 ok = ctrl.clear_chat_history(session_id, st.session_state.user_id)
#                 st.session_state["_confirm_clear"] = False
#                 if ok:
#                     st.success("All chat logs for this session were deleted.")
#                     st.rerun()
#                 else:
#                     st.error("Could not clear history — see application logs.")


# def render_export_tab(ctrl: QueryCamController) -> None:
#     st.subheader("📄 Export PDF Report")

#     if not st.session_state.get("active_session_id"):
#         st.info("No active session yet.")
#         return

#     session_id = st.session_state.active_session_id
#     history = ctrl.get_chat_history(session_id)
#     if not history:
#         st.caption("No interactions to export yet.")
#         return

#     options = {f"[{r.log_id}] {r.timestamp} — {r.query_text[:60]}": r.log_id for r in history}
#     selected_labels = st.multiselect("Select interactions to include", list(options.keys()))
#     include_frames = st.checkbox("Embed annotated YOLO evidence frames", value=True)

#     if st.button("Export PDF", type="primary"):
#         if not selected_labels:
#             st.error("Select at least one interaction.")
#             return
#         log_ids = [options[label] for label in selected_labels]
#         try:
#             pdf_path = ctrl.export_pdf(session_id, st.session_state.user_id, log_ids, include_frames)
#             st.success(f"PDF report generated: {pdf_path}")
#             with open(pdf_path, "rb") as f:
#                 st.download_button("Download report", f, file_name=pdf_path.split("/")[-1])
#         except Exception as e:  # noqa: BLE001
#             st.error(f"Export failed: {e}")


# def render_audit_logs(ctrl: QueryCamController) -> None:
#     st.subheader("🛡️ System Audit Logs")
#     logs = ctrl.get_system_logs(st.session_state.user_id)

#     action_types = sorted({log.action_type for log in logs}) or ["(none yet)"]
#     selected_type = st.selectbox("Filter by action type", ["ALL"] + action_types)

#     filtered = logs if selected_type == "ALL" else [l for l in logs if l.action_type == selected_type]
#     rows = [{"Time": l.event_time, "Action": l.action_type, "Details": l.details} for l in filtered]
#     st.dataframe(rows, use_container_width=True)

#     if rows:
#         import io
#         import csv
#         buf = io.StringIO()
#         writer = csv.DictWriter(buf, fieldnames=["Time", "Action", "Details"])
#         writer.writeheader()
#         writer.writerows(rows)
#         st.download_button("Export filtered logs as CSV", buf.getvalue(), file_name="querycam_audit_logs.csv")


# def main() -> None:
#     ctrl = get_controller()

#     if not is_authenticated():
#         render_login(ctrl)
#         return

#     with st.sidebar:
#         st.markdown(f"**Signed in as:** {st.session_state.username}")
#         render_system_status_sidebar(ctrl)

#         if st.button("Log out"):
#             ctrl.auth.logout(st.session_state.get("session_token", ""))
#             for key in ("user_id", "username", "session_token", "active_session_id", "chat_display"):
#                 st.session_state.pop(key, None)
#             st.rerun()

#     tabs = st.tabs(["Video Ingestion", "Forensic Query", "Chat History", "Export PDF", "System Audit"])
#     with tabs[0]:
#         render_ingestion_tab(ctrl)
#     with tabs[1]:
#         render_query_tab(ctrl)
#     with tabs[2]:
#         render_history_tab(ctrl)
#     with tabs[3]:
#         render_export_tab(ctrl)
#     with tabs[4]:
#         render_audit_logs(ctrl)


# if __name__ == "__main__":
#     main()

"""
app.py
======
Streamlit entrypoint — SDS §7 UI/UX Design.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

import config
from core.controller import QueryCamController
from core.monitor import get_system_stats
from core.video_utils import ensure_browser_playable as _ensure_browser_playable
from core.video_utils import get_video_properties, format_duration

logger = logging.getLogger("querycam.app")

logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="Query-Cam", page_icon="🎥", layout="wide")

st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        [data-testid="stToolbar"] {visibility: hidden;}
        [data-testid="stDecoration"] {visibility: hidden;}

        .qc-pill {
            display: inline-flex; align-items: center; gap: 5px;
            padding: 3px 10px; border-radius: 999px;
            font-size: 0.78rem; font-weight: 600; margin: 2px 4px 2px 0;
            white-space: nowrap;
        }
        .qc-pill-locked  { background: #3a1414; color: #ff8080; border: 1px solid #ff8080; }
        .qc-pill-loaded  { background: #123a1e; color: #4ade80; border: 1px solid #4ade80; }
        .qc-pill-idle    { background: #23262d; color: #9aa1ac; border: 1px solid #444a55; }

        .qc-card {
            border: 1px solid #333844; border-radius: 10px;
            padding: 10px 12px; margin-bottom: 10px; background: #14161b;
        }
        .qc-card-title { font-size: 0.72rem; text-transform: uppercase;
                          letter-spacing: 0.06em; color: #8b93a1; margin-bottom: 6px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _pill(label: str, kind: str) -> str:
    icon = {"locked": "🔒", "loaded": "🟢", "idle": "⚪"}[kind]
    return f'<span class="qc-pill qc-pill-{kind}">{icon} {label}</span>'


def render_system_status_sidebar(ctrl: QueryCamController) -> None:
    if st.button("🔄 Refresh status", use_container_width=True):
        st.rerun()

    stats = get_system_stats()

    st.markdown('<div class="qc-card">', unsafe_allow_html=True)
    st.markdown('<div class="qc-card-title">VRAM (4GB budget)</div>', unsafe_allow_html=True)
    if stats["vram_used_mb"] is not None:
        used, total = stats["vram_used_mb"], stats["vram_total_mb"]
        pct = used / total if total else 0.0
        st.progress(min(pct, 1.0))
        st.caption(f"{used:,.0f} MB used · {total - used:,.0f} MB free · {total:,.0f} MB total "
                   f"({stats['gpu_util_pct']:.0f}% GPU util)")
    else:
        st.caption("No NVIDIA GPU detected on this host — running CPU-only.")
    st.markdown('</div>', unsafe_allow_html=True)

    if stats["cpu_pct"] is not None:
        st.markdown('<div class="qc-card">', unsafe_allow_html=True)
        st.markdown('<div class="qc-card-title">CPU / RAM (16GB budget)</div>', unsafe_allow_html=True)
        st.progress(min(stats["ram_used_gb"] / stats["ram_total_gb"], 1.0))
        st.caption(f"CPU {stats['cpu_pct']:.0f}%  ·  RAM {stats['ram_used_gb']:.1f}/{stats['ram_total_gb']:.1f} GB")
        st.markdown('</div>', unsafe_allow_html=True)

    model_status = ctrl.get_model_status()
    phase = model_status["gpu_lock_phase"]

    st.markdown('<div class="qc-card">', unsafe_allow_html=True)
    st.markdown('<div class="qc-card-title">Model status (GPU Mutex Lock)</div>', unsafe_allow_html=True)
    badges = []
    for m in model_status["models"]:
        if not m["gpu"]:
            kind = "loaded" if m["loaded"] else "idle"
            text = "Loaded" if m["loaded"] else "Idle"
        else:
            kind = "locked" if m["loaded"] else "idle"
            text = f"Locked ({phase})" if m["loaded"] else "Released"
        badges.append(_pill(f"{m['name']}: {text}", kind))
    st.markdown("".join(badges), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_hardware_proof(ctrl: QueryCamController, session_id: str) -> None:
    """
    Live proof of the two SDS §3.2 design targets, computed from the
    ACTUAL just-completed ingestion run — not claimed, measured:
      1. Motion filter keyframe reduction (target: >=60% discarded)
      2. Peak VRAM during ingestion (target: never breaches 3.20GB)
    Plus the VRAM-over-time chart that makes the BLIP-then-Qwen GPU
    Mutex handoff visually obvious instead of an invisible guarantee.
    """
    frame_stats = ctrl.get_frame_stats(session_id)
    peak_status = ctrl.get_peak_vram_status(session_id)
    history = ctrl.get_vram_history(session_id)

    if frame_stats is None and peak_status is None:
        return  # nothing recorded yet for this session (e.g. ingestion not run this app session)

    st.markdown("**Hardware constraint proof** (this run)")
    c1, c2 = st.columns(2)

    with c1:
        if frame_stats is not None:
            target_pct = config.PIPELINE.min_keyframe_reduction_pct * 100
            actual_pct = frame_stats["reduction_pct"] * 100
            met = actual_pct >= target_pct
            st.metric(
                "Motion filter reduction",
                f"{actual_pct:.1f}%",
                delta=f"{'✅ meets' if met else '⚠️ below'} {target_pct:.0f}% target",
                delta_color="normal" if met else "inverse",
            )
            st.caption(
                f"{frame_stats['total_native_frames']:,} native frames → "
                f"{frame_stats['sampled_frame_count']:,} sampled (5 FPS) → "
                f"{frame_stats['keyframe_count']:,} keyframes kept"
            )

    with c2:
        if peak_status is not None:
            met = peak_status["within_budget"]
            st.metric(
                "Peak VRAM this run",
                f"{peak_status['peak_gb']:.2f} GB",
                delta=f"{'✅ within' if met else '⚠️ exceeded'} {peak_status['budget_gb']:.2f}GB budget",
                delta_color="normal" if met else "inverse",
            )
            st.caption(f"Hard ceiling: {config.HARDWARE.total_vram_gb:.0f}GB total VRAM "
                      f"(Quadro M1200) · Safety cap: {config.HARDWARE.vram_safety_cap_pct*100:.0f}%")

    # total_mb == 0 is VRAMSentinel's explicit "no real GPU reading"
    # sentinel (CPU-only host / nvidia-smi unavailable) — exclude those
    # before deciding whether there's a real timeline to plot.
    real_readings = [h for h in history if h["total_mb"] > 0]
    if real_readings:
        df = pd.DataFrame(real_readings).set_index("t")[["used_mb"]]
        df.columns = ["VRAM Used (MB)"]
        st.line_chart(df, height=220)
        st.caption(
            "Timeline spans the full ingestion run — the dip after the peak is "
            "BLIP unloading (Mutex release + emergency_gc()) before the GPU is "
            "freed again."
        )
    else:
        st.caption("No VRAM samples recorded — likely a CPU-only host (no NVIDIA GPU detected).")


def get_controller() -> QueryCamController:
    if "controller" not in st.session_state:
        st.session_state.controller = QueryCamController()
    return st.session_state.controller


def is_authenticated() -> bool:
    return st.session_state.get("user_id") is not None


def render_login(ctrl: QueryCamController) -> None:
    st.title("🎥 Query-Cam")
    st.caption("Offline Forensic Video Analysis — 100% air-gapped, no cloud dependency.")

    tab_login, tab_register = st.tabs(["Login", "Create Account"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            result = ctrl.auth.authenticate(username, password)
            if result.success:
                st.session_state.user_id = result.user.user_id
                st.session_state.username = result.user.username
                st.session_state.session_token = result.token
                ctrl.update_ui_display("login_success")
                st.rerun()
            else:
                if "locked" in result.message.lower():
                    st.error("Account locked. Contact admin.")
                else:
                    st.error(result.message)

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
        if reg_submitted:
            result = ctrl.auth.register(new_username, new_password)
            (st.success if result.success else st.error)(result.message)


def render_ingestion_tab(ctrl: QueryCamController) -> None:
    st.subheader("📤 Video Ingestion")
    st.caption("Upload local CCTV footage (MP4/AVI). Processing never leaves this machine.")

    uploaded = st.file_uploader("Select video file", type=["mp4", "avi", "mov", "mkv"])
    if uploaded is not None:
        dest_path = config.UPLOAD_DIR / uploaded.name
        if not dest_path.exists() or st.session_state.get("_last_upload_name") != uploaded.name:
            with open(dest_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.session_state["_last_upload_name"] = uploaded.name

        # Video properties — resolution, FPS, total frames, duration, file
        # size — shown immediately on upload, before any processing starts.
        props = get_video_properties(dest_path)
        st.markdown("**Video properties**")
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("Resolution", f"{props['width']}×{props['height']}" if props["width"] else "—")
        p2.metric("FPS", f"{props['fps']:.1f}" if props["fps"] else "—")
        p3.metric("Total Frames", f"{props['total_frames']:,}" if props["total_frames"] else "—")
        p4.metric("Duration", format_duration(props["duration_sec"]))
        p5.metric("File Size", f"{props['file_size_mb']:.1f} MB" if props["file_size_mb"] else "—")

        # Uploaded video preview — transcoded to browser-playable H.264
        # first (raw AVI/XVID uploads otherwise show a frozen 0:00 player).
        st.markdown("**Uploaded video**")
        with st.spinner("Preparing preview..."):
            preview_path = _ensure_browser_playable(dest_path)
        st.video(preview_path)

        if st.button("Start Ingestion", type="primary"):
            with st.status("Starting ingestion...", expanded=True) as status_box:
                def _on_progress(stage: str) -> None:
                    status_box.update(label=stage)
                    status_box.write(stage)

                result = ctrl.process_video_ingestion(
                    str(dest_path), st.session_state.user_id, progress_callback=_on_progress,
                )
                status_box.update(
                    label="Ingestion complete" if result.success else "Ingestion failed",
                    state="complete" if result.success else "error",
                )
            ctrl.update_ui_display(result.message)

            if result.success:
                st.success(f"{result.message} ({result.keyframe_count} keyframes indexed "
                           f"of {result.total_frames} sampled frames)")
                st.session_state.active_session_id = result.session_id
            else:
                st.error(result.message)

    # Everything below renders on EVERY rerun as long as a session is
    # active — not only right after the "Start Ingestion" button click.
    session_id = st.session_state.get("active_session_id")
    if session_id:
        render_hardware_proof(ctrl, session_id)

        processed_path = ctrl.get_processed_video_path(session_id)
        if processed_path:
            st.markdown("**Processed video** (bounding boxes drawn on every frame)")
            st.video(processed_path)

        detections = ctrl.get_session_gallery(session_id)
        st.markdown("**Processed results** (keyframes with detections)")
        if not detections:
            st.caption("No detections yet for the active session.")
        else:
            frames: dict[str, dict] = {}
            for d in detections:
                frames.setdefault(d["frame_id"], {
                    "timestamp_sec": d["timestamp_sec"],
                    "frame_image_path": d["frame_image_path"],
                    "objects": [],
                })["objects"].append(d)

            for frame_id, block in frames.items():
                st.image(block["frame_image_path"], width=480)
                st.caption(f"⏱ {block['timestamp_sec']:.2f}s — {len(block['objects'])} detection(s)")

                obj_cols = st.columns(min(len(block["objects"]), 5))
                for i, obj in enumerate(block["objects"]):
                    with obj_cols[i % len(obj_cols)]:
                        st.image(obj["crop_image_path"], width=120)
                        st.caption(f"{obj['yolo_label']} ({obj['confidence']:.2f})")
                st.divider()


def render_query_tab(ctrl: QueryCamController) -> None:
    st.subheader("🔎 Forensic Query")

    if not st.session_state.get("active_session_id"):
        st.info("Ingest a video first (Video Ingestion tab) to enable querying.")
        return

    session_id = st.session_state.active_session_id
    st.caption(f"Active session: `{session_id}`")

    for msg in st.session_state.get("chat_display", []):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("timestamps"):
                st.caption("Timestamps: " + ", ".join(msg["timestamps"]))

    query_text = st.chat_input("Ask a question about this footage ...")
    if query_text:
        st.session_state.setdefault("chat_display", []).append({"role": "user", "content": query_text})

        # Same live-progress pattern as ingestion's st.status() — this is
        # what actually lets you WATCH the GPU Mutex Lock acquire/release
        # for Qwen in real time, instead of a single opaque spinner that
        # hides the whole blocking call (and instead of the sidebar, which
        # only re-renders once per script run and therefore can never
        # catch a lock that's acquired-and-released within one blocking call).
        with st.status("Processing query...", expanded=True) as status_box:
            def _on_progress(stage: str) -> None:
                status_box.update(label=stage)
                status_box.write(stage)

            result = ctrl.handle_forensic_query(
                session_id, st.session_state.user_id, query_text, progress_callback=_on_progress,
            )
            status_box.update(
                label="Query complete" if result.success else "Query failed",
                state="complete" if result.success else "error",
            )
        ctrl.update_ui_display(result.answer)

        if result.success:
            st.session_state.chat_display.append(
                {"role": "assistant", "content": result.answer, "timestamps": result.timestamps})
        else:
            st.session_state.chat_display.append({"role": "assistant", "content": f"⚠️ {result.message}"})
        st.rerun()


def render_history_tab(ctrl: QueryCamController) -> None:
    st.subheader("🕘 Chat History")

    if not st.session_state.get("active_session_id"):
        st.info("No active session yet.")
        return

    session_id = st.session_state.active_session_id
    history = ctrl.get_chat_history(session_id)

    if not history:
        st.caption("No interactions recorded for this session yet.")
    else:
        st.dataframe(
            [{"Time": r.timestamp, "Query": r.query_text, "Answer": r.answer_text} for r in history],
            use_container_width=True,
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear history for this session"):
            st.session_state["_confirm_clear"] = True
    with col2:
        if st.session_state.get("_confirm_clear"):
            if st.button("Confirm delete (irreversible)", type="primary"):
                ok = ctrl.clear_chat_history(session_id, st.session_state.user_id)
                st.session_state["_confirm_clear"] = False
                if ok:
                    st.success("All chat logs for this session were deleted.")
                    st.rerun()
                else:
                    st.error("Could not clear history — see application logs.")


def render_export_tab(ctrl: QueryCamController) -> None:
    st.subheader("📄 Export PDF Report")

    if not st.session_state.get("active_session_id"):
        st.info("No active session yet.")
        return

    session_id = st.session_state.active_session_id
    history = ctrl.get_chat_history(session_id)
    if not history:
        st.caption("No interactions to export yet.")
        return

    options = {f"[{r.log_id}] {r.timestamp} — {r.query_text[:60]}": r.log_id for r in history}
    selected_labels = st.multiselect("Select interactions to include", list(options.keys()))
    include_frames = st.checkbox("Embed annotated YOLO evidence frames", value=True)

    if st.button("Export PDF", type="primary"):
            # TC-19: export with nothing selected.
        if not selected_labels:
            st.error("Select at least one interaction.")
        else:
            log_ids = [options[label] for label in selected_labels]
            try:
                pdf_path = ctrl.export_pdf(session_id, st.session_state.user_id, log_ids, include_frames)
                st.session_state["last_pdf_path"] = pdf_path
                st.success(f"PDF report generated: {pdf_path}")
            except Exception as e:  # noqa: BLE001 — surfaced to the user, then re-logged
                st.error(f"Export failed: {e}")

    # Download button lives OUTSIDE the "Export PDF" button block so it
    # survives the rerun its own click triggers (Streamlit reruns the whole
    # script on every widget click — if this button were nested inside
    # `if st.button("Export PDF")`, that condition would be False on the
    # rerun caused by clicking "Download report" itself, making the
    # download button vanish before the browser could receive the file).
    last_pdf = st.session_state.get("last_pdf_path")
    if last_pdf:
        from pathlib import Path
        pdf_file = Path(last_pdf)
        if pdf_file.exists():
            with open(pdf_file, "rb") as f:
                st.download_button("Download report", f, file_name=pdf_file.name)
        else:
            st.warning("The previously generated report file is missing. Export again.")


def render_audit_logs(ctrl: QueryCamController) -> None:
    st.subheader("🛡️ System Audit Logs")
    logs = ctrl.get_system_logs(st.session_state.user_id)

    action_types = sorted({log.action_type for log in logs}) or ["(none yet)"]
    selected_type = st.selectbox("Filter by action type", ["ALL"] + action_types)

    filtered = logs if selected_type == "ALL" else [l for l in logs if l.action_type == selected_type]
    rows = [{"Time": l.event_time, "Action": l.action_type, "Details": l.details} for l in filtered]
    st.dataframe(rows, use_container_width=True)

    if rows:
        import io
        import csv
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["Time", "Action", "Details"])
        writer.writeheader()
        writer.writerows(rows)
        st.download_button("Export filtered logs as CSV", buf.getvalue(), file_name="querycam_audit_logs.csv")


def main() -> None:
    ctrl = get_controller()

    if not is_authenticated():
        render_login(ctrl)
        return

    with st.sidebar:
        st.markdown(f"**Signed in as:** {st.session_state.username}")
        render_system_status_sidebar(ctrl)

        if st.button("Log out"):
            ctrl.auth.logout(st.session_state.get("session_token", ""))
            for key in ("user_id", "username", "session_token", "active_session_id", "chat_display"):
                st.session_state.pop(key, None)
            st.rerun()

    tabs = st.tabs(["Video Ingestion", "Forensic Query", "Chat History", "Export PDF", "System Audit"])
    with tabs[0]:
        render_ingestion_tab(ctrl)
    with tabs[1]:
        render_query_tab(ctrl)
    with tabs[2]:
        render_history_tab(ctrl)
    with tabs[3]:
        render_export_tab(ctrl)
    with tabs[4]:
        render_audit_logs(ctrl)


if __name__ == "__main__":
    main()