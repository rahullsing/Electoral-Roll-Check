"""Comprehensive Hindi Excel Export for Electoral Rolls.

Generates official BLO field-verification workbooks using openpyxl with
two-level headers, print optimization (A4 landscape, fit-to-width, repeat headers),
pen-marking columns (सही/गलत/टिप्पणी), user review decisions, frozen panes, autofilters, and color-coding.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from voter_match.core.matcher import MatchSessionResult, MatchRecordB
from voter_match.core.scorer import ColumnMapping

# Color Palette
COLOR_GREEN = "C6EFCE"     # मिला
COLOR_YELLOW = "FFEB9C"    # जाँचें
COLOR_RED = "FFC7CE"       # लापता
COLOR_HEADER_A = "D9E1F2"  # List A Header (Soft Blue)
COLOR_HEADER_B = "E2EFDA"  # List B Header (Soft Green)
COLOR_HEADER_GEN = "F2F2F2"# Neutral Header (Gray)
COLOR_TITLE = "1F4E79"     # Deep Navy Title

FONT_NAME = "Nirmala UI"
BASE_FONT = Font(name=FONT_NAME, size=11)
BOLD_FONT = Font(name=FONT_NAME, size=11, bold=True)
TITLE_FONT = Font(name=FONT_NAME, size=14, bold=True, color="FFFFFF")

THIN_BORDER_SIDE = Side(border_style="thin", color="D9D9D9")
CELL_BORDER = Border(
    left=THIN_BORDER_SIDE,
    right=THIN_BORDER_SIDE,
    top=THIN_BORDER_SIDE,
    bottom=THIN_BORDER_SIDE,
)
HEADER_BORDER = Border(
    left=THIN_BORDER_SIDE,
    right=THIN_BORDER_SIDE,
    top=Side(border_style="medium", color="7F7F7F"),
    bottom=Side(border_style="medium", color="7F7F7F"),
)


def style_print_setup(ws: openpyxl.worksheet.worksheet.Worksheet, title_rows: str = "1:2") -> None:
    """Configure worksheet for A4 Landscape printing with repeated headers and footer page numbers."""
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = title_rows
    ws.oddFooter.center.text = "पृष्ठ &P / &N"
    ws.oddFooter.right.text = "निर्वाचक नामावली मिलान (BLO सत्यापन)"


def auto_fit_columns(ws: openpyxl.worksheet.worksheet.Worksheet, min_width: int = 12, max_width: int = 35) -> None:
    """Adjust column widths appropriately for Hindi text and English headers."""
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if "\n" in val_str:
                lines = val_str.split("\n")
                val_str = max(lines, key=len)
            length = sum(1.4 if ord(ch) > 127 else 1.0 for ch in val_str)
            if length > max_len:
                max_len = int(length)
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 3, max_width))


class ExcelExporter:
    """Generates multi-sheet formatted workbook for BLO field review."""

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

    def export(self, output_path: str | Path) -> None:
        """Create and save the full Excel workbook with updated BLO decisions."""
        # Ensure stats and unassigned records reflect live review overrides
        self.result.recalculate_stats()

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # 1. Summary Sheet
        self._create_summary_sheet(wb)

        # 2. Missing in A (लापता मतदाता)
        self._create_records_sheet(
            wb,
            sheet_title="1. लापता मतदाता",
            records=[r for r in self.result.records_b if r.tier == "लापता"],
            banner_text="लापता मतदाता (सूची B में उपलब्ध लेकिन सूची A में नहीं मिले)",
        )

        # 3. Needs Review (जाँचें)
        self._create_records_sheet(
            wb,
            sheet_title="2. जाँचें",
            records=[r for r in self.result.records_b if r.tier == "जाँचें"],
            banner_text="सत्यापन योग्य मतदाता (आंशिक मिलान / वर्तनी अंतर - स्थलीय जाँच आवश्यक)",
        )

        # 4. Matched (मिला)
        self._create_records_sheet(
            wb,
            sheet_title="3. मिला",
            records=[r for r in self.result.records_b if r.tier == "मिला"],
            banner_text="सत्यापित मिलान (दोनों सूचियों में समान पाए गए मतदाता)",
        )

        # 5. Only in List A (केवल सूची A में)
        self._create_unmatched_a_sheet(wb)

        # 6. Master Full List (पूरी सूची)
        self._create_records_sheet(
            wb,
            sheet_title="5. पूरी सूची",
            records=self.result.records_b,
            banner_text="समस्त मतदाता स्थिति (पूरी सूची B का मिलान परिणाम)",
        )

        wb.save(output_path)

    def _create_summary_sheet(self, wb: openpyxl.Workbook) -> None:
        """Sheet: सारांश with stats, guidelines, and methodology description."""
        ws = wb.create_sheet(title="सारांश")
        ws.views.sheetView[0].showGridLines = True

        # Title
        ws.merge_cells("A1:G1")
        title_cell = ws["A1"]
        title_cell.value = "मतदाता सूची मिलान — सारांश एवं आँकड़े (Electoral Roll Matching Summary)"
        title_cell.font = Font(name=FONT_NAME, size=15, bold=True, color="FFFFFF")
        title_cell.fill = PatternFill("solid", fgColor=COLOR_TITLE)
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 36

        # Subtitle
        ws.merge_cells("A2:G2")
        sub_cell = ws["A2"]
        sub_cell.value = "बूथ लेवल अधिकारी (BLO) स्थलीय सत्यापन मार्गदर्शिका (अद्यतन रिपोर्ट)"
        sub_cell.font = Font(name=FONT_NAME, size=11, italic=True)
        sub_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 22

        # Statistics Table
        ws["A4"] = "श्रेणी (Category)"
        ws["B4"] = "मतदाता संख्या"
        ws["C4"] = "प्रतिशत (%)"
        ws["D4"] = "कार्यवाही (BLO Action)"

        for col in ["A4", "B4", "C4", "D4"]:
            ws[col].font = BOLD_FONT
            ws[col].fill = PatternFill("solid", fgColor=COLOR_HEADER_GEN)
            ws[col].border = HEADER_BORDER

        total_b = max(1, len(self.result.records_b))
        matched = self.result.stats.get("मिला", 0)
        review = self.result.stats.get("जाँचें", 0)
        missing = self.result.stats.get("लापता", 0)
        only_a = self.result.stats.get("केवल सूची A में", 0)

        rows = [
            ("मिला (समान मतदाता)", matched, f"{(matched/total_b)*100:.1f}%", "सत्यापित मिलान (पुष्टि हो चुकी)", COLOR_GREEN),
            ("जाँचें (सत्यापन आवश्यक)", review, f"{(review/total_b)*100:.1f}%", "स्थलीय जाँच कर सही व्यक्ति की पुष्टि करें", COLOR_YELLOW),
            ("लापता (सूची B में नए/अमिलान)", missing, f"{(missing/total_b)*100:.1f}%", "प्रारूप-6 (Form 6) द्वारा नाम जोड़ने हेतु जाँचें", COLOR_RED),
            ("केवल सूची A में (संदर्भ सूची)", only_a, "-", "प्रारूप-7/8 (Form 7/8) द्वारा विलोपन/संशोधन जाँचें", "E2EFDA"),
        ]

        curr_r = 5
        for cat, cnt, pct, act, col_hex in rows:
            ws.row_dimensions[curr_r].height = 24
            ws[f"A{curr_r}"] = cat
            ws[f"B{curr_r}"] = cnt
            ws[f"C{curr_r}"] = pct
            ws[f"D{curr_r}"] = act

            ws[f"A{curr_r}"].fill = PatternFill("solid", fgColor=col_hex)
            for c in ["A", "B", "C", "D"]:
                ws[f"{c}{curr_r}"].font = BASE_FONT
                ws[f"{c}{curr_r}"].border = CELL_BORDER
                ws[f"{c}{curr_r}"].alignment = Alignment(vertical="center")
            ws[f"B{curr_r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"C{curr_r}"].alignment = Alignment(horizontal="center", vertical="center")
            curr_r += 1

        curr_r += 2
        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        if serial_map and (serial_map.col_a or serial_map.col_b):
            ws.merge_cells(f"A{curr_r}:G{curr_r}")
            ws[f"A{curr_r}"] = f"कागज़ी रोल क्रम संख्या कॉलम: सूची A = '{serial_map.col_a or 'अनुपलब्ध'}' | सूची B = '{serial_map.col_b or 'अनुपलब्ध'}' (कागज़ी मिलान हेतु सुरक्षित)"
            ws[f"A{curr_r}"].font = Font(name=FONT_NAME, size=11, bold=True, color="1F4E79")
            curr_r += 1

        ws.merge_cells(f"A{curr_r}:G{curr_r}")
        ws[f"A{curr_r}"] = "मिलान तकनीक एवं पद्धति विवरण:"
        ws[f"A{curr_r}"].font = Font(name=FONT_NAME, size=12, bold=True)
        curr_r += 1

        explanations = [
            "1. देवनागरी वर्तनी सामान्यीकरण: मात्राओं (ी/ि, ू/ु), आधे अक्षरों (प्रसाद/प्साद), नुक्ता, एवं अनुस्वार को एकीकृत किया गया।",
            "2. ध्वनि समरूपता (Phonetic Key): उच्चारण एवं वर्ण-वर्ग (श/ष/स, व/ब, ण/न) की समानता का सूक्ष्म विश्लेषण।",
            "3. वैश्विक 1-to-1 इष्टतम आवंटन: हंगेरियन एल्गोरिथम (Linear Sum Assignment) द्वारा प्रत्येक मतदाता का निष्पक्ष सर्वोत्तम मिलान।",
            "4. सहोदर सुरक्षा (Sibling Guard): समान पिता लेकिन भिन्न नाम वाले भाई/बहनों को गलत मिलान से बचाया गया।",
            "5. BLO सत्यापन अद्यतन: इस रिपोर्ट में BLO द्वारा 'स्थलीय सत्यापन' स्क्रीन पर लिए गए निर्णयों को शामिल किया गया है।",
        ]
        for expl in explanations:
            ws.merge_cells(f"A{curr_r}:G{curr_r}")
            ws[f"A{curr_r}"] = expl
            ws[f"A{curr_r}"].font = BASE_FONT
            ws.row_dimensions[curr_r].height = 22
            curr_r += 1

        auto_fit_columns(ws, min_width=15, max_width=50)

    def _create_records_sheet(
        self,
        wb: openpyxl.Workbook,
        sheet_title: str,
        records: list[MatchRecordB],
        banner_text: str,
    ) -> None:
        """Create formatted comparative sheet for records with BLO decision and notes."""
        ws = wb.create_sheet(title=sheet_title)
        ws.views.sheetView[0].showGridLines = True

        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        kram_col_b = serial_map.col_b if serial_map else None
        kram_col_a = serial_map.col_a if serial_map else None

        cols_b = [m.col_b for m in self.mappings if m.col_b and m.col_b != kram_col_b]
        cols_a = [m.col_a for m in self.mappings if m.col_a and m.col_a != kram_col_a]

        row1_cells = [
            ("क्रम", COLOR_HEADER_GEN),
            ("कागज़ी क्र० (सूची B)", COLOR_HEADER_B),
            ("कागज़ी क्र० (सूची A)", COLOR_HEADER_A),
            ("परिणाम स्थिति", COLOR_HEADER_GEN),
            ("स्कोर %", COLOR_HEADER_GEN),
            ("मिलान कारण / अंतर", COLOR_HEADER_GEN),
        ]
        for _ in cols_b:
            row1_cells.append((self.label_b, COLOR_HEADER_B))
        for _ in cols_a:
            row1_cells.append((self.label_a, COLOR_HEADER_A))
        row1_cells.extend([
            ("BLO निर्णय (सत्यापन)", COLOR_HEADER_GEN),
            ("BLO स्थलीय टिप्पणी (कैफियत)", COLOR_HEADER_GEN),
            ("हस्ताक्षर", COLOR_HEADER_GEN),
        ])

        hdr_b_kram = f"क्र० [{kram_col_b}]" if kram_col_b else "क्र० सं० (B)"
        hdr_a_kram = f"क्र० [{kram_col_a}]" if kram_col_a else "क्र० सं० (A)"

        row2_labels = ["क्र०", hdr_b_kram, hdr_a_kram, "स्थिति", "स्कोर", "कारण"]
        for c in cols_b:
            row2_labels.append(c)
        for c in cols_a:
            row2_labels.append(f"{c} (A)")
        row2_labels.extend(["BLO निर्णय", "स्थलीय टिप्पणी (Remarks)", "हस्ताक्षर / दिनांक"])

        ws.row_dimensions[1].height = 26
        ws.row_dimensions[2].height = 28

        for idx, (label, color_hex) in enumerate(row1_cells, start=1):
            cell = ws.cell(row=1, column=idx, value=label)
            cell.font = BOLD_FONT
            cell.fill = PatternFill("solid", fgColor=color_hex)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = HEADER_BORDER

        for idx, label in enumerate(row2_labels, start=1):
            cell = ws.cell(row=2, column=idx, value=label)
            cell.font = BOLD_FONT
            cell.fill = PatternFill("solid", fgColor="EFEFEF")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = HEADER_BORDER

        # Data Rows
        row_num = 3
        for rec in records:
            ws.row_dimensions[row_num].height = 24
            rec_b = rec.record_b
            rec_a = rec.assigned_record_a or (rec.top_candidates[0].record_a if rec.top_candidates else {})

            col_idx = 1
            # 1. Serial No
            ws.cell(row=row_num, column=col_idx, value=rec.b_idx + 1)
            col_idx += 1

            # 2. Paper Roll Kram Sankhya List B
            b_kram_val = str(rec_b.get(kram_col_b, "")) if kram_col_b and kram_col_b in rec_b else str(rec_b.get("_orig_row", rec.b_idx + 2))
            ws.cell(row=row_num, column=col_idx, value=b_kram_val)
            col_idx += 1

            # 3. Paper Roll Kram Sankhya List A
            if rec.assigned_record_a and kram_col_a and kram_col_a in rec.assigned_record_a:
                a_kram_val = str(rec.assigned_record_a.get(kram_col_a, ""))
            elif rec_a and kram_col_a and kram_col_a in rec_a:
                a_kram_val = str(rec_a.get(kram_col_a, ""))
            elif rec.tier == "लापता":
                a_kram_val = "लापता"
            elif rec_a and "_orig_row" in rec_a:
                a_kram_val = str(rec_a.get("_orig_row", "-"))
            else:
                a_kram_val = "-"
            ws.cell(row=row_num, column=col_idx, value=a_kram_val)
            col_idx += 1

            # 4. Result Tier
            t_cell = ws.cell(row=row_num, column=col_idx, value=rec.tier)
            if rec.tier == "मिला":
                t_cell.fill = PatternFill("solid", fgColor=COLOR_GREEN)
            elif rec.tier == "जाँचें":
                t_cell.fill = PatternFill("solid", fgColor=COLOR_YELLOW)
            else:
                t_cell.fill = PatternFill("solid", fgColor=COLOR_RED)
            col_idx += 1

            # 5. Score %
            score_val = rec.best_score_result.score if rec.best_score_result else 0.0
            ws.cell(row=row_num, column=col_idx, value=f"{int(score_val * 100)}%" if score_val > 0 else "-")
            col_idx += 1

            # 6. Reasons
            reasons_str = "; ".join(rec.best_score_result.reasons) if rec.best_score_result else "-"
            ws.cell(row=row_num, column=col_idx, value=reasons_str)
            col_idx += 1

            # List B Columns
            for c in cols_b:
                ws.cell(row=row_num, column=col_idx, value=str(rec_b.get(c, "") or ""))
                col_idx += 1

            # List A Columns
            for c in cols_a:
                ws.cell(row=row_num, column=col_idx, value=str(rec_a.get(c, "") or ""))
                col_idx += 1

            # BLO Decision & Notes from verification screen
            dec_text = rec.user_decision or ("स्वतः मिलान" if rec.tier == "मिला" else "")
            ws.cell(row=row_num, column=col_idx, value=dec_text)
            col_idx += 1

            ws.cell(row=row_num, column=col_idx, value=rec.notes or "")
            col_idx += 1

            ws.cell(row=row_num, column=col_idx, value="")  # Signature
            col_idx += 1

            for c_i in range(1, col_idx):
                c_cell = ws.cell(row=row_num, column=c_i)
                c_cell.font = BASE_FONT
                c_cell.border = CELL_BORDER
                c_cell.alignment = Alignment(vertical="center")

            ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=2).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=3).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=4).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=5).alignment = Alignment(horizontal="center", vertical="center")

            row_num += 1

        ws.freeze_panes = "A3"
        last_col = get_column_letter(len(row2_labels))
        ws.auto_filter.ref = f"A2:{last_col}{max(2, row_num - 1)}"
        style_print_setup(ws, title_rows="1:2")
        auto_fit_columns(ws)

    def _create_unmatched_a_sheet(self, wb: openpyxl.Workbook) -> None:
        """Create sheet for records remaining only in List A."""
        ws = wb.create_sheet(title="4. केवल सूची A में")
        ws.views.sheetView[0].showGridLines = True

        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        kram_col_a = serial_map.col_a if serial_map else None
        cols_a = [m.col_a for m in self.mappings if m.col_a and m.col_a != kram_col_a]

        ws.row_dimensions[1].height = 28
        hdr_a_kram = f"क्र० [{kram_col_a}]" if kram_col_a else "क्र० सं० (सूची A)"
        headers = ["क्र०", hdr_a_kram, "स्थिति"] + cols_a + ["BLO सत्यापन", "विलोपन/संशोधन टिप्पणी"]

        for idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=idx, value=h)
            cell.font = BOLD_FONT
            cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_A)
            cell.border = HEADER_BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center")

        row_num = 2
        for s_idx, a_i in enumerate(self.result.unmatched_a_indices, start=1):
            ws.row_dimensions[row_num].height = 24
            rec_a = self.result.records_a[a_i]

            ws.cell(row=row_num, column=1, value=s_idx)
            a_kram_val = str(rec_a.get(kram_col_a, "")) if kram_col_a and kram_col_a in rec_a else str(rec_a.get("_orig_row", "-"))
            ws.cell(row=row_num, column=2, value=a_kram_val)
            ws.cell(row=row_num, column=3, value="केवल सूची A में")

            c_idx = 4
            for c in cols_a:
                ws.cell(row=row_num, column=c_idx, value=str(rec_a.get(c, "") or ""))
                c_idx += 1

            ws.cell(row=row_num, column=c_idx, value="")
            c_idx += 1
            ws.cell(row=row_num, column=c_idx, value="")

            for i in range(1, c_idx + 1):
                cell = ws.cell(row=row_num, column=i)
                cell.font = BASE_FONT
                cell.border = CELL_BORDER
                cell.alignment = Alignment(vertical="center")

            ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=2).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=row_num, column=3).alignment = Alignment(horizontal="center", vertical="center")

            row_num += 1

        ws.freeze_panes = "A2"
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A1:{last_col}{max(1, row_num - 1)}"
        style_print_setup(ws, title_rows="1:1")
        auto_fit_columns(ws)
