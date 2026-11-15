"""Election Commission Form 6 / 7 / 8 action classification.

Turns a matching session into a ready-to-file BLO work list:

* Form 6 (प्रारूप-6, नया नाम जोड़ना): voter is present in List B (field/check list)
  but not found in List A (reference roll).
* Form 7 (प्रारूप-7, नाम विलोपन): voter is only in List A (not found in the field),
  or the BLO remark says deceased / shifted / married away.
* Form 8 (प्रारूप-8, संशोधन): same person matched, but the roll entry has a name
  spelling, relative-name, age or gender discrepancy that needs correction.

The BLO's own remark always takes precedence over the computed suggestion.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from voter_match.core.matcher import MatchSessionResult, MatchRecordB
from voter_match.core.normalize import normalize_hindi_name
from voter_match.core.scorer import ColumnMapping, parse_age, normalize_gender
from voter_match.core.similarity import name_similarity

# Name differences at or above this similarity are typing variants (matra,
# nukta, half-letters) that the normaliser already treats as equal: no Form 8.
FORM8_NAME_SIM = 0.95

FORM_TITLES = {
    "6": "प्रारूप-6 (Form 6) — नया नाम जोड़ना",
    "7": "प्रारूप-7 (Form 7) — नाम विलोपन / आपत्ति",
    "8": "प्रारूप-8 (Form 8) — प्रविष्टि संशोधन",
}

_FORM7_HINTS = ("मृतक", "मृत", "स्थानांतरित", "विवाहोपरांत", "प्रारूप 7", "प्रारूप-7", "form 7", "दोहरी", "डुप्लिकेट")
_FORM6_HINTS = ("नया मतदाता", "प्रारूप 6", "प्रारूप-6", "form 6")
_FORM8_HINTS = ("संशोधन", "प्रारूप 8", "प्रारूप-8", "form 8", "वर्तनी", "लिपिकीय")


@dataclass
class FormAction:
    form: str               # "6", "7" or "8"
    source: str             # "B" (List B row) or "A" (List A row)
    index: int              # b_idx or a_idx
    serial_no: str
    voter_name: str
    relative_name: str
    age: str
    house_no: str
    reason: str
    remark: str = ""


def _mapping(mappings: list[ColumnMapping], role: str) -> ColumnMapping | None:
    return next((m for m in mappings if m.role == role), None)


def _val(rec: dict[str, Any] | None, col: str | None) -> str:
    if not rec or not col:
        return ""
    v = rec.get(col, "")
    s = "" if v is None else str(v).strip()
    return "" if s.lower() == "nan" else s


def _remark_form(notes: str) -> str | None:
    n = (notes or "").lower()
    if not n:
        return None
    if any(h.lower() in n for h in _FORM7_HINTS):
        return "7"
    if any(h.lower() in n for h in _FORM6_HINTS):
        return "6"
    if any(h.lower() in n for h in _FORM8_HINTS):
        return "8"
    return None


def _correction_reasons(rec: MatchRecordB, mappings: list[ColumnMapping]) -> list[str]:
    """Discrepancies between a matched B row and its assigned A row (Form 8)."""
    a = rec.assigned_record_a
    b = rec.record_b
    if not a:
        return []
    out: list[str] = []
    sr = rec.best_score_result
    for role, label in (("voter_name", "नाम वर्तनी"), ("relative_name", "सम्बन्धी नाम वर्तनी")):
        m = _mapping(mappings, role)
        if m and m.col_a and m.col_b:
            va, vb = _val(a, m.col_a), _val(b, m.col_b)
            if va and vb and va != vb:
                sim, _ = name_similarity(normalize_hindi_name(va), normalize_hindi_name(vb))
                if sim < FORM8_NAME_SIM:
                    out.append(f"{label}: '{va}' → '{vb}'")
    age_m = _mapping(mappings, "age")
    if age_m and age_m.col_a and age_m.col_b:
        aa, ab = parse_age(a.get(age_m.col_a)), parse_age(b.get(age_m.col_b))
        if aa is not None and ab is not None:
            expected = aa + int(getattr(age_m, "year_offset", 0) or 0)
            if abs(ab - expected) > age_m.tolerance:
                out.append(f"आयु: {aa} → {ab}")
    g_m = _mapping(mappings, "gender")
    if g_m and g_m.col_a and g_m.col_b:
        ga, gb = normalize_gender(a.get(g_m.col_a)), normalize_gender(b.get(g_m.col_b))
        if ga and gb and ga != gb:
            out.append(f"लिंग: {ga} → {gb}")
    if sr and sr.epic_mismatch:
        out.append("EPIC संख्या भिन्न")
    return out


def classify_form_actions(result: MatchSessionResult, mappings: list[ColumnMapping]) -> list[FormAction]:
    """Build the Form 6/7/8 work list from the (possibly BLO-reviewed) session."""
    result.recalculate_stats()
    serial = _mapping(mappings, "serial_no")
    voter = _mapping(mappings, "voter_name")
    rel = _mapping(mappings, "relative_name")
    age = _mapping(mappings, "age")
    house = _mapping(mappings, "house_no")

    def row_b(rec: MatchRecordB, form: str, reason: str) -> FormAction:
        b = rec.record_b
        return FormAction(
            form=form, source="B", index=rec.b_idx,
            serial_no=_val(b, serial.col_b if serial else None),
            voter_name=_val(b, voter.col_b if voter else None),
            relative_name=_val(b, rel.col_b if rel else None),
            age=_val(b, age.col_b if age else None),
            house_no=_val(b, house.col_b if house else None),
            reason=reason, remark=rec.notes or "",
        )

    actions: list[FormAction] = []
    for rec in result.records_b:
        if rec.is_deleted:
            continue
        by_remark = _remark_form(rec.notes)
        if by_remark == "7":
            actions.append(row_b(rec, "7", "BLO टिप्पणी अनुसार विलोपन"))
            continue
        if rec.tier == "लापता" or by_remark == "6":
            actions.append(row_b(rec, "6", "सूची A (संदर्भ नामावली) में नाम नहीं मिला"))
            continue
        if rec.tier == "मिला":
            reasons = _correction_reasons(rec, mappings)
            if reasons or by_remark == "8":
                actions.append(row_b(rec, "8", "; ".join(reasons) or "BLO टिप्पणी अनुसार संशोधन"))

    for a_idx in result.unmatched_a_indices:
        if not (0 <= a_idx < len(result.records_a)):
            continue
        a = result.records_a[a_idx]
        actions.append(FormAction(
            form="7", source="A", index=a_idx,
            serial_no=_val(a, serial.col_a if serial else None),
            voter_name=_val(a, voter.col_a if voter else None),
            relative_name=_val(a, rel.col_a if rel else None),
            age=_val(a, age.col_a if age else None),
            house_no=_val(a, house.col_a if house else None),
            reason="केवल सूची A में — स्थल पर नहीं मिला (मृत्यु/स्थानांतरण की जाँच करें)",
        ))
    return actions


def export_form_actions_excel(actions: list[FormAction], output_path: str) -> None:
    """Write one printable sheet per form with a tick column for the BLO."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from voter_match.export.excel_export import auto_fit_columns, style_print_setup, CELL_BORDER

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    headers = ["क्र०", "सूची", "कागज़ी क्र०", "मतदाता का नाम", "पिता/पति का नाम", "आयु",
               "मकान नं०", "कारण", "BLO टिप्पणी", "प्रपत्र भरा ✓"]
    fills = {"6": "FFC7CE", "7": "D9E1F2", "8": "FFEB9C"}
    for form in ("6", "7", "8"):
        rows = [a for a in actions if a.form == form]
        ws = wb.create_sheet(title=f"प्रारूप {form} ({len(rows)})")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.cell(1, 1, f"{FORM_TITLES[form]} — कुल {len(rows)} मतदाता").font = Font(
            name="Nirmala UI", size=13, bold=True, color="FFFFFF")
        ws.cell(1, 1).fill = PatternFill("solid", fgColor="1F4E79")
        ws.cell(1, 1).alignment = Alignment(horizontal="center")
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(2, c, h)
            cell.font = Font(name="Nirmala UI", bold=True)
            cell.fill = PatternFill("solid", fgColor=fills[form])
            cell.border = CELL_BORDER
        for i, a in enumerate(rows, start=1):
            vals = [i, a.source, a.serial_no, a.voter_name, a.relative_name, a.age,
                    a.house_no, a.reason, a.remark, ""]
            for c, v in enumerate(vals, start=1):
                cell = ws.cell(i + 2, c, v)
                cell.font = Font(name="Nirmala UI", size=11)
                cell.border = CELL_BORDER
        ws.freeze_panes = "A3"
        style_print_setup(ws)
        auto_fit_columns(ws, max_width=45)
    wb.save(output_path)


def export_form_actions_pdf(actions: list[FormAction], output_path: str) -> None:
    """Printable per-form checklist PDF for field use."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    # Paragraph from pdf_export applies the Devanagari ordering fallback
    from voter_match.export.pdf_export import ACTIVE_FONT, ACTIVE_FONT_BOLD, Paragraph

    title = ParagraphStyle("t", fontName=ACTIVE_FONT_BOLD, fontSize=14, leading=18,
                           textColor=colors.HexColor("#1F4E79"))
    cell = ParagraphStyle("c", fontName=ACTIVE_FONT, fontSize=8, leading=10)
    head = ParagraphStyle("h", fontName=ACTIVE_FONT_BOLD, fontSize=8, leading=10, textColor=colors.white)

    doc = SimpleDocTemplate(str(output_path), pagesize=landscape(A4),
                            leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    story: list[Any] = []
    headers = ["क्र०", "सूची", "कागज़ी क्र०", "मतदाता का नाम", "पिता/पति का नाम", "आयु", "मकान", "कारण / टिप्पणी", "भरा"]
    widths = [28, 30, 55, 120, 120, 30, 40, 340, 25]
    for n, form in enumerate(("6", "7", "8")):
        rows = [a for a in actions if a.form == form]
        if n:
            story.append(PageBreak())
        story.append(Paragraph(f"{FORM_TITLES[form]} — कुल {len(rows)} मतदाता", title))
        story.append(Spacer(1, 8))
        data = [[Paragraph(h, head) for h in headers]]
        for i, a in enumerate(rows, start=1):
            why = a.reason + (f" | टिप्पणी: {a.remark}" if a.remark else "")
            data.append([Paragraph(str(x), cell) for x in
                         (i, a.source, a.serial_no, a.voter_name, a.relative_name, a.age, a.house_no, why, "[   ]")])
        if len(data) == 1:
            data.append([Paragraph("—", cell)] + [""] * (len(headers) - 1))
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t)
    doc.build(story)
