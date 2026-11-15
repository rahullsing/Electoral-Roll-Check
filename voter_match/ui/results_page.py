"""Results Summary and Export Page (मिलान परिणाम एवं रिपोर्ट).

Designed for Government School Teachers and BLOs.
Features clear high-contrast table rendering (preventing white-on-white text),
plain-language summary cards, and intuitive export/review actions.
"""

from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QFrame,
    QSizePolicy,
)

from voter_match.core.matcher import MatchSessionResult
from voter_match.core.scorer import ColumnMapping
from voter_match.export.excel_export import ExcelExporter
from voter_match.export.pdf_export import PdfExporter
from voter_match.ui.i18n import mark_translatable
from voter_match.ui.theme import (
    fit_table_columns,
    scoped_style,
    NAVY_PRIMARY,
    TEXT_DARK,
    GREEN_PRIMARY,
    GREEN_BG,
    GREEN_TEXT,
    AMBER_BG,
    AMBER_TEXT,
    AMBER_PRIMARY,
    RED_BG,
    RED_TEXT,
    RED_PRIMARY,
    BLUE_BG,
    BLUE_TEXT,
    BORDER_COLOR,
)


class CompactStatPill(QFrame):
    """Sleek horizontal KPI pill providing clear metrics while taking minimal vertical height.
    Clickable to filter results table directly by criteria.
    """

    clicked = Signal(str)

    def __init__(
        self,
        title: str,
        count: int,
        percentage: str,
        desc: str,
        border_color: str,
        bg_color: str,
        text_color: str,
        filter_key: str = "all",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.filter_key = filter_key
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        scoped_style(
            self,
            f"background-color: {bg_color}; border: 1.5px solid {border_color}; border-radius: 6px;",
            hover_css=f"border: 2px solid {text_color}; background-color: #FFFFFF;",
        )
        self.setToolTip(f"{title}: {desc}\n👉 क्लिक करके केवल ये रिकॉर्ड्स देखें")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {text_color};")
        layout.addWidget(lbl_t)

        lbl_c = QLabel(f"{count:,}")
        lbl_c.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {text_color};")
        layout.addWidget(lbl_c)

        if percentage:
            lbl_p = QLabel(f"({percentage})")
            lbl_p.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {text_color};")
            layout.addWidget(lbl_p)

        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filter_key)
        super().mousePressEvent(event)


# Backwards compatibility alias
StatCard = CompactStatPill


class ResultsPage(QWidget):
    """Results summary dashboard and report generator."""

    go_to_review = Signal()
    save_session_requested = Signal()
    accuracy_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session_result: MatchSessionResult | None = None
        self.mappings: list[ColumnMapping] = []
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Single Streamlined Top Bar (Title + Save Session + Excel Export + PDF Export + SINGLE Review Button)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        header_lbl = QLabel("चरण 3: मिलान परिणाम (Results & Export)")
        header_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        top_bar.addWidget(header_lbl)

        top_bar.addSpacing(10)

        # Direct Export Buttons in Top Toolbar
        self.btn_export_excel = QPushButton("📊 Excel रिपोर्ट (.xlsx)")
        self.btn_export_excel.setStyleSheet(
            "background-color: #15803D; color: #FFFFFF; font-weight: bold; "
            "padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_export_excel.setToolTip("सत्यापन निर्णयों और टिप्पणियों के साथ 5-शीट Excel रिपोर्ट सहेजें")
        self.btn_export_excel.clicked.connect(self.export_excel)
        top_bar.addWidget(self.btn_export_excel)

        self.btn_export_pdf = QPushButton("📄 सत्यापन PDF प्रपत्र")
        self.btn_export_pdf.setStyleSheet(
            "background-color: #DC2626; color: #FFFFFF; font-weight: bold; "
            "padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_export_pdf.setToolTip("फ़ील्ड में ले जाने हेतु प्रिंट-अनुकूलित PDF डाउनलोड करें")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        top_bar.addWidget(self.btn_export_pdf)

        self.btn_export_forms = QPushButton("📋 प्रारूप 6/7/8 कार्य-सूची")
        self.btn_export_forms.setStyleSheet(
            "background-color: #7C3AED; color: #FFFFFF; font-weight: bold; "
            "padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_export_forms.setToolTip(
            "किसके लिए प्रारूप-6 (नाम जोड़ना), प्रारूप-7 (विलोपन) या प्रारूप-8 (संशोधन) भरना है — "
            "Excel व PDF चेकलिस्ट"
        )
        self.btn_export_forms.clicked.connect(self.export_forms)
        top_bar.addWidget(self.btn_export_forms)

        self.btn_accuracy = QPushButton("📈 सटीकता जाँच")
        self.btn_accuracy.setStyleSheet(
            "background-color: #0F766E; color: #FFFFFF; font-weight: bold; "
            "padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_accuracy.setToolTip("आपके सत्यापन निर्णयों के आधार पर कंप्यूटर की सटीकता देखें और बेहतर सीमाएँ पाएं")
        self.btn_accuracy.clicked.connect(self.accuracy_requested.emit)
        top_bar.addWidget(self.btn_accuracy)

        top_bar.addStretch()

        # SINGLE Next Button to Review Screen (No duplicate buttons!)
        self.btn_review = QPushButton("🔍 स्थलीय सत्यापन (Review) पर आगे बढ़ें ➔")
        self.btn_review.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 7px 18px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_review.setToolTip("संदेहास्पद रिकॉर्ड्स को एक-एक करके आमने-सामने जाँचें")
        self.btn_review.clicked.connect(self.go_to_review.emit)
        top_bar.addWidget(self.btn_review)

        # Compatibility aliases for legacy references
        self.btn_review_top = self.btn_review
        self.btn_review_bottom = self.btn_review

        main_layout.addLayout(top_bar)

        # Compact KPI Summary Pills Strip (Height: ~36px, zero wasted vertical space!)
        self.cards_layout = QHBoxLayout()
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        main_layout.addLayout(self.cards_layout)

        # Criteria Filter and Search Toolbar (~34px)
        filter_bar = QFrame()
        scoped_style(filter_bar, "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;")
        fb_layout = QHBoxLayout(filter_bar)
        fb_layout.setContentsMargins(6, 2, 6, 2)
        fb_layout.setSpacing(8)

        lbl_crit = QLabel("🎯 परिणाम फ़िल्टर (Criteria):")
        lbl_crit.setStyleSheet("font-weight: bold; font-size: 11px; color: #1E293B;")
        fb_layout.addWidget(lbl_crit)

        self.combo_criteria = mark_translatable(QComboBox())
        self.combo_criteria.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: bold;")
        self.combo_criteria.addItem("📋 सभी परिणाम (All Results)", "all")
        self.combo_criteria.addItem("🟢 केवल मिला (Matched Only)", "मिला")
        self.combo_criteria.addItem("🟡 केवल जाँचें (Needs Review Only)", "जाँचें")
        self.combo_criteria.addItem("🔴 केवल नहीं मिला / लापता (Missing in A Only)", "लापता")
        self.combo_criteria.addItem("🔵 केवल सूची A में (Only in List A)", "only_a")
        self.combo_criteria.currentIndexChanged.connect(self.populate_table)
        fb_layout.addWidget(self.combo_criteria)

        fb_layout.addSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 नाम, सम्बन्धी, या क्र० खोजें...")
        self.txt_search.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.txt_search.setMinimumWidth(180)
        self.txt_search.textChanged.connect(self.populate_table)
        fb_layout.addWidget(self.txt_search)

        self.btn_reset_filter = QPushButton("✕ साफ़ करें")
        self.btn_reset_filter.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self.btn_reset_filter.clicked.connect(self.reset_filter)
        fb_layout.addWidget(self.btn_reset_filter)

        fb_layout.addStretch()

        self.lbl_filtered_count = QLabel("दिखाए गए: 0 / 0")
        self.lbl_filtered_count.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {NAVY_PRIMARY};")
        fb_layout.addWidget(self.lbl_filtered_count)

        main_layout.addWidget(filter_bar)

        # High-Contrast Results Table Preview taking 85%+ of screen height!
        self.table_results = mark_translatable(QTableWidget())
        self.table_results.setAlternatingRowColors(True)
        self.table_results.verticalHeader().setVisible(False)  # क्र० column already numbers rows
        self.table_results.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Guaranteed high-contrast stylesheet: Dark Navy Header with crisp bold white text
        self.table_results.setStyleSheet(
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )
        main_layout.addWidget(self.table_results)

    def set_results(self, result: MatchSessionResult, mappings: list[ColumnMapping]) -> None:
        self.session_result = result
        self.mappings = mappings
        self.update_kpi_cards()
        self.populate_table()

    def update_kpi_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.session_result:
            return

        total_b = max(1, len(self.session_result.records_b))
        matched = self.session_result.stats.get("मिला", 0)
        review = self.session_result.stats.get("जाँचें", 0)
        missing = self.session_result.stats.get("लापता", 0)
        only_a = self.session_result.stats.get("केवल सूची A में", 0)

        card_matched = CompactStatPill(
            title="🟢 मिला",
            count=matched,
            percentage=f"{(matched/total_b)*100:.1f}%",
            desc="दोनों सूचियों में समान पाए गए मतदाता (पुष्टि हो चुकी)।",
            border_color="#22C55E",
            bg_color="#F0FDF4",
            text_color="#15803D",
            filter_key="मिला",
        )
        card_matched.clicked.connect(self.on_filter_pill_clicked)

        card_review = CompactStatPill(
            title="🟡 जाँचें",
            count=review,
            percentage=f"{(review/total_b)*100:.1f}%",
            desc="मात्रा या वर्तनी का अंतर है। स्थलीय सत्यापन आवश्यक है।",
            border_color="#F59E0B",
            bg_color="#FFFBEB",
            text_color="#B45309",
            filter_key="जाँचें",
        )
        card_review.clicked.connect(self.on_filter_pill_clicked)

        card_missing = CompactStatPill(
            title="🔴 लापता",
            count=missing,
            percentage=f"{(missing/total_b)*100:.1f}%",
            desc="सूची B में उपलब्ध हैं किन्तु सूची A में नहीं मिले।",
            border_color="#EF4444",
            bg_color="#FEF2F2",
            text_color="#B91C1C",
            filter_key="लापता",
        )
        card_missing.clicked.connect(self.on_filter_pill_clicked)

        card_only_a = CompactStatPill(
            title="🔵 केवल A में",
            count=only_a,
            percentage="",
            desc="संदर्भ सूची में हैं लेकिन सत्यापन सूची में नहीं मिले।",
            border_color="#3B82F6",
            bg_color="#EFF6FF",
            text_color="#1D4ED8",
            filter_key="only_a",
        )
        card_only_a.clicked.connect(self.on_filter_pill_clicked)

        card_total = CompactStatPill(
            title="📋 कुल (B)",
            count=len(self.session_result.records_b),
            percentage="",
            desc="सत्यापन सूची B में कुल मतदाता",
            border_color="#94A3B8",
            bg_color="#F8FAFC",
            text_color="#334155",
            filter_key="all",
        )
        card_total.clicked.connect(self.on_filter_pill_clicked)

        self.cards_layout.addWidget(card_matched)
        self.cards_layout.addWidget(card_review)
        self.cards_layout.addWidget(card_missing)
        self.cards_layout.addWidget(card_only_a)
        self.cards_layout.addWidget(card_total)

    def on_filter_pill_clicked(self, filter_key: str) -> None:
        idx = self.combo_criteria.findData(filter_key)
        if idx >= 0:
            self.combo_criteria.setCurrentIndex(idx)

    def reset_filter(self) -> None:
        self.txt_search.clear()
        self.combo_criteria.setCurrentIndex(0)

    def populate_table(self) -> None:
        if not self.session_result:
            return

        crit = self.combo_criteria.currentData() or "all"
        query = self.txt_search.text().strip().lower()

        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        kram_col_b = serial_map.col_b if serial_map else None
        kram_col_a = serial_map.col_a if serial_map else None

        voter_map = next((m for m in self.mappings if m.role == "voter_name"), None)
        rel_map = next((m for m in self.mappings if m.role == "relative_name"), None)

        v_b = voter_map.col_b if voter_map else ""
        v_a = voter_map.col_a if voter_map else ""
        r_b = rel_map.col_b if rel_map else ""
        r_a = rel_map.col_a if rel_map else ""

        lbl_b_kram = f"क्र० [{kram_col_b}]" if kram_col_b else "क्र० (B)"
        lbl_a_kram = f"क्र० [{kram_col_a}]" if kram_col_a else "क्र० (A)"

        dark_text_color = QColor(15, 23, 42)
        font_bold = QFont("Nirmala UI", 10, QFont.Bold)
        center_align = Qt.AlignCenter
        left_align = Qt.AlignVCenter | Qt.AlignLeft

        # Handle "केवल सूची A में" (Unmatched reference list records)
        if crit == "only_a":
            headers = [
                "क्र०",
                lbl_b_kram,
                lbl_a_kram,
                "स्थिति (Status)",
                "स्कोर %",
                "मतदाता (सूची B)",
                "सम्बन्धी (सूची B)",
                "मतदाता (सूची A)",
                "सम्बन्धी (सूची A)",
                "विवरण / कारण",
            ]
            self.table_results.setColumnCount(len(headers))
            self.table_results.setHorizontalHeaderLabels(headers)

            unmatched_indices = self.session_result.unmatched_a_indices
            filtered_indices = []
            for a_idx in unmatched_indices:
                rec_a = self.session_result.records_a[a_idx]
                va_str = str(rec_a.get(v_a, "") or "")
                ra_str = str(rec_a.get(r_a, "") or "")
                ka_str = str(rec_a.get(kram_col_a, "") or rec_a.get("_orig_row", a_idx + 2))
                if query:
                    if query not in va_str.lower() and query not in ra_str.lower() and query not in ka_str.lower():
                        continue
                filtered_indices.append((a_idx, rec_a, va_str, ra_str, ka_str))

            self.table_results.setRowCount(len(filtered_indices))
            for row_i, (a_idx, rec_a, va_str, ra_str, ka_str) in enumerate(filtered_indices):
                # 0: Serial
                it_s = QTableWidgetItem(str(row_i + 1))
                it_s.setTextAlignment(center_align)
                self.table_results.setItem(row_i, 0, it_s)

                # 1: Kram B (None)
                it_kb = QTableWidgetItem("-")
                it_kb.setTextAlignment(center_align)
                self.table_results.setItem(row_i, 1, it_kb)

                # 2: Kram A
                it_ka = QTableWidgetItem(ka_str)
                it_ka.setTextAlignment(center_align)
                it_ka.setFont(font_bold)
                it_ka.setForeground(QBrush(QColor(109, 40, 217)))
                self.table_results.setItem(row_i, 2, it_ka)

                # 3: Status
                it_st = QTableWidgetItem(" केवल A में ")
                it_st.setTextAlignment(center_align)
                it_st.setFont(font_bold)
                it_st.setBackground(QBrush(QColor(219, 234, 254)))  # Soft Blue
                it_st.setForeground(QBrush(QColor(29, 78, 216)))    # Deep Blue
                self.table_results.setItem(row_i, 3, it_st)

                # 4: Score %
                it_sc = QTableWidgetItem("-")
                it_sc.setTextAlignment(center_align)
                self.table_results.setItem(row_i, 4, it_sc)

                # 5: Voter B
                it_vb = QTableWidgetItem("-")
                it_vb.setTextAlignment(left_align)
                self.table_results.setItem(row_i, 5, it_vb)

                # 6: Rel B
                it_rb = QTableWidgetItem("-")
                it_rb.setTextAlignment(left_align)
                self.table_results.setItem(row_i, 6, it_rb)

                # 7: Voter A
                it_va = QTableWidgetItem(va_str)
                it_va.setTextAlignment(left_align)
                it_va.setForeground(QBrush(dark_text_color))
                self.table_results.setItem(row_i, 7, it_va)

                # 8: Rel A
                it_ra = QTableWidgetItem(ra_str)
                it_ra.setTextAlignment(left_align)
                it_ra.setForeground(QBrush(dark_text_color))
                self.table_results.setItem(row_i, 8, it_ra)

                # 9: Details
                it_rsn = QTableWidgetItem("सत्यापन सूची B में कोई मिलान नहीं मिला (केवल संदर्भ सूची में उपलब्ध)")
                it_rsn.setTextAlignment(left_align)
                it_rsn.setForeground(QBrush(QColor(71, 85, 105)))
                self.table_results.setItem(row_i, 9, it_rsn)

            self.lbl_filtered_count.setText(
                f"दिखाए गए रिकॉर्ड्स: {len(filtered_indices):,} / {len(unmatched_indices):,}"
            )
            fit_table_columns(self.table_results)
            return

        # Normal List B Records Filtering (all, मिला, जाँचें, लापता)
        recs = self.session_result.records_b
        filtered_recs: list[tuple[int, Any, dict, dict, str, str, str, str, str, str]] = []

        for idx, r in enumerate(recs):
            if crit != "all" and r.tier != crit:
                continue

            rec_b = r.record_b
            rec_a = r.assigned_record_a or (r.top_candidates[0].record_a if r.top_candidates else {})

            vb_val = str(rec_b.get(v_b, "") or "")
            rb_val = str(rec_b.get(r_b, "") or "")
            kb_val = str(rec_b.get(kram_col_b, "")) if kram_col_b and kram_col_b in rec_b else str(rec_b.get("_orig_row", idx + 2))

            va_val = str(rec_a.get(v_a, "") or "")
            ra_val = str(rec_a.get(r_a, "") or "")
            if r.assigned_record_a and kram_col_a and kram_col_a in r.assigned_record_a:
                ka_val = str(r.assigned_record_a.get(kram_col_a, ""))
            elif rec_a and kram_col_a and kram_col_a in rec_a:
                ka_val = str(rec_a.get(kram_col_a, ""))
            elif r.tier == "लापता":
                ka_val = "लापता"
            elif rec_a and "_orig_row" in rec_a:
                ka_val = str(rec_a.get("_orig_row", "-"))
            else:
                ka_val = "-"

            if query:
                combined = f"{vb_val} {rb_val} {kb_val} {va_val} {ra_val} {ka_val}".lower()
                if query not in combined:
                    continue

            filtered_recs.append((idx, r, rec_b, rec_a, vb_val, rb_val, kb_val, va_val, ra_val, ka_val))

        headers = [
            "क्र०",
            lbl_b_kram,
            lbl_a_kram,
            "स्थिति (Status)",
            "स्कोर %",
            "मतदाता (सूची B)",
            "सम्बन्धी (सूची B)",
            "निकटतम प्रत्याशी (सूची A)",
            "सम्बन्धी (सूची A)",
            "मिलान का कारण",
        ]
        self.table_results.setColumnCount(len(headers))
        self.table_results.setHorizontalHeaderLabels(headers)
        self.table_results.setRowCount(len(filtered_recs))

        for row_i, (orig_idx, r, rec_b, rec_a, vb_val, rb_val, kb_val, va_val, ra_val, ka_val) in enumerate(filtered_recs):
            # 1. Serial No
            item_idx = QTableWidgetItem(str(row_i + 1))
            item_idx.setTextAlignment(center_align)
            item_idx.setForeground(QBrush(QColor(71, 85, 105)))
            self.table_results.setItem(row_i, 0, item_idx)

            # 2. Kram B
            item_kb = QTableWidgetItem(kb_val)
            item_kb.setTextAlignment(center_align)
            item_kb.setFont(font_bold)
            item_kb.setForeground(QBrush(QColor(109, 40, 217)))
            self.table_results.setItem(row_i, 1, item_kb)

            # 3. Kram A
            item_ka = QTableWidgetItem(ka_val)
            item_ka.setTextAlignment(center_align)
            item_ka.setFont(font_bold)
            item_ka.setForeground(QBrush(QColor(109, 40, 217)))
            self.table_results.setItem(row_i, 2, item_ka)

            # 4. Tier Badge with EXPLICIT background and foreground
            item_tier = QTableWidgetItem(f" {r.tier} ")
            item_tier.setTextAlignment(center_align)
            item_tier.setFont(font_bold)

            if r.tier == "मिला":
                item_tier.setBackground(QBrush(QColor(220, 252, 231)))  # Soft green
                item_tier.setForeground(QBrush(QColor(22, 101, 52)))    # Dark green text
            elif r.tier == "जाँचें":
                item_tier.setBackground(QBrush(QColor(254, 243, 199)))  # Soft amber
                item_tier.setForeground(QBrush(QColor(146, 64, 14)))    # Dark amber text
            else:
                item_tier.setBackground(QBrush(QColor(254, 226, 226)))  # Soft red
                item_tier.setForeground(QBrush(QColor(153, 27, 27)))    # Dark red text
            self.table_results.setItem(row_i, 3, item_tier)

            # 5. Score %
            sc = r.best_score_result.score if r.best_score_result else 0.0
            sc_text = f"{int(sc * 100)}%" if sc > 0 else "-"
            item_sc = QTableWidgetItem(sc_text)
            item_sc.setTextAlignment(center_align)
            item_sc.setFont(font_bold)
            item_sc.setForeground(QBrush(dark_text_color))
            self.table_results.setItem(row_i, 4, item_sc)

            # 6. Voter B
            item_vb = QTableWidgetItem(vb_val)
            item_vb.setTextAlignment(left_align)
            item_vb.setForeground(QBrush(dark_text_color))
            self.table_results.setItem(row_i, 5, item_vb)

            # 7. Rel B
            item_rb = QTableWidgetItem(rb_val)
            item_rb.setTextAlignment(left_align)
            item_rb.setForeground(QBrush(dark_text_color))
            self.table_results.setItem(row_i, 6, item_rb)

            # 8. Voter A
            item_va = QTableWidgetItem(va_val)
            item_va.setTextAlignment(left_align)
            item_va.setForeground(QBrush(dark_text_color))
            self.table_results.setItem(row_i, 7, item_va)

            # 9. Rel A
            item_ra = QTableWidgetItem(ra_val)
            item_ra.setTextAlignment(left_align)
            item_ra.setForeground(QBrush(dark_text_color))
            self.table_results.setItem(row_i, 8, item_ra)

            # 10. Reasons
            reasons = "; ".join(r.best_score_result.reasons[:2]) if r.best_score_result else "-"
            item_rsn = QTableWidgetItem(reasons)
            item_rsn.setTextAlignment(left_align)
            item_rsn.setForeground(QBrush(QColor(71, 85, 105)))
            self.table_results.setItem(row_i, 9, item_rsn)

        self.lbl_filtered_count.setText(
            f"दिखाए गए रिकॉर्ड्स: {len(filtered_recs):,} / {len(recs):,}"
        )
        fit_table_columns(self.table_results)

    def export_excel(self) -> None:
        if not self.session_result:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Excel रिपोर्ट सहेजें",
            "मतदाता_सूची_मिलान_रिपोर्ट.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        try:
            exporter = ExcelExporter(self.session_result, self.mappings)
            exporter.export(file_path)
            QMessageBox.information(
                self,
                "सफल",
                f"Excel रिपोर्ट सफलतापूर्वक सहेजी गई:\n{file_path}\n\n"
                "रिपोर्ट में 5 शीट शामिल हैं (सारांश, लापता, जाँचें, मिला, केवल A में, पूरी सूची)।",
            )
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"Excel रिपोर्ट बनाने में समस्या:\n{e}")

    def export_forms(self) -> None:
        if not self.session_result:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "प्रारूप 6/7/8 कार्य-सूची सहेजें",
            "प्रारूप_6_7_8_कार्य_सूची.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        try:
            from voter_match.core.forms import (
                classify_form_actions,
                export_form_actions_excel,
                export_form_actions_pdf,
            )

            actions = classify_form_actions(self.session_result, self.mappings)
            export_form_actions_excel(actions, file_path)
            pdf_path = str(Path(file_path).with_suffix(".pdf"))
            pdf_note = ""
            try:
                export_form_actions_pdf(actions, pdf_path)
                pdf_note = f"\nप्रिंट हेतु PDF: {pdf_path}"
            except Exception as pe:
                pdf_note = f"\n(PDF नहीं बन सका: {pe})"
            counts = {f: sum(1 for a in actions if a.form == f) for f in ("6", "7", "8")}
            QMessageBox.information(
                self,
                "कार्य-सूची तैयार",
                f"प्रारूप-6 (नाम जोड़ना): {counts['6']}\n"
                f"प्रारूप-7 (विलोपन): {counts['7']}\n"
                f"प्रारूप-8 (संशोधन): {counts['8']}\n\n"
                f"Excel: {file_path}{pdf_note}",
            )
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"कार्य-सूची बनाने में समस्या:\n{e}")

    def export_pdf(self) -> None:
        if not self.session_result:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF प्रपत्र सहेजें",
            "मतदाता_सत्यापन_प्रपत्र.pdf",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        try:
            exporter = PdfExporter(self.session_result, self.mappings)
            exporter.export(file_path)
            QMessageBox.information(
                self,
                "सफल",
                f"PDF प्रपत्र सफलतापूर्वक तैयार किया गया:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"PDF रिपोर्ट बनाने में समस्या:\n{e}")
