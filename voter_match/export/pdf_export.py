"""Printable Hindi PDF Export for Electoral Rolls.

Renders formatted Devanagari reports with Nirmala UI / Mangal font embedding,
A4 landscape tables, and color-coded verification tiers.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph as _RLParagraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from voter_match.core.matcher import MatchSessionResult
from voter_match.core.scorer import ColumnMapping

# Locate a Devanagari-capable font. Helvetica has no Hindi glyphs, so falling
# back to it renders every Hindi character as a solid black box.
WINDOWS_FONT_DIR = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
NIRMALA_REGULAR = WINDOWS_FONT_DIR / "Nirmala.ttf"
NIRMALA_BOLD = WINDOWS_FONT_DIR / "NirmalaB.ttf"

# (file name, subfont index inside a .ttc collection or None) for regular / bold.
# Windows 10/11 ship Nirmala UI only as the collection Nirmala.ttc
# (index 0 = Nirmala UI Regular, 1 = Nirmala UI Bold).
_FONT_CANDIDATES: list[tuple[tuple[str, int | None], tuple[str, int | None]]] = [
    (("Nirmala.ttc", 0), ("Nirmala.ttc", 1)),
    (("Nirmala.ttf", None), ("NirmalaB.ttf", None)),
    (("mangal.ttf", None), ("mangalb.ttf", None)),
    (("Mangal.ttf", None), ("Mangalb.ttf", None)),
    (("aparaj.ttf", None), ("aparajb.ttf", None)),
    (("kokila.ttf", None), ("kokilab.ttf", None)),
    (("utsaah.ttf", None), ("utsaahb.ttf", None)),
]

FONT_REGISTERED = False
ACTIVE_FONT = "Helvetica"
ACTIVE_FONT_BOLD = "Helvetica-Bold"


def _shaping_available() -> bool:
    """Complex-script shaping (correct matra placement and conjuncts such as प्र,
    क्ष) needs reportlab >= 4.1 plus the optional uharfbuzz package."""
    try:
        import uharfbuzz  # noqa: F401

        return True
    except Exception:
        return False


SHAPING_ENABLED = _shaping_available()


def _make_ttfont(name: str, path: Path, subfont: int | None) -> TTFont:
    kwargs: dict[str, Any] = {}
    if subfont is not None:
        kwargs["subfontIndex"] = subfont
    if SHAPING_ENABLED:
        kwargs["shapable"] = True
    try:
        return TTFont(name, str(path), **kwargs)
    except TypeError:  # older reportlab without 'shapable'
        kwargs.pop("shapable", None)
        return TTFont(name, str(path), **kwargs)


def _register_devanagari_font() -> None:
    global FONT_REGISTERED, ACTIVE_FONT, ACTIVE_FONT_BOLD
    for (reg_file, reg_idx), (bold_file, bold_idx) in _FONT_CANDIDATES:
        reg_path = WINDOWS_FONT_DIR / reg_file
        if not reg_path.exists():
            continue
        try:
            pdfmetrics.registerFont(_make_ttfont("HindiFont", reg_path, reg_idx))
        except Exception:
            continue
        ACTIVE_FONT = "HindiFont"
        ACTIVE_FONT_BOLD = "HindiFont"  # use regular weight if no bold face exists
        bold_path = WINDOWS_FONT_DIR / bold_file
        if bold_path.exists():
            try:
                pdfmetrics.registerFont(_make_ttfont("HindiFont-Bold", bold_path, bold_idx))
                ACTIVE_FONT_BOLD = "HindiFont-Bold"
            except Exception:
                pass
        FONT_REGISTERED = True
        return



_register_devanagari_font()


# --- Devanagari visual ordering fallback --------------------------------------
# Without a shaping engine reportlab draws glyphs strictly in logical order, so
# the short-i matra (ि), which is typed AFTER its consonant cluster but written
# BEFORE it, would print on the wrong side ("निकट" -> "नकिट"). When shaping is
# unavailable we move ि in front of its whole consonant cluster (e.g. स्त्रि).
_CONS = "[\u0915-\u0939\u0958-\u095F]\u093C?"
_I_MATRA_RE = re.compile(f"((?:{_CONS}\u094D)*{_CONS})\u093F")


def visual_order_devanagari(text: str) -> str:
    if SHAPING_ENABLED or not text or "\u093F" not in text:
        return text
    return _I_MATRA_RE.sub(lambda m: "\u093F" + m.group(1), text)


class Paragraph(_RLParagraph):
    """reportlab Paragraph that applies the Devanagari ordering fallback."""

    def __init__(self, text, *args, **kwargs):
        super().__init__(visual_order_devanagari(str(text)), *args, **kwargs)


class NumberedCanvas:
    """Canvas wrapper to print page numbers on footers."""
    def __init__(self, *args, **kwargs):
        pass


class PdfExporter:
    """Generates official field-ready PDF reports for BLO verification."""

    def __init__(
        self,
        session_result: MatchSessionResult,
        mappings: list[ColumnMapping],
        label_a: str = "सूची A (संदर्भ)",
        label_b: str = "सूची B (सत्यापन)",
    ):
        self.result = session_result
        self.mappings = [m for m in mappings if m.is_active()]
        self.label_a = label_a
        self.label_b = label_b

    def export(self, output_path: str | Path, max_rows_per_section: int = 200) -> None:
        """Generate PDF document with summary and categorized tables."""
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=landscape(A4),
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=25,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName=ACTIVE_FONT_BOLD,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1F4E79"),
            alignment=1,  # Center
        )
        sub_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName=ACTIVE_FONT,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#555555"),
            alignment=1,
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Normal"],
            fontName=ACTIVE_FONT_BOLD,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0D233A"),
            spaceBefore=10,
            spaceAfter=6,
        )
        cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName=ACTIVE_FONT,
            fontSize=8,
            leading=10,
        )
        cell_bold_style = ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName=ACTIVE_FONT_BOLD,
            fontSize=8,
            leading=10,
        )

        story = []

        # 1. Title Banner
        story.append(Paragraph("मतदाता सूची मिलान — आधिकारिक स्थलीय सत्यापन रिपोर्ट", title_style))
        story.append(Paragraph("Electoral Roll Fuzzy Matching Report for Booth Level Officers (BLO)", sub_style))
        story.append(Spacer(1, 12))

        # 2. Summary Statistics Table
        matched = self.result.stats.get("मिला", 0)
        review = self.result.stats.get("जाँचें", 0)
        missing = self.result.stats.get("लापता", 0)
        only_a = self.result.stats.get("केवल सूची A में", 0)
        total_b = max(1, len(self.result.records_b))

        summary_data = [
            [
                Paragraph("<b>श्रेणी (Category)</b>", cell_bold_style),
                Paragraph("<b>मतदाता संख्या</b>", cell_bold_style),
                Paragraph("<b>प्रतिशत (%)</b>", cell_bold_style),
                Paragraph("<b>अपेक्षित कार्यवाही</b>", cell_bold_style),
            ],
            [
                Paragraph("मिला (Matched)", cell_style),
                Paragraph(str(matched), cell_style),
                Paragraph(f"{(matched/total_b)*100:.1f}%", cell_style),
                Paragraph("सत्यापित मिलान - कोई कार्यवाही आवश्यक नहीं", cell_style),
            ],
            [
                Paragraph("जाँचें (Needs Review)", cell_style),
                Paragraph(str(review), cell_style),
                Paragraph(f"{(review/total_b)*100:.1f}%", cell_style),
                Paragraph("स्थलीय भौतिक सत्यापन द्वारा पुष्टि करें", cell_style),
            ],
            [
                Paragraph("लापता (Missing in A)", cell_style),
                Paragraph(str(missing), cell_style),
                Paragraph(f"{(missing/total_b)*100:.1f}%", cell_style),
                Paragraph("प्रारूप-6 (Form 6) द्वारा नाम जोड़ने की जाँच", cell_style),
            ],
            [
                Paragraph("केवल सूची A में (Only in A)", cell_style),
                Paragraph(str(only_a), cell_style),
                Paragraph("-", cell_style),
                Paragraph("प्रारूप-7/8 (Form 7/8) विलोपन/संशोधन जाँच", cell_style),
            ],
        ]

        t_summary = Table(summary_data, colWidths=[150, 80, 80, 400])
        t_summary.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#C6EFCE")),
                ("BACKGROUND", (0, 2), (0, 2), colors.HexColor("#FFEB9C")),
                ("BACKGROUND", (0, 3), (0, 3), colors.HexColor("#FFC7CE")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(t_summary)
        story.append(Spacer(1, 15))

        # 3. Tables for Review Records & Missing Records
        sections = [
            ("सत्यापन योग्य मतदाता (जाँचें — Review Required)", [r for r in self.result.records_b if r.tier == "जाँचें"]),
            ("लापता मतदाता (Missing in Reference Roll)", [r for r in self.result.records_b if r.tier == "लापता"]),
        ]

        for s_title, rec_list in sections:
            if not rec_list:
                continue

            story.append(PageBreak())
            story.append(Paragraph(f"{s_title} — कुल: {len(rec_list)}", section_style))

            table_rows = [
                [
                    Paragraph("<b>क्र०</b>", cell_bold_style),
                    Paragraph("<b>क्र० (B)</b>", cell_bold_style),
                    Paragraph("<b>क्र० (A)</b>", cell_bold_style),
                    Paragraph("<b>मतदाता (सूची B)</b>", cell_bold_style),
                    Paragraph("<b>पिता/पति (B)</b>", cell_bold_style),
                    Paragraph("<b>आयु/लिंग (B)</b>", cell_bold_style),
                    Paragraph("<b>निकटतम प्रत्याशी (सूची A)</b>", cell_bold_style),
                    Paragraph("<b>पिता/पति (A)</b>", cell_bold_style),
                    Paragraph("<b>स्कोर %</b>", cell_bold_style),
                    Paragraph("<b>सत्यापन (सही / गलत)</b>", cell_bold_style),
                    Paragraph("<b>कैफियत / हस्ताक्षर</b>", cell_bold_style),
                ]
            ]

            serial_m = next((m for m in self.mappings if m.role == "serial_no"), None)
            voter_m = next((m for m in self.mappings if m.role == "voter_name"), None)
            rel_m = next((m for m in self.mappings if m.role == "relative_name"), None)
            age_m = next((m for m in self.mappings if m.role == "age"), None)
            gen_m = next((m for m in self.mappings if m.role == "gender"), None)

            s_b = serial_m.col_b if serial_m else ""
            s_a = serial_m.col_a if serial_m else ""
            v_b = voter_m.col_b if voter_m else ""
            v_a = voter_m.col_a if voter_m else ""
            r_b = rel_m.col_b if rel_m else ""
            r_a = rel_m.col_a if rel_m else ""

            for idx, r in enumerate(rec_list[:max_rows_per_section], start=1):
                rec_b = r.record_b
                rec_a = r.assigned_record_a or (r.top_candidates[0].record_a if r.top_candidates else {})

                age_val = rec_b.get(age_m.col_b, "") if age_m else ""
                gen_val = rec_b.get(gen_m.col_b, "") if gen_m else ""
                demo = f"{age_val} / {gen_val}".strip(" /")

                score_pct = (
                    f"{int(r.best_score_result.score * 100)}%"
                    if r.best_score_result
                    else "-"
                )

                b_kram = str(rec_b.get(s_b, "") or rec_b.get("_orig_row", idx + 1))
                if r.tier == "लापता":
                    a_kram = "लापता"
                elif rec_a and s_a and s_a in rec_a:
                    a_kram = str(rec_a.get(s_a, ""))
                elif rec_a and "_orig_row" in rec_a:
                    a_kram = str(rec_a.get("_orig_row", "-"))
                else:
                    a_kram = "-"

                table_rows.append([
                    Paragraph(str(idx), cell_style),
                    Paragraph(b_kram, cell_style),
                    Paragraph(a_kram, cell_style),
                    Paragraph(str(rec_b.get(v_b, "") or ""), cell_style),
                    Paragraph(str(rec_b.get(r_b, "") or ""), cell_style),
                    Paragraph(demo, cell_style),
                    Paragraph(str(rec_a.get(v_a, "") or ""), cell_style),
                    Paragraph(str(rec_a.get(r_a, "") or ""), cell_style),
                    Paragraph(score_pct, cell_style),
                    Paragraph("", cell_style),
                    Paragraph("", cell_style),
                ])

            t_recs = Table(table_rows, colWidths=[25, 38, 38, 98, 98, 55, 98, 98, 42, 60, 125])
            t_recs.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D9D9")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ])
            )
            story.append(t_recs)

        doc.build(story)
