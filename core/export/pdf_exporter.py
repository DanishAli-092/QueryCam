# """
# core/export/pdf_exporter.py
# =============================
# PDFExporter — SDS §3.1 Module 6 tail-end / §4.1 Class Diagram (<<Entity>>).

# "generate_report(session_id: str, chat_data: List[ChatRecord]): str"
# "format_layout(): void"

# Backs US-11 and TC-12 / TC-19:
#   TC-12: "PDF generated containing selected Q&A pairs, timestamps, and
#           annotated frame images, file saved to local reports folder,
#           success message with file path displayed."
#   TC-19: "Export button disabled / error: 'Select at least one interaction.'"

# Sprint 5 decision (SDS §8): "upgraded the PDF generator to optionally
# embed YOLO bounding-box frames" — generate_report() accepts an
# optional lookup so each Q&A pair can carry its supporting evidence
# frame with the detection box drawn on it.
# """

# from __future__ import annotations

# import logging
# from dataclasses import dataclass
# from datetime import datetime
# from pathlib import Path

# import config
# from dto.entities import ChatRecord

# logger = logging.getLogger("querycam.export.pdf_exporter")

# try:
#     from fpdf import FPDF
# except ImportError:  # pragma: no cover
#     FPDF = None

# REPORTS_DIR = config.DATA_DIR / "reports"
# REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# class NoInteractionsSelectedError(ValueError):
#     """TC-19: raised when generate_report() is called with an empty chat_data list."""


# @dataclass
# class EvidenceFrame:
#     """Optional per-ChatRecord supporting image (a crop or full frame with
#     the YOLO bounding box already drawn on it) for the Sprint-5 enhancement."""

#     image_path: str
#     caption: str = ""


# class PDFExporter:
#     """<<Entity>> — SDS Class Diagram."""

#     def __init__(self, page_width_mm: float = 210.0, page_height_mm: float = 297.0) -> None:
#         self.page_width_mm = page_width_mm
#         self.page_height_mm = page_height_mm

#     # ------------------------------------------------------------------ #
#     # generate_report() -> str — SDS Class Diagram
#     # ------------------------------------------------------------------ #

#     def generate_report(
#         self,
#         session_id: str,
#         chat_data: list[ChatRecord],
#         evidence_frames: dict[int, EvidenceFrame] | None = None,
#         investigator_username: str | None = None,
#     ) -> str:
#         """
#         Returns the absolute path of the generated PDF (TC-12: "success
#         message with file path displayed").

#         chat_data        : the user-selected ChatRecord rows to include.
#         evidence_frames  : optional {log_id: EvidenceFrame} — Sprint 5's
#                             "annotated frame images" enhancement.
#         """
#         if not chat_data:
#             raise NoInteractionsSelectedError("Select at least one interaction.")
#         if FPDF is None:
#             raise RuntimeError("fpdf2 is not installed. `pip install fpdf2`.")

#         evidence_frames = evidence_frames or {}
#         pdf = FPDF(orientation="P", unit="mm", format="A4")
#         pdf.set_auto_page_break(auto=True, margin=15)
#         self._render_cover_page(pdf, session_id, investigator_username, len(chat_data))

#         for record in chat_data:
#             self._render_qa_page(pdf, record, evidence_frames.get(record.log_id))

#         filename = f"querycam_report_{session_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.pdf"
#         output_path = REPORTS_DIR / filename
#         pdf.output(str(output_path))
#         logger.info("PDF report generated: %s (%d Q&A pairs)", output_path, len(chat_data))
#         return str(output_path)

#     def format_layout(self) -> None:
#         """
#         format_layout() -> void — SDS Class Diagram.

#         Kept as a distinct, overridable hook (rather than inlining
#         everything into generate_report()) so a future examiner-requested
#         letterhead/branding change touches one method, not the whole
#         export pipeline. Concrete page rendering is delegated to
#         _render_cover_page()/_render_qa_page() below, which this method
#         conceptually governs the shared styling constants for.
#         """
#         logger.debug("format_layout(): using default Query-Cam forensic report layout.")

#     # ------------------------------------------------------------------ #
#     # Internals
#     # ------------------------------------------------------------------ #

#     def _render_cover_page(
#         self, pdf: "FPDF", session_id: str, investigator_username: str | None, num_records: int
#     ) -> None:
#         self.format_layout()
#         pdf.add_page()
#         pdf.set_font("Helvetica", "B", 20)
#         pdf.cell(0, 15, "Query-Cam Forensic Analysis Report", ln=True, align="C")
#         pdf.set_font("Helvetica", "", 11)
#         pdf.ln(4)
#         pdf.cell(0, 8, f"Video Session ID: {session_id}", ln=True)
#         if investigator_username:
#             pdf.cell(0, 8, f"Investigator: {investigator_username}", ln=True)
#         pdf.cell(0, 8, f"Generated: {datetime.utcnow().isoformat(timespec='seconds')} UTC", ln=True)
#         pdf.cell(0, 8, f"Total Interactions Included: {num_records}", ln=True)
#         pdf.set_font("Helvetica", "I", 9)
#         pdf.ln(6)
#         pdf.multi_cell(
#             0, 5,
#             "This report was generated entirely offline by Query-Cam, an "
#             "air-gapped Visual-RAG forensic video analysis tool. All "
#             "answers below were synthesized locally by Qwen2.5-1.5B-Instruct "
#             "from retrieved video evidence; no data left this machine.",
#         )

#     def _render_qa_page(self, pdf: "FPDF", record: ChatRecord, evidence: EvidenceFrame | None) -> None:
#         pdf.add_page()
#         pdf.set_font("Helvetica", "B", 12)
#         pdf.multi_cell(0, 7, f"Q: {record.query_text}")
#         pdf.ln(1)

#         pdf.set_font("Helvetica", "", 11)
#         pdf.multi_cell(0, 6, f"A: {record.answer_text}")
#         pdf.ln(2)

#         pdf.set_font("Helvetica", "I", 9)
#         pdf.cell(0, 5, f"Asked: {record.timestamp}", ln=True)
#         if record.retrieved_context_ids:
#             pdf.multi_cell(0, 5, f"Retrieved evidence object IDs: {', '.join(record.retrieved_context_ids)}")

#         if evidence is not None and Path(evidence.image_path).exists():
#             pdf.ln(3)
#             try:
#                 pdf.image(evidence.image_path, w=min(120, self.page_width_mm - 40))
#                 if evidence.caption:
#                     pdf.set_font("Helvetica", "I", 8)
#                     pdf.cell(0, 5, evidence.caption, ln=True)
#             except RuntimeError:
#                 logger.warning("Could not embed evidence image: %s", evidence.image_path)


from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config
from dto.entities import ChatRecord

logger = logging.getLogger("querycam.export.pdf_exporter")

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None

REPORTS_DIR = config.DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class NoInteractionsSelectedError(ValueError):
    pass


@dataclass
class EvidenceFrame:
    image_path: str
    caption: str = ""


class PDFExporter:
    def __init__(self, page_width_mm: float = 210.0, page_height_mm: float = 297.0) -> None:
        self.page_width_mm = page_width_mm
        self.page_height_mm = page_height_mm

    def generate_report(self, session_id: str, chat_data: list[ChatRecord],
                         evidence_frames: dict[int, EvidenceFrame] | None = None,
                         investigator_username: str | None = None) -> str:
        if not chat_data:
            raise NoInteractionsSelectedError("Select at least one interaction.")
        if FPDF is None:
            raise RuntimeError("fpdf2 is not installed.")

        evidence_frames = evidence_frames or {}
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        self._render_cover_page(pdf, session_id, investigator_username, len(chat_data))
        for record in chat_data:
            self._render_qa_page(pdf, record, evidence_frames.get(record.log_id))

        filename = f"querycam_report_{session_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.pdf"
        output_path = REPORTS_DIR / filename
        pdf.output(str(output_path))
        return str(output_path)

    def format_layout(self) -> None:
        logger.debug("format_layout(): using default Query-Cam forensic report layout.")

    def _render_cover_page(self, pdf, session_id, investigator_username, num_records) -> None:
        self.format_layout()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 15, "Query-Cam Forensic Analysis Report", ln=True, align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.ln(4)
        pdf.cell(0, 8, f"Video Session ID: {session_id}", ln=True)
        if investigator_username:
            pdf.cell(0, 8, f"Investigator: {investigator_username}", ln=True)
        pdf.cell(0, 8, f"Generated: {datetime.utcnow().isoformat(timespec='seconds')} UTC", ln=True)
        pdf.cell(0, 8, f"Total Interactions Included: {num_records}", ln=True)
        pdf.set_font("Helvetica", "I", 9)
        pdf.ln(6)
        pdf.multi_cell(0, 5, "This report was generated entirely offline by Query-Cam.")

    # Evidence image is capped to this box (mm), aspect ratio preserved —
    # keeps it from overflowing onto an orphan page (FPDF's auto-page-break
    # would otherwise push an unexpectedly tall image to a near-blank new
    # page) and from being stretched into a distorted shape.
    _MAX_EVIDENCE_W_MM = 90.0
    _MAX_EVIDENCE_H_MM = 90.0

    def _render_qa_page(self, pdf, record: ChatRecord, evidence: EvidenceFrame | None) -> None:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(0, 7, f"Q: {record.query_text}")
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, f"A: {record.answer_text}")
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, f"Asked: {record.timestamp}", ln=True)
        if record.retrieved_context_ids:
            # A raw list of UUIDs is clutter a human reader can't act on —
            # just the count is enough to say "this answer is grounded in
            # retrieved evidence, not a guess".
            n = len(record.retrieved_context_ids)
            pdf.cell(0, 5, f"Grounded in {n} retrieved evidence object{'s' if n != 1 else ''}.", ln=True)

        if evidence is not None and Path(evidence.image_path).exists():
            pdf.ln(3)
            self._place_evidence_image(pdf, evidence)

    def _place_evidence_image(self, pdf, evidence: EvidenceFrame) -> None:
        """Measures the image's real pixel size and scales it to fit
        within _MAX_EVIDENCE_W_MM x _MAX_EVIDENCE_H_MM, aspect ratio
        preserved — never stretched, never tall enough to overflow the page."""
        try:
            from PIL import Image as PILImage
            with PILImage.open(evidence.image_path) as im:
                px_w, px_h = im.size
        except Exception:
            logger.warning("Could not read image dimensions: %s", evidence.image_path, exc_info=True)
            px_w, px_h = 1, 1  # fall through to a square placeholder box

        aspect = px_w / px_h if px_h else 1.0
        w_mm, h_mm = self._MAX_EVIDENCE_W_MM, self._MAX_EVIDENCE_W_MM / aspect
        if h_mm > self._MAX_EVIDENCE_H_MM:
            h_mm = self._MAX_EVIDENCE_H_MM
            w_mm = h_mm * aspect

        # Center it horizontally within the usable page width.
        x = (self.page_width_mm - w_mm) / 2
        try:
            pdf.image(evidence.image_path, x=x, w=w_mm, h=h_mm)
            if evidence.caption:
                pdf.ln(2)
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(0, 5, evidence.caption, ln=True, align="C")
        except RuntimeError:
            logger.warning("Could not embed evidence image: %s", evidence.image_path)