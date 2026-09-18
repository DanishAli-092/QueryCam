"""
QueryCam â€” Pipeline Test UI (Streamlit)
Stages: Video Ingestion -> Detection (base vs custom YOLO) -> BLIP captioning
(Qwen2.5 query layer to be wired in once ChromaDB integration is ready.)
"""

import tempfile
import cv2
import streamlit as st

import config
from video_ingestion import extract_frames, get_video_metadata
from detection import DualYoloDetector
from captioning import BlipCaptioner


st.set_page_config(page_title="QueryCam â€” Pipeline Test", layout="wide")
st.title("QueryCam â€” Pipeline Test (Streamlit)")

# --- Cache heavy model loads across reruns ---
@st.cache_resource
def load_detector():
    return DualYoloDetector()

@st.cache_resource
def load_captioner():
    return BlipCaptioner()


uploaded_video = st.file_uploader("Upload a video", type=["mp4", "avi", "mov", "mkv"])

if uploaded_video:
    # Save to a temp file so OpenCV can read it
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_video.read())
    video_path = tfile.name

    meta = get_video_metadata(video_path)
    st.caption(
        f"Duration: {meta['duration_sec']:.1f}s | FPS: {meta['fps']:.1f} | "
        f"Resolution: {meta['width']}x{meta['height']}"
    )

    interval = st.slider("Frame extraction interval (seconds)", 0.5, 5.0, config.FRAME_INTERVAL_SEC)

    if st.button("Run Pipeline"):
        with st.status("Stage 1: Ingesting video...", expanded=False):
            frames = extract_frames(video_path, interval_sec=interval)
            st.write(f"Extracted {len(frames)} frames")

        detector = load_detector()
        captioner = load_captioner()

        st.subheader("Stage 2 & 3: Detection (Base vs Custom) + Captioning")

        for ef in frames:
            base_result, custom_result = detector.run_both(ef.frame)

            # Only run BLIP if either model found something â€” saves VRAM/time
            has_detection = bool(base_result.detections or custom_result.detections)

            with st.expander(f"Frame {ef.index} â€” t={ef.timestamp_sec:.1f}s "
                              f"{'(detection found)' if has_detection else ''}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.image(
                        cv2.cvtColor(base_result.annotated_frame, cv2.COLOR_BGR2RGB),
                        caption="Base YOLOv11n (COCO pretrained)",
                    )
                    if base_result.detections:
                        st.table([
                            {"class": d.class_name, "confidence": f"{d.confidence:.2f}"}
                            for d in base_result.detections
                        ])
                    else:
                        st.write("No detections")

                with col2:
                    st.image(
                        cv2.cvtColor(custom_result.annotated_frame, cv2.COLOR_BGR2RGB),
                        caption="Custom Fine-tuned YOLOv11n (gun / bag / violence)",
                    )
                    if custom_result.detections:
                        st.table([
                            {"class": d.class_name, "confidence": f"{d.confidence:.2f}"}
                            for d in custom_result.detections
                        ])
                    else:
                        st.write("No detections")

                if has_detection:
                    caption = captioner.caption(ef.frame)
                    st.info(f"**BLIP caption:** {caption}")

        st.success("Pipeline run complete. Qwen2.5 query layer will plug in here once ChromaDB is wired up.")

