"""Global Fuzzy Search Page (त्वरित सार्वभौमिक खोज).

Allows typing any Hindi spelling variation and instantly retrieving the top-10
most similar records from both List A and List B using the full Devanagari matching engine.
Designed with high-contrast headers and clear typography.
"""

from __future__ import annotations
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QSplitter,
    QFrame,
)

from voter_match.core.normalize import normalize_hindi_name, NormalizedName
from voter_match.core.similarity import name_similarity
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    BORDER_COLOR,
    GREEN_PRIMARY,
)


class SearchPage(QWidget):
    """Global search across both lists with live Indic ranking."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.records_a: list[dict[str, Any]] = []
        self.records_b: list[dict[str, Any]] = []
        self.cols_a: list[str] = []
        self.cols_b: list[str] = []
        self.norm_a: list[NormalizedName] = []
        self.norm_b: list[NormalizedName] = []
        self.voter_col_a: str = ""
        self.voter_col_b: str = ""
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(12)

        header_lbl = QLabel("त्वरित सार्वभौमिक खोज (Global Indic Fuzzy Search)")
        header_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY_PRIMARY};")
        main_layout.addWidget(header_lbl)

        # Guidance Card
        help_card = QFrame()
        help_card.setStyleSheet(
            f"background-color: #FFFFFF; border: 1px solid #BFDBFE; "
            f"border-left: 5px solid {NAVY_PRIMARY}; border-radius: 6px; padding: 8px 12px;"
        )
        hc_layout = QHBoxLayout(help_card)
        hc_layout.setContentsMargins(6, 4, 6, 4)
        lbl_h = QLabel(
            "💡 <b>किसी भी मतदाता को तुरंत खोजें:</b> यदि किसी मतदाता के नाम की स्पेलिंग गलत है (जैसे 'सुनील' की जगह 'सुनिल' या 'ओमप्रकाश' की जगह 'ओमप्काश'), "
            "तो यहाँ किसी भी रूप में नाम टाइप करें। कंप्यूटर दोनों सूचियों से सबसे मिलते-जुलते नाम खोजकर लाएगा।"
        )
        lbl_h.setTextFormat(Qt.RichText)
        lbl_h.setStyleSheet("color: #1E293B; font-size: 12px;")
        hc_layout.addWidget(lbl_h)
        main_layout.addWidget(help_card)

        # Search Bar
        search_card = QFrame()
        search_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px;")
        search_box = QHBoxLayout(search_card)
        search_box.setContentsMargins(6, 4, 6, 4)

        search_lbl = QLabel("नाम टाइप करें:")
        search_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #1E293B;")
        search_box.addWidget(search_lbl)

        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("उदा० जमीलखां, ओमप्काश, सुनिल, प्रसाद, कृष्ण...")
        self.txt_query.setStyleSheet("font-size: 14px; padding: 6px;")
        self.txt_query.returnPressed.connect(self.run_search)
        search_box.addWidget(self.txt_query)

        self.btn_search = QPushButton("🔍 खोजें (Search)")
        self.btn_search.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_search.clicked.connect(self.run_search)
        search_box.addWidget(self.btn_search)

        main_layout.addWidget(search_card)

        # Side-by-Side Results Tables for List A and List B
        splitter = QSplitter(Qt.Horizontal)

        table_qss = (
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )

        # List A Results
        box_a = QGroupBox("सूची A (संदर्भ सूची) के शीर्ष-10 परिणाम")
        box_a.setStyleSheet(f"QGroupBox {{ font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY}; }}")
        layout_a = QVBoxLayout(box_a)
        self.table_a = QTableWidget()
        self.table_a.setAlternatingRowColors(True)
        self.table_a.setStyleSheet(table_qss)
        layout_a.addWidget(self.table_a)
        splitter.addWidget(box_a)

        # List B Results
        box_b = QGroupBox("सूची B (सत्यापन सूची) के शीर्ष-10 परिणाम")
        box_b.setStyleSheet(f"QGroupBox {{ font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY}; }}")
        layout_b = QVBoxLayout(box_b)
        self.table_b = QTableWidget()
        self.table_b.setAlternatingRowColors(True)
        self.table_b.setStyleSheet(table_qss)
        layout_b.addWidget(self.table_b)
        splitter.addWidget(box_b)

        splitter.setSizes([500, 500])
        main_layout.addWidget(splitter)

    def set_data(self, recs_a: list[dict[str, Any]], recs_b: list[dict[str, Any]], cols_a: list[str], cols_b: list[str]) -> None:
        self.records_a = recs_a
        self.records_b = recs_b
        self.cols_a = cols_a
        self.cols_b = cols_b

        self.voter_col_a = next((c for c in cols_a if any(k in c.lower() for k in ["नाम", "voter", "name"])), cols_a[0] if cols_a else "")
        self.voter_col_b = next((c for c in cols_b if any(k in c.lower() for k in ["नाम", "voter", "name"])), cols_b[0] if cols_b else "")

        if self.voter_col_a:
            self.norm_a = [normalize_hindi_name(r.get(self.voter_col_a)) for r in recs_a]
        if self.voter_col_b:
            self.norm_b = [normalize_hindi_name(r.get(self.voter_col_b)) for r in recs_b]

    def run_search(self) -> None:
        query = self.txt_query.text().strip()
        if not query:
            return

        norm_query = normalize_hindi_name(query)

        scored_a: list[tuple[float, str, dict[str, Any]]] = []
        for idx, rec in enumerate(self.records_a):
            n_val = self.norm_a[idx] if idx < len(self.norm_a) else normalize_hindi_name(rec.get(self.voter_col_a))
            sim, method = name_similarity(norm_query, n_val)
            if sim > 0.40:
                scored_a.append((sim, method, rec))
        scored_a.sort(key=lambda x: x[0], reverse=True)

        scored_b: list[tuple[float, str, dict[str, Any]]] = []
        for idx, rec in enumerate(self.records_b):
            n_val = self.norm_b[idx] if idx < len(self.norm_b) else normalize_hindi_name(rec.get(self.voter_col_b))
            sim, method = name_similarity(norm_query, n_val)
            if sim > 0.40:
                scored_b.append((sim, method, rec))
        scored_b.sort(key=lambda x: x[0], reverse=True)

        self._populate_search_table(self.table_a, scored_a[:10], self.voter_col_a)
        self._populate_search_table(self.table_b, scored_b[:10], self.voter_col_b)

    def _populate_search_table(self, table: QTableWidget, items: list[tuple[float, str, dict[str, Any]]], voter_col: str) -> None:
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["रैंक", "समानता %", "मतदाता नाम", "मिलान का प्रकार"])
        table.setRowCount(len(items))

        dark_text = QColor(15, 23, 42)
        font_bold = QFont("Nirmala UI", 10, QFont.Bold)

        for rank, (sim, method, rec) in enumerate(items, start=1):
            item_rank = QTableWidgetItem(f"#{rank}")
            item_rank.setTextAlignment(Qt.AlignCenter)
            item_rank.setForeground(QBrush(QColor(71, 85, 105)))
            table.setItem(rank - 1, 0, item_rank)

            sc_item = QTableWidgetItem(f"{int(sim*100)}%")
            sc_item.setTextAlignment(Qt.AlignCenter)
            sc_item.setFont(font_bold)
            if sim >= 0.88:
                sc_item.setBackground(QBrush(QColor(220, 252, 231)))
                sc_item.setForeground(QBrush(QColor(22, 101, 52)))
            elif sim >= 0.70:
                sc_item.setBackground(QBrush(QColor(254, 243, 199)))
                sc_item.setForeground(QBrush(QColor(146, 64, 14)))
            else:
                sc_item.setForeground(QBrush(dark_text))
            table.setItem(rank - 1, 1, sc_item)

            item_name = QTableWidgetItem(str(rec.get(voter_col, "")))
            item_name.setForeground(QBrush(dark_text))
            table.setItem(rank - 1, 2, item_name)

            item_method = QTableWidgetItem(method)
            item_method.setForeground(QBrush(QColor(71, 85, 105)))
            table.setItem(rank - 1, 3, item_method)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
